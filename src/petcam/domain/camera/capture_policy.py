"""Pure validation policy for camera capture-mode selection."""

from __future__ import annotations

PERFORMANCE_OVERRIDE_MESSAGE = (
    "This capture mode exceeds the estimated performance budget for this device. "
    "Confirm the warning to use it anyway, or choose a lower resolution or FPS."
)
H264_FEATURE_CONFLICT_MESSAGE = (
    "Disable timelapse and motion detection before selecting H.264; "
    "both require the MJPEG capture feed."
)


def estimated_pixel_rate(width: int, height: int, fps: float) -> float:
    """Estimate the number of pixels the capture pipeline must process per second."""
    return int(width) * int(height) * float(fps)


def validate_performance_budget(
    width: int,
    height: int,
    fps: float,
    pixel_budget: float,
    *,
    capture_format: str,
    allow_override: bool = False,
) -> None:
    """Reject over-budget non-H.264 modes unless the user explicitly overrides."""
    if (
        capture_format != "H264"
        and estimated_pixel_rate(width, height, fps) > pixel_budget
        and allow_override is not True
    ):
        raise ValueError(PERFORMANCE_OVERRIDE_MESSAGE)


def validate_capture_feature_compatibility(
    capture_format: str,
    *,
    timelapse_enabled: bool,
    motion_enabled: bool,
) -> None:
    """Enforce capture-feed requirements independently of worker/config I/O."""
    if capture_format == "H264" and (timelapse_enabled or motion_enabled):
        raise ValueError(H264_FEATURE_CONFLICT_MESSAGE)
