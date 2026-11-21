#!/usr/bin/env python3
"""Detect stalled PetCam streams and recover only the affected service."""

from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..persistence.configuration import config_transaction_guard, parse_config
from . import processes as process_control

STATE_FILE = Path("/var/lib/petcam/health.json")
BACKEND_STREAM_URL = "http://127.0.0.1:8081/stream"
PUBLIC_STREAM_URL = "http://127.0.0.1:8080/stream"
CAMERA_STATUS_FILE = Path("/var/lib/petcam/camera-status.json")
RTSP_STATUS_FILE = Path("/run/petcam/g-streamer-status.json")
RTSP_STATUS_MAX_AGE_SECONDS = 45
WEB_CONFIG_FILE = Path("/etc/petcam/web-manager.json")


def backend_stream_url() -> str:
    try:
        return f"http://127.0.0.1:{parse_config()['PORT']}/stream"
    except Exception:
        return BACKEND_STREAM_URL
STARTUP_GRACE_SECONDS = 30
BACKEND_FRAME_TIMEOUT_SECONDS = 15
PUBLIC_FRAME_TIMEOUT_SECONDS = 5
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 300


def timestamp(now: float | None = None) -> str:
    return datetime.fromtimestamp(now if now is not None else time.time(), timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_FILE)


