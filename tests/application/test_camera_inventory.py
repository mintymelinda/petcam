from petcam.application.camera_inventory import build_camera_inventory, build_capture_modes


def test_build_capture_modes_flattens_frame_rates_and_applies_pixel_budget():
    camera = {
        "kind": "usb",
        "modes": [
            {"format": "MJPG", "width": 1280, "height": 720, "fps": [15, 30]},
            {"format": "H264", "width": 1920, "height": 1080, "fps": [30]},
        ],
    }

    modes = build_capture_modes(camera, 20_000_000)

    assert [(mode["width"], mode["height"], mode["fps"]) for mode in modes] == [
        (1280, 720, 15), (1280, 720, 30), (1920, 1080, 30)
    ]
    assert modes[0]["exceeds_performance_budget"] is False
    assert modes[1]["exceeds_performance_budget"] is True
    assert modes[2]["exceeds_performance_budget"] is False


def test_build_capture_modes_preserves_fractional_csi_rates():
    modes = build_capture_modes({
        "kind": "csi",
        "modes": [{"width": 1640, "height": 1232, "fps": [20.0, 29.97]}],
    }, 100_000_000)
    assert [item["fps"] for item in modes] == [20.0, 29.97]


def test_build_camera_inventory_combines_usb_and_csi_records():
    usb = [{
        "device": "/dev/video0",
        "physical_path": "/sys/devices/usb1/1-1",
        "modes": [{"format": "MJPG", "width": 640, "height": 480, "fps": [30]}],
    }]
    csi = [{
        "index": 0,
        "sensor": "imx708",
        "device_path": "/base/camera0",
        "modes": [{"width": 1280, "height": 720, "fps": [30.0]}],
    }]

    result = build_camera_inventory(
        discover_devices=lambda: usb,
        discover_csi_cameras=lambda: csi,
        model_tier=lambda _model: "pi5",
        read_model=lambda: "Raspberry Pi 5",
        pixel_budgets={"pi5": 50_000_000},
        ustreamer_formats={"MJPEG"},
        camera_identity=lambda camera: {
            "id": f'{camera["kind"]}-stable',
            "stable_identity": True,
        },
    )

    assert [item["kind"] for item in result] == ["usb", "csi"]
    assert result[0]["id"] == "usb-stable"
    assert result[1]["device_path"] == "/base/camera0"
    assert result[1]["capture_modes"][0]["fps"] == 30.0
