"""Pure camera identity and capability parsing helpers."""

import hashlib
import re

MODE_RE = re.compile(r"Size: Discrete (\d+)x(\d+)")
FORMAT_RE = re.compile(r"\[\d+\]: '([^']+)'")
FPS_RE = re.compile(r"\(([\d.]+) fps\)")
SIZE_RANGE_RE = re.compile(r"Size: (?:Stepwise|Continuous) (\d+)x(\d+) - (\d+)x(\d+)(?: with step (\d+)/(\d+))?")
FPS_RANGE_RE = re.compile(r"Interval: (?:Stepwise|Continuous) ([\d.]+)s - ([\d.]+)s(?: with step ([\d.]+)s)?")
NATIVE_JPEG_FORMATS = {"MJPG", "MJPEG", "JPEG"}
NATIVE_H264_FORMATS = {"H264"}
USTREAMER_FORMATS = NATIVE_JPEG_FORMATS | {"YUYV", "YVYU", "UYVY", "YUV420", "YVU420", "RGB565", "RGB24", "GREY"}
NATIVE_JPEG_FORMATS = {"MJPG", "MJPEG", "JPEG"}
NATIVE_H264_FORMATS = {"H264"}
USTREAMER_FORMATS = NATIVE_JPEG_FORMATS | {"YUYV", "YVYU", "UYVY", "YUV420", "YVU420", "RGB565", "RGB24", "GREY"}

def _camera_slug(value):
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-") or "camera"


def camera_identity(camera):
    """Return a stable identifier for a discovered physical camera."""
    kind = camera.get("kind")
    if kind == "usb":
        device = str(camera.get("device", ""))
        if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+-]+)", device):
            raise ValueError("USB camera has no valid device path.")
        physical_path = str(camera.get("physical_path", ""))
        stable = device.startswith("/dev/v4l/by-id/") or bool(physical_path)
        source = device if device.startswith("/dev/v4l/by-id/") else physical_path or device
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
        return {
            "id": f"usb-{digest}",
            "kind": "usb",
            "device": device,
            "physical_path": physical_path,
            "stable_identity": stable,
            "label": camera.get("label") or f"USB camera · {device}",
        }
    if kind == "csi":
        sensor = _camera_slug(str(camera.get("sensor", "csi")))
        index = camera.get("camera")
        device_path = str(camera.get("device_path", ""))
        if not isinstance(index, int) or index < 0:
            raise ValueError("CSI camera index is invalid.")
        digest = hashlib.sha256(f"{sensor}|{device_path}".encode("utf-8")).hexdigest()[:12]
        return {
            "id": f"csi-{digest}" if device_path else f"csi-{sensor}-{index}",
            "kind": "csi",
            "camera": index,
            "sensor": sensor,
            "device_path": device_path,
            "stable_identity": bool(device_path),
            "label": camera.get("label") or f"CSI {sensor} · camera {index}",
        }
    raise ValueError("Camera type must be usb or csi.")


def parse_modes(output):
    modes = []
    current_format = None
    current_mode = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        fmt = FORMAT_RE.search(line)
        if fmt:
            current_format = fmt.group(1).upper()
            current_mode = None
            continue
        size = MODE_RE.search(line)
        if size and current_format:
            current_mode = {
                "format": current_format,
                "width": int(size.group(1)),
                "height": int(size.group(2)),
                "fps": [],
            }
            modes.append(current_mode)
            continue
        size_range = SIZE_RANGE_RE.search(line)
        if size_range and current_format:
            min_w, min_h, max_w, max_h = map(int, size_range.groups()[:4])
            step_w, step_h = size_range.groups()[4:]
            current_mode = {
                "format": current_format,
                "width": max_w,
                "height": max_h,
                "fps": [],
                "size_range": {
                    "min_width": min_w, "min_height": min_h,
                    "max_width": max_w, "max_height": max_h,
                    "step_width": int(step_w or 1), "step_height": int(step_h or 1),
                },
            }
            modes.append(current_mode)
            continue
        fps = FPS_RE.search(line)
        if fps and current_mode:
            value = float(fps.group(1))
            if value > 0 and value not in current_mode["fps"]:
                current_mode["fps"].append(value)
            continue
        fps_range = FPS_RANGE_RE.search(line)
        if fps_range and current_mode:
            min_interval, max_interval = float(fps_range.group(1)), float(fps_range.group(2))
            if min_interval > 0 and max_interval > 0:
                current_mode["fps_range"] = {
                    "min": round(1 / max_interval, 3),
                    "max": round(1 / min_interval, 3),
                    "min_interval_seconds": min_interval,
                    "max_interval_seconds": max_interval,
                    "interval_step_seconds": float(fps_range.group(3)) if fps_range.group(3) else None,
                }
    for mode in modes:
        mode["fps"].sort(reverse=True)
    return modes


def mode_supports_resolution(mode, width, height):
    if mode["width"] == width and mode["height"] == height:
        return True
    bounds = mode.get("size_range")
    if not bounds:
        return False
    return (
        bounds["min_width"] <= width <= bounds["max_width"]
        and bounds["min_height"] <= height <= bounds["max_height"]
        and (width - bounds["min_width"]) % bounds["step_width"] == 0
        and (height - bounds["min_height"]) % bounds["step_height"] == 0
    )


def mode_max_fps(mode):
    return max(mode["fps"], default=mode.get("fps_range", {}).get("max", 30.0))


def mode_supports_fps(mode, fps):
    if any(abs(value - fps) < 0.1 for value in mode["fps"]):
        return True
    limits = mode.get("fps_range")
    if not limits or not limits["min"] <= fps <= limits["max"]:
        return False
    interval = 1 / fps
    step = limits["interval_step_seconds"]
    if step:
        steps = (interval - limits["min_interval_seconds"]) / step
        return abs(steps - round(steps)) < 0.001
    return limits["min_interval_seconds"] <= interval <= limits["max_interval_seconds"]

CSI_CAMERA_RE = re.compile(r"^\s*(\d+)\s*:\s*(\S+)\s*\[(\d+)x(\d+)\](?:\s+\(([^)]+)\))?")
CSI_MODE_RE = re.compile(r"(\d+)x(\d+)\s+\[([\d.]+)\s+fps")


def parse_csi_cameras(output):
    cameras = []
    current = None
    for line in output.splitlines():
        camera_match = CSI_CAMERA_RE.search(line)
        if camera_match:
            current = {
                "index": int(camera_match.group(1)),
                "sensor": camera_match.group(2),
                "sensor_width": int(camera_match.group(3)),
                "sensor_height": int(camera_match.group(4)),
                "device_path": camera_match.group(5) or "",
                "modes": [],
            }
            cameras.append(current)
            continue
        mode_match = CSI_MODE_RE.search(line)
        if mode_match and current:
            mode = {
                "width": int(mode_match.group(1)),
                "height": int(mode_match.group(2)),
                "fps": float(mode_match.group(3)),
            }
            if mode not in current["modes"]:
                current["modes"].append(mode)
    return cameras


def ustreamer_format(pixel_format):
    """Translate V4L2 native JPEG fourcc values to µStreamer passthrough format."""
    return "MJPEG" if pixel_format in NATIVE_JPEG_FORMATS else pixel_format
