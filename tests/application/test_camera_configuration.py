import pytest

from petcam.application import camera_configuration as application


def dependencies(persist_selection):
    return {
        "discover_cameras": lambda: [{
            "kind": "usb",
            "id": "usb-1",
            "device": "/dev/video0",
            "physical_path": "",
            "modes": [{
                "width": 1280,
                "height": 720,
                "format": "H264",
                "fps": [30],
            }],
        }],
        "mode_supports_fps": lambda _mode, _fps: True,
        "persist_selection": persist_selection,
    }


def selection():
    return {
        "kind": "usb",
        "camera_id": "usb-1",
        "device": "/dev/video0",
        "mode": {
            "width": 1280,
            "height": 720,
            "format": "H264",
            "fps": 30,
        },
    }


def test_save_selection_persists_native_h264_selection_once():
    persisted = []
    result = application.save_selection(
        selection(),
        **dependencies(lambda config: persisted.append(config) or config),
    )

    assert result["SOURCE"] == "usb"
    assert result["FORMAT"] == "H264"
    assert result["RESOLUTION"] == "1280x720"
    assert result["FPS"] == "30"
    assert persisted == [result]


def test_save_selection_propagates_persistence_failure_without_retrying():
    persisted = []

    def persist(config):
        persisted.append(config)
        raise RuntimeError("Capture worker restart failed")

    with pytest.raises(RuntimeError, match="Capture worker restart failed"):
        application.save_selection(selection(), **dependencies(persist))

    assert len(persisted) == 1

