"""Application service for validating and applying camera selections."""

try:
    from ..domain.camera.capture_policy import (
        validate_capture_feature_compatibility,
        validate_performance_budget,
    )
    from ..camera_selection import resolve_camera_selection
except ImportError:  # Support the installed standalone web-manager entry point.
    from domain.camera.capture_policy import (
        validate_capture_feature_compatibility,
        validate_performance_budget,
    )
    from camera_selection import resolve_camera_selection


def save_selection(
    data,
    *,
    discover_cameras,
    mode_supports_fps,
    pixel_budgets,
    model_tier,
    read_model,
    config_path,
    parse_config,
    load_rtmp_config,
    save_rtmp_config,
    load_timelapse_config,
    load_motion_config,
    check_gstreamer_runtime,
    run,
    set_rtmp_service,
    apply_config,
):
    """Validate a discovered capture mode and apply it with output rollback."""
    values = resolve_camera_selection(
        data,
        discover_cameras=discover_cameras,
        mode_supports_fps=mode_supports_fps,
    )
    width, height = map(int, values["RESOLUTION"].split("x"))
    fps = float(values["FPS"])
    pixel_budget = pixel_budgets[model_tier(read_model())]
    validate_performance_budget(
        width,
        height,
        fps,
        pixel_budget,
        capture_format=values["FORMAT"],
        allow_override=data.get("allow_performance_override") is True,
    )
    requested_h264 = values["FORMAT"] == "H264"
    previous_camera = parse_config(config_path)
    previous_rtmp = load_rtmp_config()
    rtmp_was_active = False
    if requested_h264 or previous_rtmp["enabled"]:
        rtmp_was_active = run(
            ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
            check=False, timeout=5,
        ).returncode == 0

    if requested_h264:
        validate_capture_feature_compatibility(
            values["FORMAT"],
            timelapse_enabled=load_timelapse_config().get("enabled") is True,
            motion_enabled=load_motion_config().get("enabled") is True,
        )
        try:
            check_gstreamer_runtime()
        except ValueError as error:
            raise RuntimeError(str(error)) from error

    camera_applied = False
    try:
        if requested_h264 or previous_camera.get("FORMAT") == "H264":
            if rtmp_was_active:
                set_rtmp_service("disable")
        if requested_h264:
            save_rtmp_config({**previous_rtmp, "enabled": True})
        updated = apply_config(values)
        camera_applied = True
        current_rtmp = load_rtmp_config()
        if current_rtmp["enabled"]:
            set_rtmp_service("enable" if requested_h264 or previous_camera.get("FORMAT") == "H264" or not rtmp_was_active else "restart")
        elif rtmp_was_active:
            set_rtmp_service("disable")
        return updated
    except Exception:
        if requested_h264:
            save_rtmp_config(previous_rtmp)
        if camera_applied:
            try:
                if previous_camera.get("FORMAT") == "H264":
                    set_rtmp_service("disable")
                apply_config(previous_camera)
                if previous_rtmp["enabled"]:
                    set_rtmp_service("enable")
                elif rtmp_was_active:
                    set_rtmp_service("disable")
            except Exception as rollback_error:
                raise RuntimeError(f"Camera selection failed and restoring the previous camera/output settings also failed: {rollback_error}")
        elif rtmp_was_active and previous_rtmp["enabled"]:
            set_rtmp_service("enable")
        raise
