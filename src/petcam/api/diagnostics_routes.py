"""Diagnostics, support-bundle, and runtime-status routes."""

import json
import re
import time


def handle_get(handler, services, path):
    if path.startswith("/api/motion/events/"):
        filename = path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z(?:-[0-9]{3})?\.jpg", filename):
            handler.send_error(404)
            return True
        try:
            payload = (services.MOTION_FRAMES / filename).read_bytes()
        except OSError:
            handler.send_error(404)
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "private, no-store")
        handler.end_headers()
        handler.wfile.write(payload)
        return True

    if path == "/api/diagnostics":
        try:
            handler.send_json(200, services.collect_diagnostics())
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True

    if path == "/api/support-bundle":
        try:
            body = services.create_support_bundle(performance={
                "capture_status": services.live_capture_status(),
                "stream_metrics": services.stream_metrics_snapshot(),
                "network_status": services.collect_network_performance(),
                "captured_at": time.time(),
            })
            handler.send_response(200)
            handler.send_header("Content-Type", "application/gzip")
            handler.send_header("Content-Disposition", 'attachment; filename="petcam-support.tar.gz"')
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True

    if path == "/api/live-status":
        handler.send_json(200, {
            "capture_status": services.live_capture_status(),
            "capture_status_updated_at": time.time(),
            "stream_metrics": services.stream_metrics_snapshot(),
            "network_status": services.collect_network_performance(),
            "system_metrics": services.system_resource_metrics(),
            "g_streamer_status": services.g_streamer_status_snapshot(),
        })
        return True

    if path == "/api/system":
        handler.send_json(200, {"services.installed_version": services.installed_version()})
        return True

    if path == "/api/health":
        try:
            health = json.loads(services.HEALTH_FILE.read_text(encoding="utf-8"))
            if not isinstance(health, dict):
                raise ValueError("Invalid health status document")
            handler.send_json(200, health)
        except (OSError, ValueError):
            handler.send_json(200, {
                "state": "not_checked",
                "reason": "The periodic health monitor has not reported yet.",
                "recovery_count": 0,
            })
        return True
    return False
