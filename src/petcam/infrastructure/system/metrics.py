"""Read CPU and memory statistics from Linux procfs without extra packages."""

from __future__ import annotations


class ResourceMetrics:
    def __init__(self):
        self._previous = None

    def sample(self) -> dict:
        cpu_percent = None
        try:
            with open("/proc/stat", encoding="ascii") as source:
                values = [int(value) for value in source.readline().split()[1:]]
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            previous = self._previous
            self._previous = (total, idle)
            if previous:
                total_delta = total - previous[0]
                idle_delta = idle - previous[1]
                if total_delta > 0:
                    cpu_percent = round(max(0, min(100, (total_delta - idle_delta) * 100 / total_delta)), 1)
        except (OSError, ValueError, IndexError):
            pass

        memory = {}
        try:
            with open("/proc/meminfo", encoding="ascii") as source:
                for line in source:
                    key, value = line.split(":", 1)
                    if key in {"MemTotal", "MemAvailable"}:
                        memory[key] = int(value.split()[0])
            total_mb = round(memory["MemTotal"] / 1024)
            used_mb = round((memory["MemTotal"] - memory["MemAvailable"]) / 1024)
        except (OSError, ValueError, IndexError, KeyError):
            used_mb = total_mb = None
        return {
            "cpu_percent": cpu_percent,
            "memory_used_mb": used_mb,
            "memory_total_mb": total_mb,
        }
