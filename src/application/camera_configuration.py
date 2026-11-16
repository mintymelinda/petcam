"""Application service for validating and applying camera selections."""

from ..domain.camera.capture_policy import (
    validate_capture_feature_compatibility,
    validate_performance_budget,
)
from .camera_selection import resolve_camera_selection


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
    load_timelapse_config,
    load_motion_config,
    check_gstreamer_runtime,
    restart_g_streamer_service,
    apply_config,
):
    """Validate and apply a camera selection with RTSP service recovery."""
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
    previous_camera = parse_config(config_path)
    if values["FORMAT"] == "H264":
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
        updated = apply_config(values)
        camera_applied = True
        restart_g_streamer_service()
        return updated
    except Exception:
        if camera_applied:
            try:
                apply_config(previous_camera)
                restart_g_streamer_service()
            except Exception as rollback_error:
                raise RuntimeError(
                    "Camera selection failed and restoring the previous camera/GStreamer state also failed: "
                    + str(rollback_error)
                ) from rollback_error
        raise
