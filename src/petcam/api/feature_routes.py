"""Timelapse, motion, and ambient-light feature configuration routes."""

from urllib.parse import urlparse


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path == "/api/timelapse":
        try:
            config = services.load_timelapse_config()
            handler.send_json(200, {"config": config, "status": services.timelapse_snapshot(config)})
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True
    if path == "/api/motion":
        try:
            config = services.load_motion_config()
            handler.send_json(200, {"config": config, "status": services.motion_snapshot(config)})
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True
    if path == "/api/light-sensor":
        try:
            handler.send_json(200, {
                "config": services.load_light_config(),
                "status": services.light_sensor_status(),
            })
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return True
    return False


def handle_post(handler, services, data):
    path = urlparse(handler.path).path
    if path == "/api/timelapse":
        updated = services.update_timelapse(data)
        handler.send_json(200, {"ok": True, "config": updated})
        return True
    if path == "/api/motion":
        updated = services.update_motion(data)
        handler.send_json(200, {"ok": True, "config": updated})
        return True
    if path == "/api/light-sensor":
        updated = services.update_light_sensor(data)
        handler.send_json(200, {"ok": True, "config": updated})
        return True
    return False
