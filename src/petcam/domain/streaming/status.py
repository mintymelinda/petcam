"""Pure streaming output state policy."""

from __future__ import annotations


def status_snapshot(service_active, status, now, stale_after=10):
    updated_at = status.get("updated_at")
    fresh = isinstance(updated_at, (int, float)) and now - updated_at <= stale_after
    state = status.get("state", "starting") if service_active else "stopped"
    if service_active and not fresh:
        state = "stalled"
    return {
        "service_active": service_active,
        "active": service_active and state == "publishing",
        "state": state,
        "fps": status.get("fps") if fresh else None,
        "updated_at": updated_at,
        "source": status.get("source") if fresh else None,
    }
