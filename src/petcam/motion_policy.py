"""Motion-detection configuration and decision policies, independent of worker I/O."""

DEFAULTS = {
    "enabled": False,
    "sample_interval_seconds": 2,
    "sensitivity": 50,
    "minimum_changed_percent": 2.5,
    "confirm_samples": 2,
    "min_event_interval_seconds": 60,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "retention_days": 14,
    "max_storage_mb": 512,
    "min_free_mb": 256,
    "max_events": 100,
}


def _clock(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("Quiet-hour times must use HH:MM.")
    hour, minute = value[:2], value[3:]
    if not hour.isdigit() or not minute.isdigit() or int(hour) > 23 or int(minute) > 59:
        raise ValueError("Quiet-hour times must be valid 24-hour HH:MM values.")
    return value


def validate_config(values):
    if not isinstance(values, dict):
        raise ValueError("Motion configuration must be an object.")
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown motion setting(s): " + ", ".join(sorted(unknown)))
    result = {**DEFAULTS, **values}
    if not isinstance(result["enabled"], bool) or not isinstance(result["quiet_hours_enabled"], bool):
        raise ValueError("enabled and quiet_hours_enabled must be true or false.")
    for key, low, high in (
        ("sample_interval_seconds", 1, 30),
        ("sensitivity", 1, 100),
        ("confirm_samples", 1, 5),
        ("min_event_interval_seconds", 5, 86400),
        ("retention_days", 1, 3650),
        ("max_storage_mb", 64, 102400),
        ("min_free_mb", 64, 102400),
        ("max_events", 1, 1000),
    ):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    value = result["minimum_changed_percent"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.1 <= value <= 20:
        raise ValueError("minimum_changed_percent must be between 0.1 and 20.")
    result["minimum_changed_percent"] = float(value)
    result["quiet_hours_start"] = _clock(result["quiet_hours_start"])
    result["quiet_hours_end"] = _clock(result["quiet_hours_end"])
    return result


def in_quiet_hours(now, start, end):
    if start == end:
        return False
    current = now.strftime("%H:%M")
    if start < end:
        return start <= current < end
    return current >= start or current < end


def pixel_delta_threshold(sensitivity):
    return max(8, 52 - round(sensitivity * 0.42))


def cooldown_elapsed(now, last_event, minimum_interval):
    return now - last_event >= minimum_interval
