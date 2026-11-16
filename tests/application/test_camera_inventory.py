from petcam.application.camera_inventory import build_capture_modes


def test_capture_mode_catalog_flattens_frame_rates_and_marks_budget_overruns():
    modes = build_capture_modes(
        {
            "kind": "usb",
            "modes": [
                {"format": "MJPG", "width": 1280, "height": 720, "fps": [15, 30]},
                {"format": "H264", "width": 1920, "height": 1080, "fps": [30]},
            ],
        },
        20_000_000,
    )
    assert [(mode["width"], mode["fps"]) for mode in modes] == [
        (1280, 15), (1280, 30), (1920, 30),
    ]
    assert modes[1]["exceeds_performance_budget"] is True
    assert modes[2]["exceeds_performance_budget"] is False
