"""Runtime status aggregation for the always-on GStreamer RTSP service."""

import json
import subprocess
import time


def snapshot(status_file, run=subprocess.run, clock=time.time):
    try:
        active_service = run(
            ["systemctl", "is-active", "--quiet", "petcam-g-streamer-rtsp.service"],
            check=False, timeout=1,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        active_service = False
    status = {}
    try:
        with open(status_file, encoding="utf-8") as source:
            status = json.load(source)
    except (OSError, ValueError):
        pass
    updated_at = status.get("updated_at")
    fresh = isinstance(updated_at, (int, float)) and clock() - updated_at <= 10
    state = status.get("state", "starting") if active_service else "stopped"
    if active_service and not fresh:
        state = "stalled"
    return {
        "service_active": active_service,
        "active": active_service and state == "publishing",
        "state": state,
        "fps": status.get("fps") if fresh else None,
        "updated_at": updated_at,
        "source": status.get("source") if fresh else None,
    }
