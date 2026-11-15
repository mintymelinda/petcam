"""Application service for validating and applying camera selections."""

if __package__:
    from .camera_selection import resolve_camera_selection
else:  # Support the installed standalone web-manager entry point.
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
    kind = values["SOURCE"]
    width, height = map(int, values["RESOLUTION"].split("x"))
    fps = float(values["FPS"])
    estimated_pixels_per_second = width * height * float(fps)
    pixel_budget = pixel_budgets[model_tier(read_model())]
    if values["FORMAT"] != "H264" and estimated_pixels_per_second > pixel_budget and data.get("allow_performance_override") is not True:
        raise ValueError(
            "This capture mode exceeds the estimated performance budget for this device. "
            "Confirm the warning to use it anyway, or choose a lower resolution or FPS."
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
        if load_timelapse_config().get("enabled") or load_motion_config().get("enabled"):
            raise ValueError("Disable timelapse and motion detection before selecting H.264; both require the MJPEG capture feed.")
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
