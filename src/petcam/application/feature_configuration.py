"""Application use cases for camera-adjacent feature configuration changes."""


def update_timelapse(data, *, load_config, save_config):
    """Persist time-lapse settings; the existing camera tee serves its frame branch."""
    current = load_config()
    return save_config({**current, **data})


def update_motion(data, *, load_config, save_config):
    """Persist motion settings without restarting the shared camera or RTSP pipeline."""
    current = load_config()
    return save_config({**current, **data})


def update_light_sensor(data, *, save_config):
    return save_config(data)
