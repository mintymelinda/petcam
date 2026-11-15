"""Application use cases for camera-adjacent feature configuration changes.

HTTP handlers translate requests and responses; these functions own the
validation, service transitions, and persistence rollback for feature updates.
"""


def _mjpeg_required(data, feature, parse_config, config_path):
    if data.get("enabled") and parse_config(config_path).get("FORMAT") == "H264":
        raise RuntimeError(
            f"Switch the camera back to MJPEG before enabling {feature}; "
            f"{feature} requires MJPEG frames."
        )


def _consumer_restart_commands(load_rtmp_config, feature):
    commands = [
        (
            ["/usr/bin/systemctl", "restart", "petcam-stream.service"],
            45,
            f"Unable to restart camera after changing {feature} settings.",
        ),
    ]
    if load_rtmp_config()["enabled"]:
        commands.append(
            (
                ["/usr/bin/systemctl", "restart", "petcam-rtmp.service"],
                30,
                "Unable to restart OBS output after changing MJPEG consumer settings.",
            )
        )
    return commands


def update_timelapse(
    data,
    *,
    parse_config,
    config_path,
    load_config,
    save_config,
    load_rtmp_config,
    apply_transaction,
):
    """Apply timelapse settings with dependent-service restart and rollback."""
    _mjpeg_required(data, "timelapse", parse_config, config_path)
    current = load_config()
    commands = _consumer_restart_commands(load_rtmp_config, "timelapse")
    return apply_transaction(
        save_config, current, {**current, **data}, commands, commands,
    )


def update_motion(
    data,
    *,
    parse_config,
    config_path,
    load_config,
    save_config,
    load_rtmp_config,
    apply_transaction,
):
    """Apply motion settings with dependent-service restart and rollback."""
    _mjpeg_required(data, "motion detection", parse_config, config_path)
    current = load_config()
    commands = _consumer_restart_commands(load_rtmp_config, "motion")
    return apply_transaction(
        save_config, current, {**current, **data}, commands, commands,
    )


def update_light_sensor(data, *, save_config):
    """Persist light-sensor settings and return the saved configuration."""
    return save_config(data)


def _rtmp_action(enabled, was_active):
    if enabled:
        return "restart" if was_active else "enable"
    return "disable"


def update_rtmp_output(
    data,
    *,
    parse_config,
    config_path,
    load_config,
    save_config,
    check_runtime,
    run,
    service_command,
    apply_transaction,
    public_config,
    status_snapshot,
):
    """Apply OBS RTSP output settings as one recoverable camera/output transition."""
    current_camera = parse_config(config_path)
    if current_camera.get("FORMAT") == "H264" and data.get("enabled") is not True:
        raise RuntimeError("OBS RTSP output is forced on while H.264 capture is selected.")
    if data.get("enabled"):
        try:
            check_runtime()
        except ValueError as error:
            raise RuntimeError(str(error)) from error

    current = load_config()
    was_active = run(
        ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
        check=False,
        timeout=5,
    ).returncode == 0
    candidate = {**current, **data}
    action = _rtmp_action(candidate["enabled"], was_active)
    previous_action = _rtmp_action(current["enabled"], was_active)
    commands = [
        (
            ["/usr/bin/systemctl", "restart", "petcam-stream.service"],
            45,
            "Unable to restart the camera with the saved OBS output settings.",
        ),
        (
            service_command(action),
            30,
            "Unable to update OBS output service state.",
        ),
    ]
    rollback_commands = [
        (
            ["/usr/bin/systemctl", "restart", "petcam-stream.service"],
            45,
            "Unable to restart the camera with the restored OBS output settings.",
        ),
        (
            service_command(previous_action),
            30,
            "Unable to restore OBS output service state.",
        ),
    ]
    updated = apply_transaction(
        save_config, current, candidate, commands, rollback_commands,
    )
    return {
        "config": public_config(updated),
        "status": status_snapshot(),
    }
