from petcam.domain.camera.capabilities import camera_identity, mode_supports_fps, parse_modes


SAMPLE = """[0]: 'MJPG' (Motion-JPEG, compressed)
  Size: Discrete 1280x720
    Interval: Discrete 0.033s (30.000 fps)
    Interval: Discrete 0.017s (60.000 fps)
"""


def test_parse_modes_preserves_formats_dimensions_and_fps():
    modes = parse_modes(SAMPLE)
    assert len(modes) == 1
    assert modes[0]["format"] == "MJPG"
    assert (modes[0]["width"], modes[0]["height"]) == (1280, 720)
    assert modes[0]["fps"] == [60.0, 30.0]
    assert mode_supports_fps(modes[0], 30)
    assert not mode_supports_fps(modes[0], 45)


def test_usb_identity_is_stable_across_video_node_changes():
    first = camera_identity({"kind": "usb", "device": "/dev/video2", "physical_path": "/sys/devices/usb1/1-1"})
    second = camera_identity({"kind": "usb", "device": "/dev/video5", "physical_path": "/sys/devices/usb1/1-1"})
    assert first["stable_identity"] is True
    assert first["id"] == second["id"]
