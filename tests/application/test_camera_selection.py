import pytest

from petcam.application.camera_selection import resolve_camera_selection


def test_usb_selection_must_match_a_currently_advertised_mode():
    cameras = [{
        "kind": "usb",
        "id": "usb-cam",
        "device": "/dev/video2",
        "physical_path": "/sys/devices/usb1/1-1",
        "modes": [{"format": "MJPG", "width": 1280, "height": 720, "fps": [30.0]}],
    }]
    selected = resolve_camera_selection(
        {
            "kind": "usb",
            "camera_id": "usb-cam",
            "mode": {"format": "MJPG", "width": 1280, "height": 720, "fps": 30},
        },
        discover_cameras=lambda: cameras,
        mode_supports_fps=lambda mode, fps: fps in mode["fps"],
    )
    assert selected["RESOLUTION"] == "1280x720"
    assert selected["FPS"] == "30"
    assert selected["SOURCE"] == "usb"


def test_selection_rejects_a_camera_that_disappeared():
    with pytest.raises(ValueError, match="no longer available"):
        resolve_camera_selection(
            {
                "kind": "usb",
                "camera_id": "missing",
                "mode": {"format": "MJPG", "width": 640, "height": 480, "fps": 30},
            },
            discover_cameras=lambda: [],
            mode_supports_fps=lambda mode, fps: True,
        )
