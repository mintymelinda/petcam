"""Runtime status, health, diagnostics, and support-bundle routes."""

import json
import time
from urllib.parse import urlparse


def handle_get(handler, services):
    path = urlparse(handler.path).path
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
        handler.send_json(200, services.diagnostics_snapshot())
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
