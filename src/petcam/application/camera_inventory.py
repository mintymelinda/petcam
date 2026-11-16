"""Expose hardware-reported camera capabilities without application mode policy."""


def build_capture_modes(camera):
    """Flatten every mode reported by the camera without applying policy."""
    modes = []
    for advertised in camera["modes"]:
        fps_values = advertised.get("fps") or [
            advertised.get("fps_range", {}).get("max") or 30
        ]
        for fps in fps_values:
            modes.append({
                "format": advertised.get("format") or "CSI",
                "width": advertised["width"],
                "height": advertised["height"],
                "fps": fps,
            })
    return modes


def build_camera_inventory(
    discover_devices,
    discover_csi_cameras,
    camera_identity,
):
    """Return every discovered camera and every mode its hardware advertises."""
    result = []
    for item in discover_devices():
        camera = {
            "kind": "usb",
            "device": item["device"],
            "physical_path": item.get("physical_path", ""),
            "label": f'USB · {item["device"]}',
            "modes": item["modes"],
        }
        identity = camera_identity(camera)
        result.append({
            **camera,
            "id": identity["id"],
            "stable_identity": identity["stable_identity"],
            "capture_modes": build_capture_modes(camera),
        })

    for item in discover_csi_cameras():
        camera = {
            "kind": "csi",
            "camera": item["index"],
            "sensor": item["sensor"],
            "device_path": item.get("device_path", ""),
            "label": f'CSI · {item["sensor"]} (camera {item["index"]})',
            "modes": item["modes"],
        }
        identity = camera_identity(camera)
        result.append({
            **camera,
            "id": identity["id"],
            "stable_identity": identity["stable_identity"],
            "capture_modes": build_capture_modes(camera),
        })
    return result
