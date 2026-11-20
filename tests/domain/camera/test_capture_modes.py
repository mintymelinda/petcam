"""Deterministic camera mode selection tests."""

from petcam.domain.camera.capture_modes import select_csi_mode, select_mode, select_mode_fps


def device(name, modes):
    return {"device": name, "modes": modes}


def mode(fmt, width, height, *fps):
    return {"format": fmt, "width": width, "height": height, "fps": list(fps)}


def test_usb_prefers_exact_native_h264_720p30_independent_of_enumeration_order():
    h264 = mode("H264", 1280, 720, 30)
    mjpeg = mode("MJPG", 1280, 720, 60, 30)
    other = mode("YUYV", 640, 480, 30)
    for modes in ([mjpeg, other, h264], [h264, other, mjpeg]):
        _, selected, native = select_mode([device("/dev/video0", modes)])
        assert (selected["format"], selected["width"], selected["height"]) == ("H264", 1280, 720)
        assert select_mode_fps(selected) == 30
        assert native is False


def test_usb_fallback_prefers_jpeg_before_raw_formats_and_uses_30_fps():
    modes = [
        mode("YUYV", 1280, 720, 30),
        mode("MJPG", 1920, 1080, 30),
        mode("MJPG", 1280, 720, 60, 30),
    ]
    _, selected, native = select_mode([device("/dev/video0", modes)])
    assert (selected["format"], selected["width"], selected["height"]) == ("MJPG", 1280, 720)
    assert select_mode_fps(selected) == 30
    assert native is True


def test_usb_fallback_is_stable_when_preferred_resolution_is_unavailable():
    modes = [mode("MJPG", 1920, 1080, 60, 30), mode("MJPG", 640, 480, 30)]
    _, selected, _ = select_mode([device("/dev/video0", modes)])
    assert (selected["width"], selected["height"]) == (640, 480)


def test_explicit_usb_resolution_and_fps_override_auto_preferences():
    modes = [mode("H264", 1280, 720, 30), mode("MJPG", 1920, 1080, 60, 30)]
    _, selected, _ = select_mode([device("/dev/video0", modes)], resolution="1920x1080", fps="60")
    assert selected["format"] == "MJPG"
    assert select_mode_fps(selected, "60") == 60


def test_explicit_usb_unsupported_fps_is_rejected():
    try:
        select_mode([device("/dev/video0", [mode("H264", 1280, 720, 30)])], fps="25")
    except ValueError as error:
        assert "frame rate" in str(error)
    else:
        raise AssertionError("Unsupported explicit FPS must be rejected")


def test_csi_prefers_720p30_independent_of_enumeration_order():
    target = {"width": 1280, "height": 720, "fps": 30.0}
    alternative = {"width": 1920, "height": 1080, "fps": 30.0}
    camera = {"index": 0, "sensor": "test-sensor", "device_path": "/camera/test", "modes": [alternative, target]}
    for item in (camera, {**camera, "modes": [target, alternative]}):
        selected = select_csi_mode([item])
        assert selected["resolution"] == "1280x720"
        assert selected["fps"] == 30


def test_csi_explicit_resolution_and_fps_take_precedence():
    camera = {"index": 0, "sensor": "test-sensor", "modes": [
        {"width": 1280, "height": 720, "fps": 30.0},
        {"width": 1920, "height": 1080, "fps": 60.0},
    ]}
    selected = select_csi_mode([camera], resolution="1920x1080", fps="60")
    assert selected["resolution"] == "1920x1080"
    assert selected["fps"] == 60

def test_stepwise_fps_fallback_selects_an_advertised_rate_nearest_to_30():
    mode_with_stepwise_fps = {
        "format": "MJPG",
        "width": 1280,
        "height": 720,
        "fps": [],
        "fps_range": {
            "min": 10.0,
            "max": 100.0,
            "min_interval_seconds": 0.01,
            "max_interval_seconds": 0.1,
            "interval_step_seconds": 0.001,
        },
    }
    selected_fps = select_mode_fps(mode_with_stepwise_fps)
    from petcam.domain.camera.capabilities import mode_supports_fps
    assert mode_supports_fps(mode_with_stepwise_fps, selected_fps)
    assert abs(selected_fps - 30) < 1
