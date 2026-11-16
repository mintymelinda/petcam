import pytest

from petcam.domain.camera.capture_policy import (
    validate_capture_feature_compatibility,
    validate_performance_budget,
)


def test_over_budget_capture_requires_an_explicit_override():
    with pytest.raises(ValueError, match="performance budget"):
        validate_performance_budget(1920, 1080, 30, 50_000_000, capture_format="MJPEG")
    validate_performance_budget(
        1920, 1080, 30, 50_000_000,
        capture_format="MJPEG", allow_override=True,
    )


def test_h264_rejects_features_that_require_mjpeg_frames():
    with pytest.raises(ValueError, match="Disable timelapse and motion"):
        validate_capture_feature_compatibility(
            "H264", timelapse_enabled=True, motion_enabled=False,
        )
