"""Application service for validating and applying camera selections."""

from .camera_selection import resolve_camera_selection


def save_selection(
    data,
    *,
    discover_cameras,
    mode_supports_fps,
    persist_selection,
):
    """Validate a native H.264 mode and hand it to the GStreamer pipeline."""
    values = resolve_camera_selection(
        data,
        discover_cameras=discover_cameras,
        mode_supports_fps=mode_supports_fps,
    )
    # The capture worker republishes selected camera metadata. GStreamer then
    # negotiates the requested caps and reports errors asynchronously; there is
    # no RTSP packet wait or camera-profile rollback in this request path.
    return persist_selection(values)
