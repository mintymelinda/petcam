import pytest

from petcam.infrastructure.streaming.gstreamer import GStreamerError, build_gstreamer_launch


def test_native_h264_pipeline_keeps_video_compressed():
    launch = build_gstreamer_launch({
        "native_h264": True,
        "resolution": "1920x1080",
        "fps": 30,
        "device": "/dev/video2",
        "backend": "usb",
    })
    assert "video/x-h264" in launch
    assert "h264parse" in launch
    assert "decode" not in launch


def test_mjpeg_pipeline_uses_only_the_local_stream():
    launch = build_gstreamer_launch({})
    assert "multipartdemux" in launch
    assert "rtpjpegpay" in launch
    with pytest.raises(GStreamerError, match="local PetCam stream"):
        build_gstreamer_launch({}, mjpeg_url="http://example.invalid/stream")
