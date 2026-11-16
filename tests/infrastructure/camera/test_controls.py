from petcam.infrastructure.camera.controls import parse_controls


def test_control_parser_reads_integer_range_and_writability():
    controls = parse_controls(
        "Brightness 0x00980900 (int) : min=0 max=255 step=1 default=128 value=64\n"
        "  Contrast 0x00980901 (int) : min=0 max=100 step=5 default=50 value=55 flags=read-only\n"
    )
    assert controls[0]["name"] == "Brightness"
    assert controls[0]["value"] == 64
    assert controls[0]["writable"] is True
    assert controls[1]["writable"] is False
    assert controls[1]["value"] == 55
