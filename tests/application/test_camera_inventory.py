from petcam.application.camera_inventory import build_camera_inventory, build_capture_modes


def test_build_capture_modes_preserves_every_advertised_usb_format_and_rate():
    camera = {
        "kind": "usb",
        "modes": [
            {"format": "MJPG", "width": 1280, "height": 720, "fps": [15, 30]},
            {"format": "YUYV", "width": 1920, "height": 1080, "fps": [30]},
            {"format": "H264", "width": 3840, "height": 2160, "fps": [30]},
        ],
    }

    modes = build_capture_modes(camera)

    assert [(mode["format"], mode["width"], mode["height"], mode["fps"]) for mode in modes] == [
        ("MJPG", 1280, 720, 15),
        ("MJPG", 1280, 720, 30),
        ("YUYV", 1920, 1080, 30),
        ("H264", 3840, 2160, 30),
    ]
    assert all("exceeds_performance_budget" not in mode for mode in modes)


def test_build_capture_modes_preserves_fractional_csi_rates():
    modes = build_capture_modes({
        "kind": "csi",
        "modes": [{"width": 1640, "height": 1232, "fps": [20.0, 29.97]}],
    })
    assert [item["fps"] for item in modes] == [20.0, 29.97]


def test_build_camera_inventory_returns_every_discovered_hardware_mode():
    usb = [{
        "device": "/dev/video0",
        "physical_path": "/sys/devices/usb1/1-1",
        "modes": [
            {"format": "YUYV", "width": 640, "height": 480, "fps": [30]},
            {"format": "MJPG", "width": 1920, "height": 1080, "fps": [60]},
        ],
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
        camera_identity=lambda camera: {
            "id": f'{camera["kind"]}-stable',
            "stable_identity": True,
        },
    )

    assert [item["kind"] for item in result] == ["usb", "csi"]
    assert result[0]["id"] == "usb-stable"
    assert len(result[0]["capture_modes"]) == 2
    assert result[0]["capture_modes"][0]["format"] == "YUYV"
    assert result[1]["device_path"] == "/base/camera0"
    assert result[1]["capture_modes"][0]["fps"] == 30.0
