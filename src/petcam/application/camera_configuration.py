"""Application service for validating and applying camera selections."""

from .camera_selection import resolve_camera_selection


def save_selection(
    data,
    *,
    discover_cameras,
    mode_supports_fps,
    apply_config,
):
    """Validate and apply a camera selection through the transactional config service."""
    values = resolve_camera_selection(
        data,
        discover_cameras=discover_cameras,
        mode_supports_fps=mode_supports_fps,
    )
    # apply_config owns the full restart/readiness/rollback transaction. Restarting
    # camera-capture again here tears down the stream immediately after it recovers.
    return apply_config(values)
