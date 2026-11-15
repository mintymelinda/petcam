"""Camera capture-mode policy independent of hardware discovery."""

import re

if __package__:
    from .camera_capabilities import (
        NATIVE_H264_FORMATS,
        NATIVE_JPEG_FORMATS,
        USTREAMER_FORMATS,
        mode_max_fps,
        mode_supports_fps,
        mode_supports_resolution,
    )
else:  # Support the installed standalone camera worker entry point.
    from camera_capabilities import (
        NATIVE_H264_FORMATS,
        NATIVE_JPEG_FORMATS,
        USTREAMER_FORMATS,
        mode_max_fps,
        mode_supports_fps,
        mode_supports_resolution,
    )

PIXEL_BUDGETS = {
    "zero": 1280 * 720 * 30,
    "pi1": 640 * 480 * 30,
    "pi2": 1280 * 720 * 30,
    "zero2": 1920 * 1080 * 30,
    "pi3": 1920 * 1080 * 30,
    "pi4": 1920 * 1080 * 60,
    "pi5": 3840 * 2160 * 30,
    "unknown": 1280 * 720 * 30,
}


def select_csi_mode(cameras, tier, requested_camera=None, resolution="auto", fps="auto", requested_device_path=None):
    if requested_device_path:
        cameras = [camera for camera in cameras if camera.get("device_path") == requested_device_path]
    if requested_camera is not None:
        cameras = [camera for camera in cameras if camera["index"] == requested_camera]
    candidates = []
    for camera in cameras:
        for mode in camera["modes"]:
            candidates.append((
                mode["width"] * mode["height"] * mode["fps"],
                mode["width"] * mode["height"],
                mode["fps"],
                camera,
                mode,
            ))
    if not candidates:
        return None
    if resolution != "auto":
        match = re.fullmatch(r"(\d+)x(\d+)", resolution)
        if not match:
            raise ValueError("Resolution must be 'auto' or WIDTHxHEIGHT.")
        width, height = map(int, match.groups())
        candidates = [item for item in candidates if item[4]["width"] == width and item[4]["height"] == height]
        if not candidates:
            raise ValueError(f"CSI resolution {resolution} is not advertised by the selected camera.")
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except ValueError as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [item for item in candidates if abs(item[4]["fps"] - requested_fps) < 0.1]
        if not candidates:
            raise ValueError(f"CSI frame rate {fps} is not advertised for the selected resolution.")
    budget = PIXEL_BUDGETS[tier]
    within_budget = [item for item in candidates if item[0] <= budget]
    chosen = max(within_budget, key=lambda item: (item[1], item[2])) if within_budget else min(candidates, key=lambda item: item[0])
    camera, mode = chosen[3], chosen[4]
    return {
        "camera": camera["index"],
        "sensor": camera["sensor"],
        "device_path": camera.get("device_path", ""),
        "resolution": f'{mode["width"]}x{mode["height"]}',
        "fps": int(mode["fps"]) if mode["fps"].is_integer() else mode["fps"],
        "mode_fps": [item["fps"] for item in camera["modes"] if item["width"] == mode["width"] and item["height"] == mode["height"]],
        "estimated_pixels_per_second": chosen[0],
        "hardware_budget_pixels_per_second": budget,
        "performance_warning": chosen[0] > budget,
    }


def model_tier(model):
    value = model.lower()
    if "zero 2" in value or "zero 2 w" in value:
        return "zero2"
    if "zero" in value:
        return "zero"
    if "raspberry pi 1" in value or "raspberry pi model a" in value or "raspberry pi model b" in value:
        return "pi1"
    if "raspberry pi 2" in value:
        return "pi2"
    if "raspberry pi 5" in value or "raspberry pi 500" in value or "compute module 5" in value:
        return "pi5"
    if "raspberry pi 4" in value or "pi 400" in value or "compute module 4" in value:
        return "pi4"
    if "raspberry pi 3" in value or "compute module 3" in value:
        return "pi3"
    return "unknown"


def filter_devices_by_format(devices, requested_format):
    if requested_format == "auto":
        return devices
    requested_format = requested_format.upper()
    return [
        {**device, "modes": [mode for mode in device["modes"] if mode["format"] == requested_format]}
        for device in devices
        if any(mode["format"] == requested_format for mode in device["modes"])
    ]


def select_native_h264_mode(devices, resolution="auto", fps="auto"):
    """Select only an explicitly advertised V4L2 H.264 capture mode."""
    candidates = [
        (device, mode)
        for device in devices
        for mode in device["modes"]
        if mode["format"] in NATIVE_H264_FORMATS
    ]
    if resolution != "auto":
        match = re.fullmatch(r"(\d+)x(\d+)", resolution)
        if not match:
            raise ValueError("Resolution must be 'auto' or WIDTHxHEIGHT.")
        width, height = map(int, match.groups())
        candidates = [(device, mode) for device, mode in candidates
                      if mode_supports_resolution(mode, width, height)]
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except ValueError as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [(device, mode) for device, mode in candidates
                      if mode_supports_fps(mode, requested_fps)]
    if not candidates:
        return None
    device, mode = max(candidates, key=lambda item: (
        item[1]["width"] * item[1]["height"] * mode_max_fps(item[1]),
        item[1]["width"] * item[1]["height"],
    ))
    selected_fps = float(fps) if fps != "auto" else float(mode_max_fps(mode))
    return {
        "device": device["device"],
        "resolution": f'{mode["width"]}x{mode["height"]}',
        "fps": int(selected_fps) if selected_fps.is_integer() else selected_fps,
        "format": "H264",
    }


def select_mode(devices, tier):
    candidates = []
    for device in devices:
        for mode in device["modes"]:
            # Select only formats supported by µStreamer; discovery still lists
            # every advertised fourcc, including formats that cannot be streamed.
            if mode["format"] not in USTREAMER_FORMATS:
                continue
            fmt_rank = 0 if mode["format"] in NATIVE_JPEG_FORMATS else 1
            max_fps = mode_max_fps(mode)
            pixels_per_second = mode["width"] * mode["height"] * max_fps
            candidates.append((fmt_rank, pixels_per_second, mode["width"] * mode["height"], max_fps, device, mode))
    if not candidates:
        return None
    native = [item for item in candidates if item[0] == 0]
    pool = native or candidates
    budget = PIXEL_BUDGETS[tier]
    within_budget = [item for item in pool if item[1] <= budget]
    # If every advertised native mode exceeds the heuristic budget, start
    # with the least demanding one and warn; never hide a camera capability.
    chosen = max(within_budget, key=lambda item: (item[2], item[3])) if within_budget else min(pool, key=lambda item: item[1])
    return chosen[4], chosen[5], bool(native)
