#!/usr/bin/env python3
"""Configure a camera and serve its native H.264 stream over RTSP."""

from __future__ import annotations

import argparse
import curses
import json
import logging
import math
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from .configuration import ConfigurationError, validate_config
from .domain.camera.capabilities import mode_fps_values
from .infrastructure.camera.discovery import (
    detect_hardware_h264_encoder,
    discover_csi_cameras,
    discover_usb_cameras,
)
from .infrastructure.system.metrics import ResourceMetrics

RUN_DIR = Path(os.environ.get("PETCAM_RUN", f"/tmp/petcam-{os.getuid()}"))
CAMERA_STATUS = RUN_DIR / "camera-status.json"
STREAM_STATUS = RUN_DIR / "stream-status.json"
RTSP_PORT = 8554
RTSP_PATH = "/petcam"
HOTPLUG = object()


def parse_short_config(value: str) -> tuple[str, str, float]:
    """Parse the documented SOURCE;WIDTHxHEIGHT;FPS shortcut syntax."""
    parts = value.split(";")
    if len(parts) != 3:
        raise ConfigurationError('Use -c "USB;1920x1080;30" or -c "CSI;1920x1080;30".')
    source, resolution, raw_fps = (part.strip() for part in parts)
    source = source.upper()
    if source not in {"USB", "CSI"}:
        raise ConfigurationError("Capture mode in -c must be USB or CSI.")
    if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", resolution):
        raise ConfigurationError("Resolution in -c must use WIDTHxHEIGHT format.")
    try:
        fps = float(raw_fps)
    except ValueError as error:
        raise ConfigurationError("Frame rate in -c must be a positive number.") from error
    if not math.isfinite(fps) or not 0 < fps <= 1000:
        raise ConfigurationError("Frame rate must be greater than 0 and no more than 1000 FPS.")
    return source, resolution, fps


def discover_cameras(source: str) -> list[dict]:
    if source == "USB":
        return discover_usb_cameras()
    if source == "CSI":
        return discover_csi_cameras()
    raise ValueError("Capture mode must be USB or CSI.")


def camera_modes(source: str, camera: dict) -> list[dict]:
    """Return only H.264 modes available to the selected camera and encoder."""
    options: dict[tuple[str, float], dict] = {}
    if source == "USB":
        for mode in camera.get("modes", []):
            if str(mode.get("format", "")).upper() != "H264":
                continue
            for fps in mode_fps_values(mode):
                key = (f'{mode["width"]}x{mode["height"]}', fps)
                options[key] = {"resolution": key[0], "fps": fps, "format": "H264"}
    else:
        if not detect_hardware_h264_encoder().get("available"):
            return []
        for mode in camera.get("modes", []):
            try:
                width, height, fps = int(mode["width"]), int(mode["height"]), float(mode["fps"])
            except (KeyError, TypeError, ValueError):
                continue
            if width > 0 and height > 0 and fps > 0:
                key = (f"{width}x{height}", fps)
                options[key] = {"resolution": key[0], "fps": fps, "format": "H264"}
    return sorted(options.values(), key=lambda item: (-int(item["resolution"].split("x")[0]), -item["fps"]))


def _camera_label(source: str, camera: dict) -> str:
    if source == "USB":
        return f'{camera.get("label") or "USB camera"} ({camera.get("device", "unknown device")})'
    return f'{camera.get("sensor", "CSI camera")} (camera {camera.get("index", "?")})'


def _camera_identity(source: str, camera: dict) -> tuple:
    if source == "USB":
        return (camera.get("device"), camera.get("physical_path"))
    return (camera.get("index"), camera.get("sensor"), camera.get("device_path"))


