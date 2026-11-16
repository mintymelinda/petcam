"""Resolve explicitly requested camera modes against discovered hardware."""

import re

from .capabilities import (
    NATIVE_H264_FORMATS,
    NATIVE_JPEG_FORMATS,
    mode_max_fps,
    mode_supports_fps,
    mode_supports_resolution,
)


def select_csi_mode(cameras, _tier=None, requested_camera=None, resolution="auto", fps="auto", requested_device_path=None):
    """Return the first advertised CSI mode matching the supplied constraints."""
    if requested_device_path:
        cameras = [camera for camera in cameras if camera.get("device_path") == requested_device_path]
    if requested_camera is not None:
        cameras = [camera for camera in cameras if camera["index"] == requested_camera]
    candidates = [
        (camera, mode)
        for camera in cameras
        for mode in camera["modes"]
    ]
    if resolution != "auto":
        match = re.fullmatch(r"(\d+)x(\d+)", resolution)
        if not match:
            raise ValueError("Resolution must be 'auto' or WIDTHxHEIGHT.")
        width, height = map(int, match.groups())
        candidates = [
            item for item in candidates
            if item[1]["width"] == width and item[1]["height"] == height
        ]
        if not candidates:
            raise ValueError(f"CSI resolution {resolution} is not advertised by the selected camera.")
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except ValueError as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [
            item for item in candidates
            if abs(item[1]["fps"] - requested_fps) < 0.1
        ]
        if not candidates:
            raise ValueError(f"CSI frame rate {fps} is not advertised for the selected resolution.")
    if not candidates:
        return None

    camera, mode = candidates[0]
    selected_fps = mode["fps"]
    return {
        "camera": camera["index"],
        "sensor": camera["sensor"],
        "device_path": camera.get("device_path", ""),
        "resolution": f'{mode["width"]}x{mode["height"]}',
        "fps": int(selected_fps) if float(selected_fps).is_integer() else selected_fps,
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
        candidates = [
            (device, mode) for device, mode in candidates
            if mode_supports_resolution(mode, width, height)
        ]
    if fps != "auto":
        try:
            requested_fps = float(fps)
        except ValueError as error:
            raise ValueError("FPS must be 'auto' or a positive number.") from error
        if requested_fps <= 0:
            raise ValueError("FPS must be 'auto' or a positive number.")
        candidates = [
            (device, mode) for device, mode in candidates
            if mode_supports_fps(mode, requested_fps)
        ]
    if not candidates:
        return None
    device, mode = candidates[0]
    selected_fps = float(fps) if fps != "auto" else float(mode_max_fps(mode))
    return {
        "device": device["device"],
        "resolution": f'{mode["width"]}x{mode["height"]}',
        "fps": int(selected_fps) if selected_fps.is_integer() else selected_fps,
        "format": "H264",
    }


def select_mode(devices, _tier=None):
    """Return the first advertised mode; never rank or suppress hardware modes."""
    for device in devices:
        for mode in device["modes"]:
            return device, mode, mode["format"] in NATIVE_JPEG_FORMATS
    return None
