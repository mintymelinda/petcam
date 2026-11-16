"""Timelapse configuration and scheduling policy, independent of worker I/O."""

from pathlib import Path

DEFAULTS = {
    "enabled": False,
    "interval_seconds": 300,
    "schedule_start": "00:00",
    "schedule_end": "23:59",
    "retention_days": 30,
    "max_storage_mb": 2048,
    "min_free_mb": 256,
    "storage_path": "/var/lib/petcam/timelapse/frames",
    "max_width": 0,
    "jpeg_quality": 0,
}
NETWORK_ROOT = Path("/mnt/petcam-network")


def _clock(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("Schedule times must use HH:MM.")
    hour, minute = value[:2], value[3:]
    if not hour.isdigit() or not minute.isdigit() or int(hour) > 23 or int(minute) > 59:
        raise ValueError("Schedule times must use valid 24-hour HH:MM values.")
    return value


def validate_config(values):
    if not isinstance(values, dict):
        raise ValueError("Timelapse configuration must be an object.")
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown timelapse setting(s): " + ", ".join(sorted(unknown)))
    result = {**DEFAULTS, **values}
    if not isinstance(result["enabled"], bool):
        raise ValueError("enabled must be true or false.")
    for key, low, high in (
        ("interval_seconds", 60, 86400),
        ("retention_days", 1, 3650),
        ("max_storage_mb", 64, 102400),
        ("min_free_mb", 64, 102400),
    ):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    result["storage_path"] = str(result["storage_path"])
    storage_path = Path(result["storage_path"])
    allowed_roots = (Path("/var/lib/petcam").resolve(), NETWORK_ROOT.resolve())
    if not storage_path.is_absolute() or ".." in storage_path.parts:
        raise ValueError("storage_path must be an absolute path inside /var/lib/petcam or /mnt/petcam-network.")
    resolved_path = storage_path.resolve()
    if not any(resolved_path.is_relative_to(root) for root in allowed_roots):
        raise ValueError("storage_path must remain inside /var/lib/petcam or /mnt/petcam-network.")
    if resolved_path == NETWORK_ROOT.resolve():
        raise ValueError("storage_path must be a folder beneath /mnt/petcam-network, not the mount root.")
    for key, low, high in (("max_width", 0, 4096), ("jpeg_quality", 0, 95)):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    result["schedule_start"] = _clock(result["schedule_start"])
    result["schedule_end"] = _clock(result["schedule_end"])
    return result


def in_schedule(now, start, end):
    current = now.strftime("%H:%M")
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end
