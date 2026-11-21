"""Resolve and validate a requested camera capture mode against live hardware."""


def resolve_camera_selection(data, *, discover_cameras, mode_supports_fps):
    """Return the persisted camera settings for a currently advertised mode.

    This boundary owns request-to-device resolution and advertised-mode
    validation. Applying configuration and coordinating dependent services
    remain the responsibility of the camera configuration application service.
    """
    kind = data.get("kind")
    mode = data.get("mode") or {}
    mode_format = str(mode.get("format") or "auto").upper()
    if mode_format != "H264":
        raise ValueError("Only native USB H.264 camera modes are currently supported.")
    width, height, fps = mode.get("width"), mode.get("height"), mode.get("fps")
    if mode_format == "H264" and kind != "usb":
        raise ValueError("Native H.264 capture is available only for USB cameras.")
    if kind not in ("usb", "csi") or not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Invalid camera selection")
    if not (
        width > 0
        and height > 0
        and isinstance(fps, (int, float))
        and fps > 0
    ):
        raise ValueError("Invalid capture mode")

    discovered = discover_cameras()
    camera_id = data.get("camera_id")
    if camera_id:
        match = next(
            (
                item
                for item in discovered
                if item["kind"] == kind and item["id"] == camera_id
            ),
            None,
        )
    elif kind == "usb":
        physical_path = data.get("physical_path", "")
        device = data.get("device", "")
        match = next(
            (
                item
                for item in discovered
                if item["kind"] == "usb"
                and (
                    item.get("physical_path") == physical_path
                    if physical_path
                    else item["device"] == device
                )
            ),
            None,
        )
    else:
        device_path = data.get("device_path", "")
        camera = data.get("camera")
        match = next(
            (
                item
                for item in discovered
                if item["kind"] == "csi"
                and (
                    item.get("device_path") == device_path
                    if device_path
                    else item["camera"] == camera
                )
            ),
            None,
        )
    if not match:
        raise ValueError("Selected camera is no longer available.")

    if kind == "usb":
        if not any(
            item["width"] == width
            and item["height"] == height
            and item["format"] == mode.get("format")
            and mode_supports_fps(item, float(fps))
            for item in match["modes"]
        ):
            raise ValueError("That USB mode is no longer advertised by the camera")
        device = match["device"]
        physical_path = match.get("physical_path", "")
        return {
            "SOURCE": "usb",
            "DEVICE": (
                device
                if device.startswith("/dev/v4l/by-id/") or not physical_path
                else ""
            ),
            "USB_PHYSICAL_PATH": physical_path,
            "CSI_DEVICE_PATH": "",
            "CAMERA": "auto",
            "FORMAT": mode_format,
            "RESOLUTION": f"{width}x{height}",
            "FPS": str(int(fps)) if float(fps).is_integer() else str(fps),
        }

    if not any(
        item["width"] == width
        and item["height"] == height
        and abs(item["fps"] - fps) < 0.1
        for item in match["modes"]
    ):
        raise ValueError("That CSI mode is no longer advertised by the camera")
    device_path = match.get("device_path", "")
    return {
        "SOURCE": "csi",
        "DEVICE": "",
        "USB_PHYSICAL_PATH": "",
        "CSI_DEVICE_PATH": device_path,
        "CAMERA": "auto" if device_path else str(match["camera"]),
        "FORMAT": "auto",
        "RESOLUTION": f"{width}x{height}",
        "FPS": str(fps),
    }
