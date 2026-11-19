"""Authenticated system configuration routes."""

from urllib.parse import urlparse


def handle_post(handler, services, data):
    if urlparse(handler.path).path != "/api/web-ui":
        return False
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    services.set_web_ui_enabled(enabled)
    handler.send_json(200, {
        "ok": True,
        "enabled": enabled,
        "setup_path": "/setup",
    })
    return True
