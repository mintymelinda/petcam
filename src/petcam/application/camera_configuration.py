"""Application service for validating and applying camera selections."""

from .camera_selection import resolve_camera_selection


def save_selection(
    data,
    *,
    discover_cameras,
    mode_supports_fps,
    config_path,
    parse_config,
    restart_camera_capture_service,
    apply_config,
):
    """Persist the exact hardware-advertised selection and restart its consumer."""
    values = resolve_camera_selection(
        data,
        discover_cameras=discover_cameras,
        mode_supports_fps=mode_supports_fps,
    )
    previous_camera = parse_config(config_path)
    camera_applied = False
    try:
        updated = apply_config(values)
        camera_applied = True
        restart_camera_capture_service()
        return updated
    except Exception:
        if camera_applied:
            try:
                apply_config(previous_camera)
                restart_camera_capture_service()
            except Exception as rollback_error:
                raise RuntimeError(
                    "Camera selection failed and restoring the previous camera/GStreamer state also failed: "
                    + str(rollback_error)
                ) from rollback_error
        raise
