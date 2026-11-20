"""Resolve camera modes deterministically against discovered hardware capabilities."""

import re

from .capabilities import NATIVE_JPEG_FORMATS, mode_supports_fps, mode_supports_resolution

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 30.0


def _format_rank(pixel_format):
    pixel_format = str(pixel_format).upper()
    if pixel_format == "H264":
        return 0
    if pixel_format in NATIVE_JPEG_FORMATS:
        return 1
    return 2


def _resolution_distance(mode):
    return abs(int(mode["width"]) - DEFAULT_WIDTH) + abs(int(mode["height"]) - DEFAULT_HEIGHT)


def _mode_fps(mode, requested="auto"):
    if requested != "auto":
        try:
            value = float(requested)
        except (TypeError, ValueError) as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if value <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        if not mode_supports_fps(mode, value):
            raise ValueError(f"Requested {value} FPS is not advertised for this camera mode.")
        return value
    advertised = mode.get("fps", [])
    if advertised:
        return min((float(value) for value in advertised), key=lambda value: (abs(value - DEFAULT_FPS), -value))
    limits = mode.get("fps_range")
    if limits:
        return min(max(DEFAULT_FPS, limits["min"]), limits["max"])
    return DEFAULT_FPS


def select_csi_mode(cameras, requested_camera=None, resolution="auto", fps="auto", requested_device_path=None):
    """Prefer CSI 720p30; otherwise choose the closest advertised mode deterministically."""
    if requested_device_path:
        cameras = [camera for camera in cameras if camera.get("device_path") == requested_device_path]
    if requested_camera is not None:
        cameras = [camera for camera in cameras if camera["index"] == requested_camera]
    candidates = [(camera, mode) for camera in cameras for mode in camera["modes"]]
    if resolution != "auto":
        match = re.fullmatch(r"(\d+)x(\d+)", str(resolution))
        if not match:
            raise ValueError("Resolution must be 'auto' or WIDTHxHEIGHT.")
        width, height = map(int, match.groups())
        candidates = [item for item in candidates if mode_supports_resolution(item[1], width, height)]
        if not candidates:
            raise ValueError(f"CSI resolution {resolution} is not advertised by the selected camera.")
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except (TypeError, ValueError) as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [item for item in candidates if abs(float(item[1]["fps"]) - requested_fps) < 0.1]
        if not candidates:
            raise ValueError(f"CSI frame rate {fps} is not advertised for the selected resolution.")
    if not candidates:
        return None
    camera, mode = min(candidates, key=lambda item: (
        _resolution_distance(item[1]),
        abs(float(item[1]["fps"]) - DEFAULT_FPS),
        int(item[0]["index"]),
        int(item[1]["width"]),
        int(item[1]["height"]),
        float(item[1]["fps"]),
    ))
    selected_fps = float(mode["fps"])
    return {
        "camera": camera["index"],
        "sensor": camera["sensor"],
        "device_path": camera.get("device_path", ""),
        "resolution": f'{mode["width"]}x{mode["height"]}',
        "fps": int(selected_fps) if selected_fps.is_integer() else selected_fps,
        "mode_fps": [
            item["fps"] for item in camera["modes"]
            if item["width"] == mode["width"] and item["height"] == mode["height"]
        ],
    }


def filter_devices_by_format(devices, requested_format):
    """Narrow discovered devices only when the caller explicitly names a format."""
    if requested_format == "auto":
        return devices
    requested_format = requested_format.upper()
    return [
        {**device, "modes": [mode for mode in device["modes"] if mode["format"] == requested_format]}
        for device in devices
        if any(mode["format"] == requested_format for mode in device["modes"])
    ]


def select_mode(devices, resolution="auto", fps="auto"):
    """Prefer H.264 720p30, then JPEG, then other formats with stable fallbacks."""
    candidates = [(device, mode) for device in devices for mode in device["modes"]]
    if resolution != "auto":
        match = re.fullmatch(r"(\d+)x(\d+)", str(resolution))
        if not match:
            raise ValueError("Resolution must be 'auto' or WIDTHxHEIGHT.")
        width, height = map(int, match.groups())
        candidates = [item for item in candidates if mode_supports_resolution(item[1], width, height)]
        if not candidates:
            raise ValueError(f"Requested resolution {resolution} is not advertised by the selected camera.")
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except (TypeError, ValueError) as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [item for item in candidates if mode_supports_fps(item[1], requested_fps)]
        if not candidates:
            raise ValueError(f"Requested frame rate {fps} is not advertised by the selected camera.")
    if not candidates:
        return None
    device, mode = min(candidates, key=lambda item: (
        _format_rank(item[1]["format"]),
        _resolution_distance(item[1]),
        abs(_mode_fps(item[1]) - DEFAULT_FPS),
        str(item[0].get("device", "")),
        int(item[1]["width"]),
        int(item[1]["height"]),
        str(item[1]["format"]),
    ))
    return device, mode, mode["format"] in {"MJPG", "MJPEG", "JPEG"}


def select_mode_fps(mode, requested="auto"):
    """Resolve FPS, preferring 30 over the mode's maximum rate."""
    return _mode_fps(mode, requested)