def inventory_signature(source: str, cameras: list[dict]) -> str:
    """Include camera identities and advertised modes to detect live list changes."""
    normalized = []
    for camera in cameras:
        normalized.append({
            "identity": _camera_identity(source, camera),
            "modes": camera.get("modes", []),
        })
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def resolve_shortcut(value: str) -> dict:
    source, resolution, fps = parse_short_config(value)
    cameras = discover_cameras(source)
    if source == "CSI" and not detect_hardware_h264_encoder().get("available"):
        raise ConfigurationError(
            "No hardware H.264 encoder was detected. CSI capture will not use software encoding."
        )
    for camera in cameras:
        matching = [
            mode for mode in camera_modes(source, camera)
            if mode["resolution"] == resolution and abs(float(mode["fps"]) - fps) < 0.1
        ]
        if not matching:
            continue
        if source == "USB":
            return validate_config({
                "source": source,
                "device": camera["device"],
                "physical_path": camera.get("physical_path", ""),
                "resolution": resolution,
                "fps": fps,
            })
        return validate_config({
            "source": source,
            "camera": camera["index"],
            "sensor": camera.get("sensor", ""),
            "device_path": camera.get("device_path", ""),
            "resolution": resolution,
            "fps": fps,
        })
    raise ConfigurationError(
        f"No {source} camera currently advertises H.264 at {resolution} and {fps:g} FPS. "
        "Choose another camera or advertised mode."
    )


def _draw_frame(stdscr, title: str, subtitle: str, items: list[str], selected: int) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    stdscr.addnstr(0, 0, "PetCam · H.264 RTSP", max(1, width - 1), curses.A_BOLD)
    stdscr.addnstr(2, 0, title, max(1, width - 1), curses.A_BOLD)
    if subtitle:
        stdscr.addnstr(3, 0, subtitle, max(1, width - 1))
    visible_rows = max(1, height - 7)
    first_visible = min(max(0, selected - visible_rows + 1), max(0, len(items) - visible_rows))
    for offset, item in enumerate(items[first_visible:first_visible + visible_rows]):
        index = first_visible + offset
        row = 5 + offset
        attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
        prefix = "> " if index == selected else "  "
        stdscr.addnstr(row, 0, prefix + item, max(1, width - 1), attr)
    footer = "↑/↓ Select   Enter Confirm   Esc Back"
    stdscr.addnstr(max(0, height - 1), 0, footer, max(1, width - 1), curses.A_DIM)
    stdscr.refresh()


def select_menu(
    stdscr,
    title: str,
    subtitle: str,
    items: list[str],
    *,
    refresh_signature=None,
):
    if not items:
        return None
    selected = 0
    stdscr.timeout(400)
    last_refresh = time.monotonic()
    initial_signature = refresh_signature() if refresh_signature is not None else None
    while True:
        _draw_frame(stdscr, title, subtitle, items, selected)
        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(items)
        elif key in (10, 13, curses.KEY_ENTER):
            return selected
        elif key == 27:
            return None
        if refresh_signature is not None and time.monotonic() - last_refresh >= 1.0:
            last_refresh = time.monotonic()
            try:
                current_signature = refresh_signature()
            except Exception:
                current_signature = "discovery-error"
            if current_signature != initial_signature:
                return HOTPLUG


