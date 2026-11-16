"""Runtime status aggregation for the always-on GStreamer RTSP service."""

import json
import subprocess
import time

from petcam.domain.streaming.status import status_snapshot


def snapshot(status_file, run=subprocess.run, clock=time.time):
    try:
        active_service = run(
            ["systemctl", "is-active", "--quiet", "petcam-g-streamer-rtsp.service"],
            check=False, timeout=1,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        active_service = False
    try:
        with open(status_file, encoding="utf-8") as source:
            status = json.load(source)
    except (OSError, ValueError):
        status = {}
    return status_snapshot(active_service, status, clock())
