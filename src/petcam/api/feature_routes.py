"""Motion, timelapse, and ambient-light feature routes."""


def handle_get(handler, services, path):
    readers = {
        "/api/timelapse": (services.load_timelapse_config, services.timelapse_snapshot),
        "/api/motion": (services.load_motion_config, services.motion_snapshot),
        "/api/light-sensor": (services.load_light_config, services.light_sensor_status),
    }
    if path not in readers:
        return False
    try:
        load_config, read_status = readers[path]
        config = load_config()
        status = read_status(config) if path != "/api/light-sensor" else read_status()
        handler.send_json(200, {"config": config, "status": status})
    except Exception as error:
        handler.send_json(503, {"error": str(error)})
    return True


def handle_post(handler, services, path, data):
    updates = {
        "/api/timelapse": services.update_timelapse,
        "/api/motion": services.update_motion,
        "/api/light-sensor": services.update_light_sensor,
    }
    if path not in updates:
        return False
    updated = updates[path](data)
    handler.send_json(200, {"ok": True, "config": updated})
    return True
