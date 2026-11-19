import pytest

from petcam.application import camera_configuration as application


def dependencies(apply_config):
    return {
        "discover_cameras": lambda: [],
        "mode_supports_fps": lambda _mode, _fps: True,
        "apply_config": apply_config,
    }


def test_save_selection_applies_camera_configuration_once(monkeypatch):
    values = {
        "SOURCE": "usb", "RESOLUTION": "1280x720",
        "FPS": "30", "FORMAT": "MJPEG",
    }
    monkeypatch.setattr(application, "resolve_camera_selection", lambda *_a, **_k: values)
    applied = []
    deps = dependencies(lambda config: applied.append(config) or config)

    result = application.save_selection({}, **deps)

    assert result == values
    assert applied == [values]


def test_save_selection_propagates_transactional_apply_failure_without_restarting_again(monkeypatch):
    values = {
        "SOURCE": "usb", "RESOLUTION": "1280x720",
        "FPS": "30", "FORMAT": "MJPEG",
    }
    monkeypatch.setattr(application, "resolve_camera_selection", lambda *_a, **_k: values)
    applied = []

    def apply(config):
        applied.append(config)
        raise RuntimeError("Capture readiness failed; previous settings restored")

    with pytest.raises(RuntimeError, match="previous settings restored"):
        application.save_selection({}, **dependencies(apply))

    # apply_config performs its own rollback; this layer must not retry it.
    assert applied == [values]


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
