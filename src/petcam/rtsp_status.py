"""Runtime status aggregation for the OBS RTSP output service."""

import json
import subprocess
import time


def snapshot(load_config, status_file, run=subprocess.run, clock=time.time):
    config = load_config()
    try:
        active_service = run(
            ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
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
    if active_service and updated_at is not None and not fresh:
        state = "stalled"
    return {
        "enabled": config["enabled"],
        "active": active_service and state == "publishing",
        "state": state,
        "fps": status.get("fps") if fresh else None,
        "updated_at": updated_at,
        "source": status.get("source") if fresh else None,
    }
