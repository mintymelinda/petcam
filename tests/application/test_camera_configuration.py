import pytest

from petcam.application.camera_configuration import save_selection


def test_camera_configuration_rejects_selection_when_device_is_gone():
    with pytest.raises(ValueError, match="no longer available"):
        save_selection(
            {"kind": "usb", "camera_id": "missing", "mode": {
                "format": "MJPG", "width": 640, "height": 480, "fps": 30,
            }},
            discover_cameras=lambda: [],
            mode_supports_fps=lambda mode, fps: True,
            pixel_budgets={"pi5": 100_000_000},
            model_tier=lambda model: "pi5",
            read_model=lambda: "Raspberry Pi 5",
            config_path="/etc/petcam/petcam.conf",
            parse_config=lambda path: {},
            load_timelapse_config=lambda: {},
            load_motion_config=lambda: {},
            check_gstreamer_runtime=lambda: None,
            restart_g_streamer_service=lambda: None,
            apply_config=lambda config: config,
        )
