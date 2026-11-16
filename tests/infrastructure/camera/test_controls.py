from types import SimpleNamespace

import pytest

from petcam.infrastructure.camera import controls


SAMPLE = """
brightness 0x00980900 (int) : min=0 max=255 step=1 default=128 value=90
exposure_auto 0x009a0901 (menu) : min=0 max=3 step=1 default=1 value=1
    0: Auto Mode
    1: Manual Mode
    2: Shutter Priority
"""


def test_parse_controls_exposes_supported_ranges_and_menu_values():
    parsed = controls.parse_controls(SAMPLE)
    assert parsed[0]["name"] == "brightness"
    assert parsed[0]["value"] == 90
    assert parsed[0]["writable"] is True
    assert parsed[1]["menu"] == [
        {"value": 0, "label": "Auto Mode"},
        {"value": 1, "label": "Manual Mode"},
        {"value": 2, "label": "Shutter Priority"},
    ]


def test_parse_controls_rejects_values_outside_the_reported_menu():
    sample = SAMPLE.replace("value=1", "value=3")
    parsed = controls.parse_controls(sample)
    assert parsed[1]["value"] is None


def test_read_controls_requires_an_active_usb_camera():
    result = controls.read_controls(None, lambda *_args, **_kwargs: None)
    assert result["supported"] is False
    assert result["controls"] == []


def test_set_control_validates_before_running_v4l2_command():
    camera = {"device": "/dev/video0"}
    current = {"controls": [{
        "name": "brightness", "type": "int", "writable": True,
        "min": 0, "max": 255, "step": 5, "menu": [],
    }]}
    run = lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr="")
    with pytest.raises(ValueError, match="supported step"):
        controls.set_control(
            {"name": "brightness", "value": 92}, camera,
            lambda _camera: current, run,
        )
