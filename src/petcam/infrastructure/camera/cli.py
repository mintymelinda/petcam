#!/usr/bin/env python3
"""PetCam hardware discovery and camera worker orchestration."""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from ...domain.camera.capabilities import (
    NATIVE_H264_FORMATS,
    NATIVE_JPEG_FORMATS,
    USTREAMER_FORMATS,
    camera_identity,
    mode_max_fps,
    mode_supports_fps,
    mode_supports_resolution,
    parse_csi_cameras,
    parse_modes,
    ustreamer_format,
)
from .discovery import (
    detect_hardware_h264_encoder,
    discover_csi_cameras,
    discover_devices,
    read_model,
    usb_parent_for_video_node,
)
from ...domain.camera.capture_modes import (
    filter_devices_by_format,
    select_csi_mode,
    select_mode,
    select_native_h264_mode,
)
from ..persistence.configuration import parse_config
from ..network.diagnostics import collect_diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("discover", "select", "select-h264", "discover-csi", "select-csi", "h264-encoder", "status"))
    parser.add_argument("--device")
    parser.add_argument("--physical-path")
    parser.add_argument("--camera", type=int)
    parser.add_argument("--device-path")
    parser.add_argument("--format", default="auto")
    parser.add_argument("--resolution", default="auto")
    parser.add_argument("--fps", default="auto")
    args = parser.parse_args()

    model = read_model()
    devices = discover_devices()
    if args.physical_path:
        devices = [item for item in devices if item.get("physical_path") == args.physical_path]
    if args.device:
        requested = str(Path(args.device).resolve())
        devices = [
            item for item in devices
            if item["device"] == args.device or str(Path(item["device"]).resolve()) == requested
        ]

    if args.command == "discover":
        print(json.dumps({"model": model, "usb_devices": devices, "csi_cameras": discover_csi_cameras()}, indent=2))
        return 0
    if args.command == "discover-csi":
        print(json.dumps({"model": model, "csi_cameras": discover_csi_cameras()}, indent=2))
        return 0
    if args.command == "h264-encoder":
        result = detect_hardware_h264_encoder()
        print(json.dumps(result))
        return 0 if result["available"] else 1
    if args.command == "select-csi":
        try:
            selected_csi = select_csi_mode(
                discover_csi_cameras(), requested_camera=args.camera, resolution=args.resolution, fps=args.fps, requested_device_path=args.device_path
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        if not selected_csi:
            print("No supported CSI camera or camera mode found. Check the ribbon cable and camera-stack detection.", file=sys.stderr)
            return 1
        print(json.dumps({"backend": "csi", **selected_csi}))
        return 0
    if args.command == "select-h264":
        try:
            selected_h264 = select_native_h264_mode(devices, args.resolution, args.fps)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        if not selected_h264:
            print("No native H.264 V4L2 capture mode is advertised.", file=sys.stderr)
            return 1
        print(json.dumps(selected_h264))
        return 0
    if args.command == "select":
        devices = filter_devices_by_format(devices, args.format)
        selected = select_mode(devices)
        if not selected:
            print("No usable V4L2 capture device or supported mode found.", file=sys.stderr)
            return 1
        device, mode, native = selected
        if args.resolution != "auto":
            match = re.fullmatch(r"(\d+)x(\d+)", args.resolution)
            if not match:
                print("Resolution must be 'auto' or WIDTHxHEIGHT.", file=sys.stderr)
                return 2
            width_value, height_value = map(int, match.groups())
            matching = [m for m in device["modes"] if m["format"] == mode["format"] and mode_supports_resolution(m, width_value, height_value)]
            if not matching:
                print(f"Requested resolution {args.resolution} is not advertised by {device['device']}.", file=sys.stderr)
                return 2
            matching.sort(key=lambda m: (m["format"] not in NATIVE_JPEG_FORMATS, -mode_max_fps(m)))
            mode = matching[0]
            native = mode["format"] in NATIVE_JPEG_FORMATS
        width = args.resolution if args.resolution != "auto" else f'{mode["width"]}x{mode["height"]}'
        fps = args.fps if args.fps != "auto" else "0"
        fmt = mode["format"]
        encoder = "HW" if fmt in NATIVE_JPEG_FORMATS else "CPU"
        if args.fps != "auto" and (not args.fps.isdigit() or int(args.fps) < 1):
            print("FPS must be 'auto' or a positive integer.", file=sys.stderr)
            return 2
        if args.fps != "auto":
            fps_value = int(args.fps)
            if (mode["fps"] or mode.get("fps_range")) and not mode_supports_fps(mode, fps_value):
                print(f"Requested {fps_value} FPS is not advertised for {width} {fmt}.", file=sys.stderr)
                return 2
        selected_fps = int(fps) if fps != "0" else mode_max_fps(mode)
        print(json.dumps({
            "device": device["device"], "resolution": width, "fps": fps,
            "format": ustreamer_format(fmt),
            "encoder": encoder, "native_mjpeg": native,
            "mode_fps": mode["fps"],
        }))
        return 0
    # Runtime state is read from PetCam's own process inventory and camera marker.
    try:
        supervisor = json.loads(Path("/run/petcam/supervisor-status.json").read_text(encoding="utf-8"))
        managed = supervisor.get("workers", {})
        status = "active" if managed.get("camera-capture", {}).get("running") else "inactive"
    except (OSError, ValueError, TypeError):
        status = "unknown"
    try:
        marker = json.loads(Path("/var/lib/petcam/camera-status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        marker = {}
    log = ""
    fps_values = [str(marker["fps"])] if marker.get("fps") else []
    resolutions = [marker["resolution"]] if marker.get("resolution") else []
    formats = [marker["format"]] if marker.get("format") else []
    devices_in_log = [marker["device"]] if marker.get("device") else []
    start_config = [(marker.get("device", ""), marker.get("resolution", ""), marker.get("format", ""))] if marker.get("backend") == "usb" else []
    csi_start = [(str(marker.get("camera", "")), marker.get("resolution", ""), str(marker.get("fps", "")))] if marker.get("backend") == "csi" else []
    backend_values = [marker["backend"]] if marker.get("backend") else []
    try:
        port = int(parse_config()["PORT"])
    except Exception:
        port = 8081
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            http_status = response.status
    except Exception:
        http_status = None
    stream_state = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=2) as response:
            payload = json.loads(response.read().decode())
            if payload.get("ok") and isinstance(payload.get("result"), dict):
                stream_state = payload["result"]
    except Exception:
        pass
    csi_status = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as response:
            payload = json.loads(response.read().decode())
            if payload.get("backend") == "csi":
                csi_status = payload
    except Exception:
        pass

    def sample_stream_mbps():
        received = 0
        started = time.monotonic()
        header = b""
        body_started = False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
                stream.sendall(b"GET /stream HTTP/1.1\r\nHost: localhost\r\n\r\n")
                while time.monotonic() - started < 1.0:
                    stream.settimeout(min(0.2, max(0.05, 1.0 - (time.monotonic() - started))))
                    try:
                        chunk = stream.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    if not body_started:
                        header += chunk
                        separator = header.find(b"\r\n\r\n")
                        if separator >= 0:
                            if not header.startswith((b"HTTP/1.1 200", b"HTTP/1.0 200")):
                                return None
                            received += len(header) - separator - 4
                            body_started = True
                    else:
                        received += len(chunk)
        except OSError:
            return None
        elapsed = max(time.monotonic() - started, 0.001)
        return round(received * 8 / elapsed / 1_000_000, 3) if body_started else None

    def transmitted_bytes():
        total = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            fields = line.split()
            if len(fields) >= 10 and fields[0].rstrip(":") != "lo":
                total += int(fields[9])
        return total
    tx_before = transmitted_bytes()
    stream_mbps = sample_stream_mbps()
    tx_after = transmitted_bytes()
    temp = "unavailable"
    for path in ("/sys/class/thermal/thermal_zone0/temp",):
        try:
            temp = f"{int(Path(path).read_text().strip()) / 1000:.1f} C"
            break
        except (OSError, ValueError):
            pass
    try:
        health = json.loads(Path("/var/lib/petcam/health.json").read_text(encoding="utf-8"))
        if not isinstance(health, dict):
            health = {}
    except (OSError, ValueError):
        health = {}
    report = {
        "model": model,
        "health_state": health.get("state", "not_checked"),
        "health_reason": health.get("reason", "The periodic health monitor has not reported yet."),
        "health_recovery_count": health.get("recovery_count", 0),
        "health_last_checked_at": health.get("last_checked_at"),
        "health_last_recovery_at": health.get("last_recovery_at"),
        "connectivity": collect_diagnostics(),
        "service": status,
        "http_endpoint_reachable": http_status is not None,
        "http_status": http_status,
        "camera_devices_detected": len(devices) + len(discover_csi_cameras()),
        "usb_camera_devices_detected": len(devices),
        "csi_cameras_detected": len(discover_csi_cameras()),
        "active_backend": backend_values[-1] if backend_values else ("csi" if csi_start else ("usb" if start_config else None)),
        "active_camera_device": devices_in_log[-1] if devices_in_log else (start_config[-1][0] if start_config else (f"CSI camera {csi_start[-1][0]}" if csi_start else None)),
        "latest_captured_fps": (stream_state.get("source", {}).get("captured_fps") if stream_state else (int(fps_values[-1]) if fps_values else (csi_status.get("captured_fps_average") if csi_status else None))),
        "active_resolution": (str(stream_state["source"]["resolution"]["width"]) + "x" + str(stream_state["source"]["resolution"]["height"]) if stream_state and stream_state.get("source", {}).get("resolution") else (resolutions[-1] if resolutions else (start_config[-1][1] if start_config else (csi_start[-1][1] if csi_start else None)))),
        "active_capture_format": ("MJPEG" if stream_state and stream_state.get("encoder", {}).get("type") == "HW" else (formats[-1] if formats else ("MJPEG" if csi_start else (start_config[-1][2] if start_config else None)))),
        "csi_capture": csi_status,
        "network_transmitted_bytes_since_boot": tx_after,
        "network_interface_tx_mbps_sampled": round(max(0, tx_after - tx_before) * 8 / 1_000_000, 3),
        "local_mjpeg_stream_mbps_sampled": stream_mbps,
        "temperature": temp,
        "dropped_frames": None,
        "dropped_frames_note": "The active capture backend does not expose a reliable cumulative dropped-frame counter; not inferred.",
        "bitrate_note": "The MJPEG stream rate is sampled locally for one second; interface transmit rate includes all non-loopback traffic.",
    }
    try:
        marker = json.loads(Path("/var/lib/petcam/camera-status.json").read_text(encoding="utf-8"))
        marker_pid = int(marker.get("pid", 0))
        if marker.get("native_h264") is True and marker_pid > 1:
            os.kill(marker_pid, 0)
            report.update({
                "active_backend": marker.get("backend", report["active_backend"]),
                "active_capture_format": "H264",
                "active_resolution": marker.get("resolution", report["active_resolution"]),
                "active_camera_device": f"CSI camera {marker.get('camera')}" if marker.get("backend") == "csi" else marker.get("device"),
                "hardware_encoder": marker.get("encoder"),
                "capture_mode": "native_h264_csi" if marker.get("backend") == "csi" else "native_h264",
            })
    except (OSError, ValueError, TypeError, ProcessLookupError):
        pass
    print(json.dumps(report, indent=2))
    return 0 if status == "active" else 1


if __name__ == "__main__":
    sys.exit(main())
