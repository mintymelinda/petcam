"""Select and run one supported USB or CSI camera capture backend."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..persistence.configuration import parse_config

STATE = Path(os.environ.get("PETCAM_STATE", "/var/lib/petcam"))
CONFIG = Path(os.environ.get("PETCAM_CONFIG", "/etc/petcam/petcam.conf"))
CAMERA_STATUS = STATE / "camera-status.json"
CAMERA_CLI = "petcam.infrastructure.camera.cli"
CSI_MODULE = "petcam.infrastructure.camera.csi"


def _run_selection(command: str, config: dict, *, source: str) -> dict:
    args = [sys.executable, "-m", CAMERA_CLI, command]
    if config.get("RESOLUTION"):
        args += ["--resolution", str(config["RESOLUTION"])]
    if config.get("FPS"):
        args += ["--fps", str(config["FPS"])]
    if source == "usb":
        if config.get("DEVICE"):
            args += ["--device", str(config["DEVICE"])]
        if config.get("USB_PHYSICAL_PATH"):
            args += ["--physical-path", str(config["USB_PHYSICAL_PATH"])]
        if command == "select":
            args += ["--format", str(config.get("FORMAT", "auto"))]
    else:
        if config.get("CAMERA") not in (None, "", "auto"):
            args += ["--camera", str(config["CAMERA"])]
        if config.get("CSI_DEVICE_PATH"):
            args += ["--device-path", str(config["CSI_DEVICE_PATH"])]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Camera {source} selection failed")
    try:
        selected = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError("Camera selection returned invalid JSON") from error
    if not isinstance(selected, dict):
        raise RuntimeError("Camera selection returned an invalid result")
    return selected


def select_backend(config: dict) -> tuple[str, dict]:
    requested = str(config.get("SOURCE", "auto")).lower()
    if requested not in {"auto", "usb", "csi"}:
        raise ValueError(f"Unsupported camera source: {requested}")
    discovery = subprocess.run(
        [sys.executable, "-m", CAMERA_CLI, "discover"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if discovery.returncode:
        raise RuntimeError(discovery.stderr.strip() or "Camera discovery failed")
    inventory = json.loads(discovery.stdout)
    candidates = ("usb", "csi") if requested == "auto" else (requested,)
    failures = []
    for source in candidates:
        available = inventory.get("usb_devices") if source == "usb" else inventory.get("csi_cameras")
        if not available:
            continue
        if source == "usb":
            requested_format = str(config.get("FORMAT", "auto")).upper()
            commands = ("select",)
            for command in commands:
                try:
                    return source, _run_selection(command, config, source=source)
                except (RuntimeError, ValueError) as error:
                    failures.append(str(error))
        else:
            try:
                selected = _run_selection("select-csi", config, source=source)
                requested_format = str(config.get("FORMAT", "auto")).upper()
                if requested_format not in {"AUTO", "H264", "MJPG", "MJPEG", "JPEG"}:
                    raise RuntimeError(
                        f"CSI capture does not support the explicitly requested format {requested_format}"
                    )
                selected["_native_h264"] = False
                if requested_format in {"AUTO", "H264"}:
                    probe = subprocess.run(
                        [sys.executable, "-m", CAMERA_CLI, "h264-encoder"],
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    try:
                        encoder = json.loads(probe.stdout)
                    except (TypeError, ValueError):
                        encoder = {}
                    if probe.returncode == 0 and encoder.get("available") is True:
                        selected["_native_h264"] = True
                    elif requested_format == "H264":
                        raise RuntimeError("CSI native H.264 encoding was requested but no hardware encoder is available")
                return source, selected
            except (RuntimeError, ValueError) as error:
                failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(failures))
    raise RuntimeError("No supported USB or CSI camera is currently available")


def _write_marker(payload: dict) -> None:
    CAMERA_STATUS.parent.mkdir(parents=True, exist_ok=True)
    temporary = CAMERA_STATUS.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, CAMERA_STATUS)


def _remove_marker() -> None:
    try:
        current = json.loads(CAMERA_STATUS.read_text(encoding="utf-8"))
        if current.get("pid") == os.getpid():
            CAMERA_STATUS.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def run_capture(config: dict) -> int:
    source, selected = select_backend(config)
    resolution = str(selected["resolution"])
    fps = str(selected["fps"])
    native_h264 = (
        bool(selected.get("_native_h264"))
        if source == "csi"
        else str(selected.get("format", "")).upper() == "H264"
    )
    if source == "usb":
        marker = {
            "pid": os.getpid(), "backend": "usb", "device": selected["device"],
            "resolution": resolution, "fps": fps, "format": "H264" if native_h264 else "MJPEG",
            "native_h264": native_h264,
        }
        _write_marker(marker)
        if native_h264:
            logging.info("USB camera %s exposes native H.264 at %s %s FPS", selected["device"], resolution, fps)
            stopping = [False]
            def stop_native(_signum, _frame):
                stopping[0] = True
            signal.signal(signal.SIGTERM, stop_native)
            signal.signal(signal.SIGINT, stop_native)
            try:
                while not stopping[0]:
                    signal.pause()
            finally:
                _remove_marker()
            return 0
        command = [
            "ustreamer", "--device", selected["device"], "--host", "127.0.0.1",
            "--port", "8081", "--format", selected["format"],
            "--resolution", resolution, "--desired-fps", fps,
        ]
    else:
        command = [
            sys.executable, "-m", CSI_MODULE, "--camera", str(selected["camera"]),
            "--resolution", resolution, "--fps", fps, "--port", "8081",
        ]
        if native_h264:
            command.append("--h264")
        # The supervisor gates RTSP startup on this PID marker for every CSI
        # mode, including native H.264 capture.
        _write_marker({
            "pid": os.getpid(), "backend": "csi", "camera": selected["camera"],
            "resolution": resolution, "fps": fps,
            "format": "H264" if native_h264 else "MJPEG",
            "native_h264": native_h264,
        })
    child = None
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
        if child and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        logging.info("Starting %s camera capture at %s %s FPS", source, resolution, fps)
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
        while not stopping:
            code = child.poll()
            if code is not None:
                return code
            time.sleep(0.5)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
        return 0
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        _remove_marker()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = parse_config(CONFIG, check_hardware=False)
    return run_capture(config)


if __name__ == "__main__":
    raise SystemExit(main())
