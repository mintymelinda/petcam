"""Low-cost Linux system telemetry and installed application version reporting."""

from pathlib import Path
import threading
import time


_cpu_lock = threading.Lock()
_cpu_sample = None


def resource_metrics():
    """Return low-cost CPU and memory usage from Linux procfs."""
    global _cpu_sample
    cpu_percent = None
    try:
        with open("/proc/stat", encoding="ascii") as source:
            fields = source.readline().split()[1:]
        values = [int(value) for value in fields]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        now = time.monotonic()
        with _cpu_lock:
            previous = _cpu_sample
            _cpu_sample = (total, idle, now)
        if previous:
            total_delta = total - previous[0]
            idle_delta = idle - previous[1]
            if total_delta > 0:
                cpu_percent = round(max(0.0, min(100.0, (total_delta - idle_delta) * 100.0 / total_delta)), 1)
    except (OSError, ValueError, IndexError):
        pass
    memory = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as source:
            for line in source:
                key, value = line.split(":", 1)
                if key in ("MemTotal", "MemAvailable"):
                    memory[key] = int(value.split()[0])
        total_kib = memory.get("MemTotal")
        available_kib = memory.get("MemAvailable")
        if total_kib is not None and available_kib is not None:
            total_mb = round(total_kib / 1024)
            used_mb = round(max(0, total_kib - available_kib) / 1024)
        else:
            total_mb = used_mb = None
    except (OSError, ValueError, IndexError):
        total_mb = used_mb = None
    return {"cpu_percent": cpu_percent, "memory_used_mb": used_mb, "memory_total_mb": total_mb}


def installed_version(application_file):
    """Read the VERSION file belonging to the active, resolved application release."""
    version_file = Path(application_file).resolve().parent.parent / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").strip()
        return version or None
    except OSError:
        return None
