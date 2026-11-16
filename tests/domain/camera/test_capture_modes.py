from petcam.domain.camera.capture_modes import model_tier, select_native_h264_mode


def test_native_h264_selection_uses_only_advertised_h264_modes():
    devices = [{
        "device": "/dev/video2",
        "modes": [
            {"format": "MJPG", "width": 1280, "height": 720, "fps": [30.0]},
            {"format": "H264", "width": 1920, "height": 1080, "fps": [30.0]},
        ],
    }]
    selected = select_native_h264_mode(devices)
    assert selected == {
        "device": "/dev/video2",
        "resolution": "1920x1080",
        "fps": 30,
        "format": "H264",
    }


def test_model_tier_distinguishes_zero_and_pi5_hardware():
    assert model_tier("Raspberry Pi Zero W Rev 1.1") == "zero"
    assert model_tier("Raspberry Pi 5 Model B Rev 1.0") == "pi5"
