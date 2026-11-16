"""Runtime status aggregation using the Python supervisor snapshot."""

import json
import time


def snapshot(status_file, supervisor_file="/run/petcam/supervisor-status.json", clock=time.time):
    try:
        with open(status_file, encoding="utf-8") as source:
            status = json.load(source)
    except (OSError, ValueError):
        status = {}
    try:
        with open(supervisor_file, encoding="utf-8") as source:
            supervisor = json.load(source)
        worker = supervisor.get("workers", {}).get("gstreamer-rtsp", {})
    except (OSError, ValueError, TypeError):
        worker = {}
    active_service = worker.get("running") is True
    updated_at = status.get("updated_at")
    fresh = isinstance(updated_at, (int, float)) and 0 <= clock() - updated_at <= 10
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
