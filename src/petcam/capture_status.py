"""Capture-backend status aggregation for the manager API."""

import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


def live_status(config_path, parse_config, urlopen=urllib.request.urlopen, kill=os.kill):
    """Read capture metrics directly from the active stream backend."""
    try:
        config = parse_config(config_path)
        port = int(config["PORT"])
    except Exception:
        config = {}
        port = 8081

    try:
        marker = json.loads(Path("/var/lib/petcam/camera-status.json").read_text(encoding="utf-8"))
        pid = int(marker.get("pid", 0))
        if marker.get("native_h264") is True and pid > 1:
            kill(pid, 0)
            result = {
                "active_capture_format": "H264",
                "active_resolution": marker.get("resolution") or config.get("RESOLUTION"),
                "configured_fps": marker.get("fps") or config.get("FPS"),
                "capture_mode": "native_h264_csi" if marker.get("backend") == "csi" else "native_h264",
                "hardware_encoder": marker.get("encoder"),
            }
            try:
                status = json.loads(Path("/run/petcam/rtmp-status.json").read_text(encoding="utf-8"))
                if status.get("source") in ("native_h264", "native_h264_csi"):
                    result["latest_captured_fps"] = status.get("fps")
                    result["rtsp_output_ready"] = status.get("active") is True and status.get("state") == "publishing"
            except (OSError, ValueError, TypeError):
                pass
            return result
    except (OSError, ValueError, TypeError, ProcessLookupError):
        pass

    try:
        with urlopen(f"http://127.0.0.1:{port}/state", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        state = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(state, dict):
            source = state.get("source") or {}
            resolution = source.get("resolution") or {}
            result = {
                "latest_captured_fps": source.get("captured_fps"),
                "active_resolution": (
                    f"{resolution['width']}x{resolution['height']}"
                    if resolution.get("width") and resolution.get("height") else None
                ),
                "active_capture_format": (
                    "MJPEG" if (state.get("encoder") or {}).get("type") == "HW" else None
                ),
            }
            if config.get("FPS") is not None:
                result["configured_fps"] = config["FPS"]
            return result
    except (OSError, urllib.error.URLError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError, AttributeError):
        pass

    try:
        with urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("backend") == "csi":
            result = {
                "latest_captured_fps": payload.get("captured_fps_average"),
                "active_resolution": config.get("RESOLUTION"),
                "active_capture_format": "MJPEG",
            }
            if config.get("FPS") is not None:
                result["configured_fps"] = config["FPS"]
            for key in ("frames_received", "last_frame_age_seconds", "capture_process_running"):
                if key in payload:
                    result[key] = payload[key]
            if payload.get("error"):
                result["capture_error"] = payload["error"]
            return result
    except (OSError, urllib.error.URLError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass
    return {}
