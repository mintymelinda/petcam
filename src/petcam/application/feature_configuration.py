"""Application use cases for camera-adjacent feature configuration changes."""


def _mjpeg_required(data, feature, parse_config, config_path):
    if data.get("enabled") and parse_config(config_path).get("FORMAT") == "H264":
        raise RuntimeError(
            f"Switch the camera back to MJPEG before enabling {feature}; "
            f"{feature} requires MJPEG frames."
        )


def _consumer_restart_commands(feature, supervisor_command):
    return [
        (
            supervisor_command("restart", "camera-capture"),
            45,
            f"Unable to restart camera after changing {feature} settings.",
        ),
        (
            supervisor_command("restart", "gstreamer-rtsp"),
            30,
            "Unable to reconnect GStreamer RTSP after changing camera consumer settings.",
        ),
    ]


def update_timelapse(
    data, *, parse_config, config_path, load_config, save_config,
    supervisor_command, apply_transaction,
):
    _mjpeg_required(data, "timelapse", parse_config, config_path)
    current = load_config()
    commands = _consumer_restart_commands("timelapse", supervisor_command)
    return apply_transaction(save_config, current, {**current, **data}, commands, commands)


def update_motion(
    data, *, parse_config, config_path, load_config, save_config,
    supervisor_command, apply_transaction,
):
    _mjpeg_required(data, "motion detection", parse_config, config_path)
    current = load_config()
    commands = _consumer_restart_commands("motion", supervisor_command)
    return apply_transaction(save_config, current, {**current, **data}, commands, commands)


def update_light_sensor(data, *, save_config):
    return save_config(data)
