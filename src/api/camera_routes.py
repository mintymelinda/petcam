"""Camera discovery, selection, control, and event-image routes."""

import re
from urllib.parse import urlparse


_EVENT_FILENAME = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z(?:-[0-9]{3})?\.jpg")


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path == "/api/camera-controls":
        try:
            handler.send_json(200, services.read_camera_controls())
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True
    if path == "/api/cameras":
        try:
            handler.send_json(200, {
                "cameras": services.camera_inventory(),
                "active_config": services.active_camera_config(),
                "capture_status": services.live_capture_status(),
            })
        except Exception as error:
            handler.send_json(500, {"error": str(error)})
        return True
    if path.startswith("/api/motion/events/"):
        filename = path.rsplit("/", 1)[-1]
        if not _EVENT_FILENAME.fullmatch(filename):
            handler.send_error(404)
            return True
        image_path = services.MOTION_FRAMES / filename
        try:
            payload = image_path.read_bytes()
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
    return False


def handle_post(handler, services, data):
    path = urlparse(handler.path).path
    if path == "/api/camera-controls":
        handler.send_json(200, services.set_camera_control(data))
        return True
    if path == "/api/select":
        services.save_selection(data)
        handler.send_json(200, {"ok": True})
        return True
    return False
