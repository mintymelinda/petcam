"""Application service for validating and applying camera selections."""


def save_selection(
    data,
    *,
    discover_cameras,
    mode_supports_fps,
    pixel_budgets,
    model_tier,
    read_model,
    config_path,
    parse_config,
    load_rtmp_config,
    save_rtmp_config,
    load_timelapse_config,
    load_motion_config,
    check_gstreamer_runtime,
    run,
    set_rtmp_service,
    apply_config,
):
    """Validate a discovered capture mode and apply it with output rollback."""
    kind = data.get("kind")
    mode = data.get("mode") or {}
    mode_format = str(mode.get("format") or "auto").upper()
    width, height, fps = mode.get("width"), mode.get("height"), mode.get("fps")
    if mode_format == "H264" and kind != "usb":
        raise ValueError("Native H.264 capture is available only for USB cameras.")
    if kind not in ("usb", "csi") or not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Invalid camera selection")
    if not (1 <= width <= 10000 and 1 <= height <= 10000 and isinstance(fps, (int, float)) and 0 < fps <= 240):
        raise ValueError("Invalid capture mode")

    discovered = discover_cameras()
    camera_id = data.get("camera_id")
    if camera_id:
        match = next((item for item in discovered if item["kind"] == kind and item["id"] == camera_id), None)
    elif kind == "usb":
        physical_path = data.get("physical_path", "")
        device = data.get("device", "")
        match = next((
            item for item in discovered
            if item["kind"] == "usb" and (
                item.get("physical_path") == physical_path if physical_path else item["device"] == device
            )
        ), None)
    else:
        device_path = data.get("device_path", "")
        camera = data.get("camera")
        match = next((
            item for item in discovered
            if item["kind"] == "csi" and (
                item.get("device_path") == device_path if device_path else item["camera"] == camera
            )
        ), None)
    if not match:
        raise ValueError("Selected camera is no longer available.")

    if kind == "usb":
        if not float(fps).is_integer():
            raise ValueError("USB camera FPS must be a whole number")
        if not any(
            item["width"] == width and item["height"] == height
            and item["format"] == mode.get("format")
            and mode_supports_fps(item, float(fps))
            for item in match["modes"]
        ):
            raise ValueError("That USB mode is no longer advertised by the camera")
        device = match["device"]
        physical_path = match.get("physical_path", "")
        values = {
            "SOURCE": "usb",
            "DEVICE": device if device.startswith("/dev/v4l/by-id/") or not physical_path else "",
            "USB_PHYSICAL_PATH": physical_path,
            "CSI_DEVICE_PATH": "",
            "CAMERA": "auto",
            "FORMAT": mode_format,
            "RESOLUTION": f"{width}x{height}",
            "FPS": str(int(fps)),
        }
    else:
        if not any(
            item["width"] == width and item["height"] == height and abs(item["fps"] - fps) < 0.1
            for item in match["modes"]
        ):
            raise ValueError("That CSI mode is no longer advertised by the camera")
        device_path = match.get("device_path", "")
        values = {
            "SOURCE": "csi",
            "DEVICE": "",
            "USB_PHYSICAL_PATH": "",
            "CSI_DEVICE_PATH": device_path,
            "CAMERA": "auto" if device_path else str(match["camera"]),
            "FORMAT": "auto",
            "RESOLUTION": f"{width}x{height}",
            "FPS": str(fps),
        }
    estimated_pixels_per_second = width * height * float(fps)
    pixel_budget = pixel_budgets[model_tier(read_model())]
    if values["FORMAT"] != "H264" and estimated_pixels_per_second > pixel_budget and data.get("allow_performance_override") is not True:
        raise ValueError(
            "This capture mode exceeds the estimated performance budget for this device. "
            "Confirm the warning to use it anyway, or choose a lower resolution or FPS."
        )
    requested_h264 = values["FORMAT"] == "H264"
    previous_camera = parse_config(config_path)
    previous_rtmp = load_rtmp_config()
    rtmp_was_active = False
    if requested_h264 or previous_rtmp["enabled"]:
        rtmp_was_active = run(
            ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
            check=False, timeout=5,
        ).returncode == 0

    if requested_h264:
        if load_timelapse_config().get("enabled") or load_motion_config().get("enabled"):
            raise ValueError("Disable timelapse and motion detection before selecting H.264; both require the MJPEG capture feed.")
        try:
            check_gstreamer_runtime()
        except ValueError as error:
            raise RuntimeError(str(error)) from error

    camera_applied = False
    try:
        if requested_h264 or previous_camera.get("FORMAT") == "H264":
            if rtmp_was_active:
                set_rtmp_service("disable")
        if requested_h264:
            save_rtmp_config({**previous_rtmp, "enabled": True})
        updated = apply_config(values)
        camera_applied = True
        current_rtmp = load_rtmp_config()
        if current_rtmp["enabled"]:
            set_rtmp_service("enable" if requested_h264 or previous_camera.get("FORMAT") == "H264" or not rtmp_was_active else "restart")
        elif rtmp_was_active:
            set_rtmp_service("disable")
        return updated
    except Exception:
        if requested_h264:
            save_rtmp_config(previous_rtmp)
        if camera_applied:
            try:
                if previous_camera.get("FORMAT") == "H264":
                    set_rtmp_service("disable")
                apply_config(previous_camera)
                if previous_rtmp["enabled"]:
                    set_rtmp_service("enable")
                elif rtmp_was_active:
                    set_rtmp_service("disable")
            except Exception as rollback_error:
                raise RuntimeError(f"Camera selection failed and restoring the previous camera/output settings also failed: {rollback_error}")
        elif rtmp_was_active and previous_rtmp["enabled"]:
            set_rtmp_service("enable")
        raise
