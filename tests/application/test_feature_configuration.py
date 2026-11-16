import pytest

from petcam.application.feature_configuration import _mjpeg_required


def test_features_requiring_mjpeg_reject_h264_capture():
    with pytest.raises(RuntimeError, match="Switch the camera back to MJPEG"):
        _mjpeg_required(
            {"enabled": True},
            "timelapse",
            parse_config=lambda path: {"FORMAT": "H264"},
            config_path="/etc/petcam/petcam.conf",
        )


def test_disabled_feature_does_not_require_mjpeg():
    _mjpeg_required(
        {"enabled": False},
        "motion detection",
        parse_config=lambda path: {"FORMAT": "H264"},
        config_path="/etc/petcam/petcam.conf",
    )