def wait_for_enter(stdscr, title: str, message: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.timeout(-1)
    stdscr.erase()
    stdscr.addnstr(0, 0, "PetCam · H.264 RTSP", max(1, width - 1), curses.A_BOLD)
    stdscr.addnstr(2, 0, title, max(1, width - 1), curses.A_BOLD)
    for index, line in enumerate(message.splitlines()):
        if index + 4 < height - 1:
            stdscr.addnstr(index + 4, 0, line, max(1, width - 1))
    stdscr.addnstr(height - 1, 0, "Press Enter to continue", max(1, width - 1), curses.A_DIM)
    stdscr.refresh()
    while stdscr.getch() not in (10, 13, curses.KEY_ENTER):
        pass


def guided_configuration(stdscr) -> dict:
    while True:
        source_index = select_menu(
            stdscr,
            "Step 1 · Choose capture mode",
            "Select the camera connection type.",
            ["USB", "CSI"],
        )
        if source_index is None:
            raise KeyboardInterrupt
        source = "USB" if source_index == 0 else "CSI"

        while True:
            cameras = discover_cameras(source)
            if not cameras:
                wait_for_enter(
                    stdscr,
                    "No cameras found",
                    f"No {source} cameras are currently available.\nConnect a camera and try again.",
                )
                break

            camera_index = select_menu(
                stdscr,
                f"Step 2 · Select {source} camera",
                "Highlight the camera and press Enter.",
                [_camera_label(source, camera) for camera in cameras],
            )
            if camera_index is None:
                break
            camera = cameras[camera_index]
            modes = camera_modes(source, camera)
            if not modes:
                reason = (
                    "No hardware H.264 encoder was detected for CSI capture."
                    if source == "CSI" and not detect_hardware_h264_encoder().get("available")
                    else "This camera does not advertise any H.264 modes. Try a different camera."
                )
                wait_for_enter(stdscr, "No H.264 modes available", reason)
                continue

            def current_camera_signature():
                refreshed = discover_cameras(source)
                return inventory_signature(source, refreshed)

            mode_labels = [f'{mode["resolution"]}  ·  {mode["fps"]:g} FPS  ·  H.264' for mode in modes]
            mode_index = select_menu(
                stdscr,
                "Step 3 · Select H.264 mode",
                "Only resolution and frame-rate combinations reported by the camera are shown.",
                mode_labels,
                refresh_signature=current_camera_signature,
            )
            if mode_index is HOTPLUG:
                wait_for_enter(
                    stdscr,
                    "Camera list changed",
                    "The camera inventory changed while these modes were displayed.\n"
                    "The mode information may be outdated. Press Enter to return to camera selection.",
                )
                continue
            if mode_index is None:
                continue

            # Check once more before confirmation so a change immediately before Enter
            # cannot cause an obsolete camera/mode pair to be activated.
            if current_camera_signature() != inventory_signature(source, cameras):
                wait_for_enter(
                    stdscr,
                    "Camera list changed",
                    "The camera inventory changed. The displayed mode may be outdated.\n"
                    "Press Enter to return to camera selection.",
                )
                continue

            mode = modes[mode_index]
            confirm_index = select_menu(
                stdscr,
                "Step 4 · Confirm stream",
                f"{_camera_label(source, camera)}\n{mode['resolution']} at {mode['fps']:g} FPS · H.264",
                ["Activate RTSP stream", "Return to capture mode selection"],
            )
            if confirm_index == 0:
                if source == "USB":
                    return validate_config({
                        "source": source,
                        "device": camera["device"],
                        "physical_path": camera.get("physical_path", ""),
                        "resolution": mode["resolution"],
                        "fps": mode["fps"],
                    })
                return validate_config({
                    "source": source,
                    "camera": camera["index"],
                    "sensor": camera.get("sensor", ""),
                    "device_path": camera.get("device_path", ""),
                    "resolution": mode["resolution"],
                    "fps": mode["fps"],
                })
            # Confirm's second option or Esc returns to Step 1.
            break


def _read_status() -> dict:
    try:
        payload = json.loads(STREAM_STATUS.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run_stream(config: dict, stdscr) -> int:
    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    CAMERA_STATUS.unlink(missing_ok=True)
    STREAM_STATUS.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["PETCAM_RUN"] = str(RUN_DIR)
    capture_process = None
    gstreamer_process = None
    camera_marker_owned = False

    try:
        if config["source"] == "CSI":
            capture_command = [
                sys.executable, "-m", "petcam.infrastructure.camera.csi",
                "--camera", str(config["camera"]),
                "--resolution", config["resolution"],
                "--fps", str(config["fps"]),
            ]
            capture_process = subprocess.Popen(capture_command, env=environment)
            marker_deadline = time.monotonic() + 20
            while time.monotonic() < marker_deadline:
                if capture_process.poll() is not None:
                    raise RuntimeError("CSI H.264 capture exited before it could start.")
                try:
                    marker = json.loads(CAMERA_STATUS.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    marker = {}
                if marker.get("pid") == capture_process.pid and marker.get("native_h264") is True:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("CSI H.264 capture did not publish its hardware-encoder status.")
        else:
            marker = {
                "pid": os.getpid(),
                "backend": "usb",
                "device": config["device"],
                "physical_path": config.get("physical_path", ""),
                "resolution": config["resolution"],
                "fps": config["fps"],
                "native_h264": True,
            }
            temporary = CAMERA_STATUS.with_name(CAMERA_STATUS.name + ".tmp")
            temporary.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            os.replace(temporary, CAMERA_STATUS)
            camera_marker_owned = True

        gstreamer_process = subprocess.Popen(
            [sys.executable, "-m", "petcam.infrastructure.streaming.gstreamer"],
            env=environment,
        )
        start_deadline = time.monotonic() + 20
        while time.monotonic() < start_deadline:
            if gstreamer_process.poll() is not None:
                raise RuntimeError("The H.264 RTSP server exited during startup.")
            status = _read_status()
            if status.get("state") in {"ready", "publishing"}:
                break
            if status.get("state") == "error":
                raise RuntimeError(status.get("message") or "The H.264 RTSP server failed.")
            time.sleep(0.2)
        else:
            raise RuntimeError("The H.264 RTSP server did not become ready.")

        url = f"rtsp://{socket.getfqdn()}:{RTSP_PORT}{RTSP_PATH}"
        metrics = ResourceMetrics()
        stdscr.timeout(1000)
        while True:
            if gstreamer_process.poll() is not None:
                raise RuntimeError("The H.264 RTSP server stopped unexpectedly.")
            if capture_process is not None and capture_process.poll() is not None:
                raise RuntimeError("CSI H.264 capture stopped unexpectedly.")
            status = _read_status()
            resources = metrics.sample()
            height, width = stdscr.getmaxyx()
            stdscr.erase()
            stdscr.addnstr(0, 0, "PetCam · H.264 RTSP", max(1, width - 1), curses.A_BOLD)
            stdscr.addnstr(2, 0, "RTSP URL", max(1, width - 1), curses.A_BOLD)
            stdscr.addnstr(3, 0, url, max(1, width - 1))
            stdscr.addnstr(5, 0, "STREAM STATUS", max(1, width - 1), curses.A_BOLD)
            stdscr.addnstr(6, 0, f"RTSP: {status.get('state', 'starting').upper()}", max(1, width - 1))
            fps = status.get("streamed_fps")
            fps_text = f"{float(fps):.1f} FPS" if isinstance(fps, (int, float)) else "Waiting for RTSP client"
            stdscr.addnstr(7, 0, f"Streamed frame rate: {fps_text}", max(1, width - 1))
            stdscr.addnstr(8, 0, f"Capture mode: {config['source']} · {config['resolution']} · {config['fps']} FPS · H.264", max(1, width - 1))
            stdscr.addnstr(10, 0, "SYSTEM RESOURCES", max(1, width - 1), curses.A_BOLD)
            cpu = resources["cpu_percent"]
            cpu_text = f"{cpu:.1f}%" if isinstance(cpu, (int, float)) else "Sampling…"
            used, total = resources["memory_used_mb"], resources["memory_total_mb"]
            memory_text = f"{used} / {total} MB" if used is not None and total is not None else "Unavailable"
            stdscr.addnstr(11, 0, f"CPU: {cpu_text}", max(1, width - 1))
            stdscr.addnstr(12, 0, f"Memory: {memory_text}", max(1, width - 1))
            stdscr.addnstr(max(0, height - 1), 0, "Press q to stop the RTSP stream", max(1, width - 1), curses.A_DIM)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                return 0
    finally:
        _terminate(gstreamer_process)
        _terminate(capture_process)
        if camera_marker_owned:
            try:
                marker = json.loads(CAMERA_STATUS.read_text(encoding="utf-8"))
                if marker.get("pid") == os.getpid():
                    CAMERA_STATUS.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        STREAM_STATUS.unlink(missing_ok=True)


def _terminal_main(stdscr, config: dict | None) -> int:
    curses.curs_set(0)
    selected = config if config is not None else guided_configuration(stdscr)
    return run_stream(selected, stdscr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="petcam",
        description="Configure a USB or CSI camera and serve its native H.264 stream over RTSP.",
        epilog=(
            'Examples:\n'
            '  petcam\n'
            '  petcam -c "USB;1920x1080;30"\n'
            '  petcam -c "USB;1280x720;30"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c", metavar="SOURCE;RESOLUTION;FPS", dest="shortcut",
        help="skip the guided setup (for example: -c \"USB;1920x1080;30\")",
    )
    args = parser.parse_args(argv)

    try:
        config = resolve_shortcut(args.shortcut) if args.shortcut else None
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("The PetCam configuration and status interface requires an interactive SSH terminal.")
        return curses.wrapper(_terminal_main, config)
    except (ConfigurationError, RuntimeError, OSError) as error:
        print(f"petcam: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
