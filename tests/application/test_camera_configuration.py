import pytest

from petcam.application import camera_configuration as application


def dependencies(apply_config):
    return {
        "discover_cameras": lambda: [],
        "mode_supports_fps": lambda _mode, _fps: True,
        "config_path": "/tmp/petcam.conf",
        "parse_config": lambda _path: {"SOURCE": "usb", "FORMAT": "MJPEG"},
        "restart_g_streamer_service": lambda: None,
        "apply_config": apply_config,
    }


def test_save_selection_applies_camera_and_restarts_rtsp(monkeypatch):
    values = {
        "SOURCE": "usb", "RESOLUTION": "1280x720",
        "FPS": "30", "FORMAT": "MJPEG",
    }
    monkeypatch.setattr(application, "resolve_camera_selection", lambda *_a, **_k: values)
    saved = []
    restarted = []
    deps = dependencies(lambda config: saved.append(config) or config)
    deps["restart_g_streamer_service"] = lambda: restarted.append(True)

    result = application.save_selection({}, **deps)

    assert result == values
    assert saved == [values]
    assert restarted == [True]


def test_save_selection_rolls_back_camera_when_rtsp_restart_fails(monkeypatch):
    values = {
        "SOURCE": "usb", "RESOLUTION": "1280x720",
        "FPS": "30", "FORMAT": "MJPEG",
    }
    previous = {"SOURCE": "usb", "FORMAT": "MJPEG", "RESOLUTION": "640x480"}
    monkeypatch.setattr(application, "resolve_camera_selection", lambda *_a, **_k: values)
    saved = []
    restarts = iter([RuntimeError("RTSP restart failed"), None])

    def apply(config):
        saved.append(config)
        return config

    def restart():
        result = next(restarts)
        if result:
            raise result

    deps = dependencies(apply)
    deps["parse_config"] = lambda _path: previous
    deps["restart_g_streamer_service"] = restart

    with pytest.raises(RuntimeError, match="RTSP restart failed"):
        application.save_selection({}, **deps)

    assert saved == [values, previous]


def test_hardware_mode_is_not_rejected_by_performance_or_feature_policy(monkeypatch):
    values = {
        "SOURCE": "usb", "RESOLUTION": "3840x2160",
        "FPS": "60", "FORMAT": "YUYV",
    }
    monkeypatch.setattr(application, "resolve_camera_selection", lambda *_a, **_k: values)
    applied = []
    deps = dependencies(lambda config: applied.append(config) or config)

    result = application.save_selection({}, **deps)

    assert result == values
    assert applied == [values]
