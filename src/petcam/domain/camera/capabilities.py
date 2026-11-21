"""Parse the capture modes advertised by V4L2 and Raspberry Pi cameras."""

from __future__ import annotations

import re

FORMAT_RE = re.compile(r"\[\d+\]: '([^']+)'")
DISCRETE_SIZE_RE = re.compile(r"Size: Discrete (\d+)x(\d+)")
RANGE_SIZE_RE = re.compile(
    r"Size: (?:Stepwise|Continuous) (\d+)x(\d+) - (\d+)x(\d+)"
    r"(?: with step (\d+)/(\d+))?"
)
FPS_RE = re.compile(r"\(([\d.]+) fps\)")
FPS_RANGE_RE = re.compile(
    r"Interval: (?:Stepwise|Continuous) ([\d.]+)s - ([\d.]+)s"
    r"(?: with step ([\d.]+)s)?"
)
CSI_CAMERA_RE = re.compile(
    r"^\s*(\d+)\s*:\s*(\S+)\s*\[(\d+)x(\d+)\](?:\s+\(([^)]+)\))?"
)
CSI_MODE_RE = re.compile(r"(\d+)x(\d+)\s+\[([\d.]+)\s+fps")


def parse_v4l2_modes(output: str) -> list[dict]:
    """Return all V4L2 format/mode combinations reported by v4l2-ctl."""
    modes: list[dict] = []
    pixel_format = None
    current = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = FORMAT_RE.search(line)
        if match:
            pixel_format = match.group(1).upper()
            current = None
            continue
        match = DISCRETE_SIZE_RE.search(line)
        if match and pixel_format:
            current = {
                "format": pixel_format,
                "width": int(match.group(1)),
                "height": int(match.group(2)),
                "fps": [],
            }
            modes.append(current)
            continue
        match = RANGE_SIZE_RE.search(line)
        if match and pixel_format:
            min_width, min_height, max_width, max_height = map(int, match.groups()[:4])
            step_width, step_height = match.groups()[4:]
            current = {
                "format": pixel_format,
                "width": max_width,
                "height": max_height,
                "fps": [],
                "size_range": {
                    "min_width": min_width,
                    "min_height": min_height,
                    "max_width": max_width,
                    "max_height": max_height,
                    "step_width": int(step_width or 1),
                    "step_height": int(step_height or 1),
                },
            }
            modes.append(current)
            continue
        match = FPS_RE.search(line)
        if match and current:
            fps = float(match.group(1))
            if fps > 0 and fps not in current["fps"]:
                current["fps"].append(fps)
            continue
        match = FPS_RANGE_RE.search(line)
        if match and current:
            minimum_interval = float(match.group(1))
            maximum_interval = float(match.group(2))
            if minimum_interval > 0 and maximum_interval > 0:
                current["fps_range"] = {
                    "min": round(1 / maximum_interval, 3),
                    "max": round(1 / minimum_interval, 3),
                    "min_interval_seconds": minimum_interval,
                    "max_interval_seconds": maximum_interval,
                    "interval_step_seconds": float(match.group(3)) if match.group(3) else None,
                }
    for mode in modes:
        mode["fps"].sort(reverse=True)
    return modes


def parse_csi_cameras(output: str) -> list[dict]:
    """Parse rpicam-hello --list-cameras output into camera sensor modes."""
    cameras: list[dict] = []
    current = None
    for line in output.splitlines():
        match = CSI_CAMERA_RE.search(line)
        if match:
            current = {
                "index": int(match.group(1)),
                "sensor": match.group(2),
                "sensor_width": int(match.group(3)),
                "sensor_height": int(match.group(4)),
                "device_path": match.group(5) or "",
                "modes": [],
            }
            cameras.append(current)
            continue
        match = CSI_MODE_RE.search(line)
        if match and current:
            mode = {
                "width": int(match.group(1)),
                "height": int(match.group(2)),
                "fps": float(match.group(3)),
            }
            if mode not in current["modes"]:
                current["modes"].append(mode)
    return cameras


def mode_fps_values(mode: dict) -> list[float]:
    """Expand advertised discrete rates and representative values in a rate range."""
    values = [float(value) for value in mode.get("fps", []) if float(value) > 0]
    limits = mode.get("fps_range")
    if limits:
        minimum = float(limits["min"])
        maximum = float(limits["max"])
        values.extend((minimum, maximum))
        if minimum <= 30 <= maximum and mode_supports_fps(mode, 30.0):
            values.append(30.0)
    return sorted(set(values), reverse=True)


def mode_supports_fps(mode: dict, requested: float) -> bool:
    if any(abs(value - requested) < 0.1 for value in mode.get("fps", [])):
        return True
    limits = mode.get("fps_range")
    if not limits or not limits["min"] <= requested <= limits["max"]:
        return False
    step = limits.get("interval_step_seconds")
    if not step:
        return True
    interval = 1 / requested
    steps = (interval - limits["min_interval_seconds"]) / step
    return abs(steps - round(steps)) < 0.001
