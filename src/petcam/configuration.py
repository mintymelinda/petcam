"""Validate the camera parameters used by the H.264 RTSP session."""

from __future__ import annotations

import re
from typing import Any

RESOLUTION_RE = re.compile(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})")


class ConfigurationError(ValueError):
    """Raised when the requested camera mode is invalid."""


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError("Camera configuration must be an object.")
    source = str(value.get("source", "")).upper()
    if source not in {"USB", "CSI"}:
        raise ConfigurationError("Capture mode must be USB or CSI.")
    resolution = str(value.get("resolution", ""))
    if not RESOLUTION_RE.fullmatch(resolution):
        raise ConfigurationError("Resolution must use WIDTHxHEIGHT format.")
    try:
        fps = float(value.get("fps"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("Frame rate must be a positive number.") from error
    if not 0 < fps <= 1000:
        raise ConfigurationError("Frame rate must be greater than 0 and no more than 1000 FPS.")
    normalized: dict[str, Any] = {
        "source": source,
        "resolution": resolution,
        "fps": int(fps) if fps.is_integer() else fps,
    }
    if source == "USB":
        device = str(value.get("device", ""))
        if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+-]+)", device):
            raise ConfigurationError("USB camera device path is invalid.")
        normalized["device"] = device
        normalized["physical_path"] = str(value.get("physical_path", ""))
    else:
        try:
            camera = int(value.get("camera"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError("CSI camera index is invalid.") from error
        if camera < 0:
            raise ConfigurationError("CSI camera index cannot be negative.")
        normalized["camera"] = camera
        normalized["sensor"] = str(value.get("sensor", ""))
        normalized["device_path"] = str(value.get("device_path", ""))
    return normalized
