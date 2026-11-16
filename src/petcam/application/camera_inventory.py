"""Application services for camera discovery and capture-mode policy.

The HTTP layer supplies hardware adapters; this module owns the inventory
shape and the capture-mode policy exposed by the API.
"""


def build_capture_modes(camera, performance_budget):
    """Return the server-approved capture-mode catalog for one camera."""
    modes = []
    for advertised in camera["modes"]:
        fps_values = advertised.get("fps") or [
            advertised.get("fps_range", {}).get("max") or 30
        ]
        if camera["kind"] == "usb":
            fps_values = [
                fps
                for fps in fps_values
                if isinstance(fps, int)
                or (isinstance(fps, float) and fps.is_integer())
            ]
        for fps in fps_values:
            mode = {
                "format": advertised.get("format") or "CSI",
                "width": advertised["width"],
                "height": advertised["height"],
                "fps": fps,
            }
            estimated_rate = mode["width"] * mode["height"] * float(fps)
            mode["estimated_pixels_per_second"] = estimated_rate
            mode["performance_budget_pixels_per_second"] = performance_budget
            mode["exceeds_performance_budget"] = (
                mode["format"] != "H264"
                and performance_budget > 0
                and estimated_rate > performance_budget
            )
            modes.append(mode)
    return modes


def build_camera_inventory(
    discover_devices,
    discover_csi_cameras,
    model_tier,
    read_model,
    pixel_budgets,
    ustreamer_formats,
    camera_identity,
):
    """Discover cameras and return API-ready records with approved modes."""
    usb_devices = discover_devices()
    csi_cameras = discover_csi_cameras()
    tier = model_tier(read_model())
    performance_budget = pixel_budgets[tier]
    result = []

    for item in usb_devices:
        camera = {
            "kind": "usb",
            "device": item["device"],
            "physical_path": item.get("physical_path", ""),
            "label": f'USB · {item["device"]}',
            "modes": [
                mode
                for mode in item["modes"]
                if mode["format"] in (ustreamer_formats | {"H264"})
            ],
        }
        identity = camera_identity(camera)
        result.append(
            {
                **camera,
                "id": identity["id"],
                "stable_identity": identity["stable_identity"],
                "hardware_tier": tier,
                "hardware_budget_pixels_per_second": performance_budget,
                "capture_modes": build_capture_modes(camera, performance_budget),
            }
        )

    for item in csi_cameras:
        camera = {
            "kind": "csi",
            "camera": item["index"],
            "sensor": item["sensor"],
            "device_path": item.get("device_path", ""),
            "label": f'CSI · {item["sensor"]} (camera {item["index"]})',
            "modes": item["modes"],
        }
        identity = camera_identity(camera)
        result.append(
            {
                **camera,
                "id": identity["id"],
                "stable_identity": identity["stable_identity"],
                "hardware_tier": tier,
                "hardware_budget_pixels_per_second": performance_budget,
                "capture_modes": build_capture_modes(camera, performance_budget),
            }
        )
    return result
