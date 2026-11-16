"""Camera inventory and capture-control HTTP routes."""


def handle_get(handler, services, path):
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
    return False


def handle_post(handler, services, path, data):
    if path == "/api/camera-controls":
        handler.send_json(200, services.set_camera_control(data))
        return True
    if path == "/api/select":
        services.save_selection(data)
        handler.send_json(200, {"ok": True})
        return True
    return False