def web_ui_enabled() -> bool:
    """Read the explicit manager setting; the camera/RTSP core must not depend on it."""
    try:
        config = json.loads(WEB_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and config.get("enabled") is True


def service_snapshot(service: str) -> dict[str, Any]:
    """Read lifecycle state from the supervisor process inventory."""
    workers = {
        "camera-capture": "camera-capture",
        "gstreamer-rtsp": "gstreamer-rtsp",
        "web-ui": "web-ui",
    }
    worker_name = workers.get(service)
    if worker_name is None:
        return {"state": "unknown", "active_age": None}
    try:
        snapshot = process_control.worker_snapshot(worker_name)
    except process_control.SupervisorUnavailable:
        return {"state": "unknown", "active_age": None}
    running = snapshot.get("running") is True
    started_at = snapshot.get("started_at")
    age = max(0.0, time.monotonic() - float(started_at)) if running and started_at else None
    return {"state": "active" if running else "inactive", "active_age": age}


def probe_stream(url: str, timeout: int) -> bool:
    """Require an actual first MJPEG body byte, not merely an open TCP socket."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            return bool(response.read(1))
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, http.client.HTTPException):
        return False



def native_h264_capture_active() -> bool:
    """Return true while the marked camera-mode supervisor process is alive."""
    try:
        marker = json.loads(CAMERA_STATUS_FILE.read_text(encoding="utf-8"))
        pid = int(marker.get("pid", 0))
        if marker.get("native_h264") is not True or pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def rtsp_service_ready(now: float | None = None) -> bool:
    """Require a fresh GStreamer heartbeat; idle-ready is healthy without clients."""
    now = time.time() if now is None else now
    try:
        status = json.loads(RTSP_STATUS_FILE.read_text(encoding="utf-8"))
        age = now - float(status.get("updated_at", 0))
        return (
            status.get("source") in ("native_h264", "native_h264_csi", "mjpeg_copy")
            and status.get("state") in ("ready", "publishing")
            and 0 <= age <= RTSP_STATUS_MAX_AGE_SECONDS
        )
    except (OSError, ValueError, TypeError):
        return False


def camera_present() -> bool | None:
    """Return None when discovery failed; do not mistake a failed probe for no camera."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "petcam.infrastructure.camera.cli", "discover"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            return None
        inventory = json.loads(result.stdout)
        return bool(inventory.get("usb_devices") or inventory.get("csi_cameras"))
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
        return None


def restart_service(service: str) -> tuple[bool, str]:
    workers = {
        "web-ui": "web-ui",
        "camera-capture": "camera-capture",
        "gstreamer-rtsp": "gstreamer-rtsp",
    }
    worker = workers.get(service)
    if worker is None:
        return False, f"Refusing to restart unsupported PetCam worker: {service}"
    try:
        process_control.restart_worker(worker)
        return True, ""
    except process_control.SupervisorUnavailable as error:
        return False, str(error)


def _persist(report: dict[str, Any]) -> dict[str, Any]:
    save_state(report)
    return report


def _starting(snapshot: dict[str, Any]) -> bool:
    return snapshot["state"] in ("activating", "reloading", "deactivating") or (
        snapshot["state"] == "active"
        and snapshot["active_age"] is not None
        and snapshot["active_age"] < STARTUP_GRACE_SECONDS
    )


def _recover(report: dict[str, Any], previous: dict[str, Any], service: str,
             reason: str, now: float) -> dict[str, Any]:
    failures = int(previous.get("consecutive_failures", 0)) + 1
    delay = min(BACKOFF_BASE_SECONDS * (2 ** min(failures - 1, 4)), BACKOFF_MAX_SECONDS)
    next_allowed = float(previous.get("next_recovery_at", 0))
    report["consecutive_failures"] = failures
    report["recovery_target"] = service
    report["reason"] = reason
    if now < next_allowed:
        report["state"] = "recovery_backoff"
        report["next_recovery_at"] = next_allowed
        return _persist(report)

    report["recovery_count"] = int(previous.get("recovery_count", 0)) + 1
    report["last_recovery_at"] = timestamp(now)
    report["next_recovery_at"] = now + delay
    report["last_recovery_result"] = "requested"
    report["state"] = "recovering"
    _persist(report)
    succeeded, error = restart_service(service)
    report["last_recovery_result"] = "requested" if succeeded else error
    report["state"] = "recovering" if succeeded else "recovery_failed"
    return _persist(report)


def _check_health_locked(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    previous = load_state()
    report: dict[str, Any] = {
        "state": "starting",
        "reason": "",
        "last_checked_at": timestamp(now),
        "last_healthy_at": previous.get("last_healthy_at"),
        "last_recovery_at": previous.get("last_recovery_at"),
        "next_recovery_at": previous.get("next_recovery_at", 0),
        "recovery_count": int(previous.get("recovery_count", 0)),
        "consecutive_failures": int(previous.get("consecutive_failures", 0)),
        "recovery_target": previous.get("recovery_target"),
        "last_recovery_result": previous.get("last_recovery_result"),
    }

    web_enabled = web_ui_enabled()
    backend = service_snapshot("camera-capture")
    rtsp = service_snapshot("gstreamer-rtsp")
    web = service_snapshot("web-ui") if web_enabled else {"state": "disabled", "active_age": None}
    report["backend_service_state"] = backend["state"]
    report["rtsp_service_state"] = rtsp["state"]
    report["web_service_state"] = web["state"]
    report["backend_stream_ready"] = False
    report["public_stream_ready"] = False
    report["camera_connected"] = None

    required_services = (backend, rtsp, web) if web_enabled else (backend, rtsp)
    if any(snapshot["state"] == "unknown" for snapshot in required_services):
        report["state"] = "service_state_unknown"
        report["reason"] = "supervisor process state could not be read; no restart was attempted."
        return _persist(report)
    if any(_starting(snapshot) for snapshot in required_services):
        report["state"] = "starting"
        report["reason"] = "A PetCam service is within its startup grace period."
        return _persist(report)

    configured_format = ""
    try:
        configured_format = parse_config().get("FORMAT", "")
    except Exception:
        pass
    h264_mode = configured_format == "H264" or native_h264_capture_active()
    report["capture_mode"] = "native_h264" if h264_mode else "mjpeg"
    report["rtsp_output_ready"] = False
    if h264_mode:
        backend_ready = backend["state"] == "active" and native_h264_capture_active()
    else:
        backend_ready = backend["state"] == "active" and probe_stream(
            backend_stream_url(), BACKEND_FRAME_TIMEOUT_SECONDS
        )
    report["backend_stream_ready"] = backend_ready
    if not backend_ready:
        present = camera_present()
        report["camera_connected"] = present
        if present is False:
            report["state"] = "camera_disconnected"
            report["reason"] = "No supported USB or CSI camera is currently detected; waiting for hardware."
            return _persist(report)
        if present is None:
            report["state"] = "camera_detection_failed"
            report["reason"] = "Camera discovery failed; no service restart was attempted."
            return _persist(report)
        reason = (
            "Capture service is not active."
            if backend["state"] != "active"
            else "Capture service is active but the local MJPEG stream produced no frame."
        )
        return _recover(report, previous, "camera-capture", reason, now)

    rtsp_ready = rtsp["state"] == "active" and rtsp_service_ready(now)
    report["rtsp_output_ready"] = rtsp_ready
    if not rtsp_ready:
        reason = (
            "GStreamer RTSP service is not active."
            if rtsp["state"] != "active"
            else "GStreamer RTSP service is active but its heartbeat is missing or stale."
        )
        return _recover(
            report, previous, "gstreamer-rtsp", reason, now,
        )

    if web_enabled and web["state"] != "active":
        return _recover(
            report, previous, "web-ui",
            "The web manager process is not active while the local capture stream is healthy.", now,
        )

    if h264_mode or not web_enabled:
        # Native H.264 and an intentionally disabled manager have no HTTP MJPEG proxy.
        report["public_stream_ready"] = None
    else:
        public_ready = probe_stream(PUBLIC_STREAM_URL, PUBLIC_FRAME_TIMEOUT_SECONDS)
        report["public_stream_ready"] = public_ready
        if not public_ready:
            return _recover(
                report, previous, "web-ui",
                "The local capture stream is healthy but the public OBS stream proxy is not producing frames.", now,
            )

    report["state"] = "healthy"
    report["reason"] = ""
    report["last_healthy_at"] = timestamp(now)
    report["consecutive_failures"] = 0
    report["next_recovery_at"] = 0
    report["recovery_target"] = None
    report["last_recovery_result"] = None
    return _persist(report)


def check_health(now: float | None = None) -> dict[str, Any]:
    """Run health detection without racing a camera configuration apply."""
    with config_transaction_guard() as acquired:
        if not acquired:
            current = time.time() if now is None else now
            previous = load_state()
            return _persist({
                "state": "configuring",
                "reason": "A camera configuration transaction is in progress; health recovery is paused.",
                "last_checked_at": timestamp(current),
                "last_healthy_at": previous.get("last_healthy_at"),
                "last_recovery_at": previous.get("last_recovery_at"),
                "next_recovery_at": previous.get("next_recovery_at", 0),
                "recovery_count": int(previous.get("recovery_count", 0)),
                "consecutive_failures": int(previous.get("consecutive_failures", 0)),
                "recovery_target": previous.get("recovery_target"),
                "last_recovery_result": previous.get("last_recovery_result"),
            })
        return _check_health_locked(now)


def main() -> int:
    report = check_health()
    print(json.dumps(report, indent=2))
    return 0 if report["state"] in ("healthy", "starting", "camera_disconnected") else 1


if __name__ == "__main__":
    raise SystemExit(main())
