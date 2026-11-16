#!/usr/bin/env python3
"""Optional, dependency-free MQTT discovery publisher for Home Assistant."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import ssl
import struct
import subprocess
import sys
import time
from pathlib import Path

from petcam.infrastructure.mqtt.client import MQTTClient, MQTTError
from urllib.parse import urlsplit

from petcam.infrastructure.persistence.configuration import parse_config

CONFIG_FILE = Path("/etc/petcam/home-assistant.conf")
HEALTH_FILE = Path("/var/lib/petcam/health.json")
LIGHT_SENSOR_FILE = Path("/var/lib/petcam/light-sensor.json")
DEFAULTS = {
    "MQTT_ENABLED": "false",
    "MQTT_HOST": "",
    "MQTT_PORT": "1883",
    "MQTT_USERNAME": "",
    "MQTT_PASSWORD": "",
    "MQTT_TLS": "false",
    "MQTT_CLIENT_ID": "",
    "MQTT_DISCOVERY_PREFIX": "homeassistant",
    "MQTT_TOPIC_PREFIX": "petcam",
    "MQTT_PUBLISH_STREAM_URL": "false",
    "MQTT_STREAM_URL": "",
}
POLL_SECONDS = 30
KEEPALIVE_SECONDS = 60
_STOP = False



def _bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise MQTTError(f"{key} must be true or false.")
    return normalized == "true"


def load_config(path: Path = CONFIG_FILE) -> dict[str, object]:
    values = dict(DEFAULTS)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {**values, "MQTT_ENABLED": False, "MQTT_TLS": False, "MQTT_PUBLISH_STREAM_URL": False}
    except OSError as error:
        raise MQTTError(f"Unable to read Home Assistant MQTT configuration: {error}") from error
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise MQTTError(f"Invalid setting on line {number}.")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in values:
            raise MQTTError(f"Unknown Home Assistant MQTT setting: {key}.")
        if "\n" in value or "\r" in value:
            raise MQTTError(f"Invalid value for {key}.")
        values[key] = value

    enabled = _bool(str(values["MQTT_ENABLED"]), "MQTT_ENABLED")
    tls = _bool(str(values["MQTT_TLS"]), "MQTT_TLS")
    publish_url = _bool(str(values["MQTT_PUBLISH_STREAM_URL"]), "MQTT_PUBLISH_STREAM_URL")
    try:
        port = int(str(values["MQTT_PORT"]))
    except ValueError as error:
        raise MQTTError("MQTT_PORT must be an integer.") from error
    if not 1 <= port <= 65535:
        raise MQTTError("MQTT_PORT must be between 1 and 65535.")
    host = str(values["MQTT_HOST"]).strip()
    if enabled and (not host or any(char.isspace() for char in host)):
        raise MQTTError("MQTT_HOST is required when MQTT_ENABLED=true.")
    for key in ("MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_CLIENT_ID"):
        if any(char in str(values[key]) for char in "\r\n\x00"):
            raise MQTTError(f"{key} contains an invalid control character.")
    if values["MQTT_PASSWORD"] and not values["MQTT_USERNAME"]:
        raise MQTTError("MQTT_PASSWORD requires MQTT_USERNAME.")
    for key in ("MQTT_DISCOVERY_PREFIX", "MQTT_TOPIC_PREFIX"):
        value = str(values[key]).strip("/")
        if not value or any(char in value for char in "+#\x00"):
            raise MQTTError(f"{key} must be a valid MQTT topic prefix.")
        values[key] = value
    stream_url = str(values["MQTT_STREAM_URL"]).strip()
    if stream_url:
        parsed = urlsplit(stream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MQTTError("MQTT_STREAM_URL must be an absolute HTTP or HTTPS URL.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise MQTTError("MQTT_STREAM_URL must not contain credentials, query parameters, or fragments.")
    if publish_url and not stream_url:
        try:
            hostname = socket.gethostname().strip()
        except OSError:
            hostname = "petcam"
        stream_url = f"http://{hostname}.local:8080/stream"
    values.update({
        "MQTT_ENABLED": enabled,
        "MQTT_TLS": tls,
        "MQTT_PUBLISH_STREAM_URL": publish_url,
        "MQTT_PORT": port,
        "MQTT_HOST": host,
        "MQTT_STREAM_URL": stream_url,
    })
    return values


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def collect_snapshot(config: dict[str, object], health: dict | None = None) -> dict[str, str]:
    health = health if health is not None else _read_json(HEALTH_FILE)
    try:
        active = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "petcam-stream.service"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip() == "active"
    except (OSError, subprocess.TimeoutExpired):
        active = False
    try:
        log = subprocess.run(
            ["/usr/bin/journalctl", "-u", "petcam-stream.service", "-n", "120", "--no-pager"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        log = ""
    backends = re.findall(r"PetCam backend: (usb|csi)", log)
    active_backend = backends[-1] if backends else str(config.get("SOURCE", "unknown"))
    camera_connected = health.get("camera_connected")
    public_ready = health.get("public_stream_ready")
    backend_ready = health.get("backend_stream_ready")
    health_state = str(health.get("state", "not_checked"))
    resolution = str(config.get("RESOLUTION", "auto"))
    fps = str(config.get("FPS", "auto"))
    capture_format = str(config.get("FORMAT", "auto"))
    mode = f"{resolution} @ {fps} fps"
    if capture_format != "auto":
        mode += f" · {capture_format}"
    light = _read_json(LIGHT_SENSOR_FILE)
    light_state = str(light.get("state", "unknown")).lower()
    ambient_light = light_state.upper() if light_state in {"bright", "dark"} else "UNKNOWN"
    return {
        "ambient_light": ambient_light,
        "illuminance": str(light.get("illuminance_lux", "unknown")) if light.get("available") else "unknown",
        "service_active": "ON" if active else "OFF",
        "health_available": "ON" if active and health_state in {"healthy", "camera_disconnected", "starting", "configuring"} else "OFF",
        "camera_connected": "ON" if camera_connected is True else ("OFF" if camera_connected is False else "UNKNOWN"),
        "stream_ready": "ON" if active and public_ready is True and backend_ready is True else "OFF",
        "health_state": health_state,
        "active_backend": active_backend,
        "active_mode": mode,
        "stream_url": str(config.get("MQTT_STREAM_URL", "")) if config.get("MQTT_PUBLISH_STREAM_URL") else "",
        "health_reason": str(health.get("reason", "")),
    }


ENTITIES = [
    {"component": "binary_sensor", "object_id": "camera_connected", "name": "Camera connected", "device_class": "connectivity"},
    {"component": "binary_sensor", "object_id": "stream_ready", "name": "Stream ready", "device_class": "connectivity"},
    {"component": "binary_sensor", "object_id": "ambient_light", "name": "Ambient light", "device_class": "light", "payload_on": "BRIGHT", "payload_off": "DARK"},
    {"component": "sensor", "object_id": "illuminance", "name": "Illuminance", "device_class": "illuminance", "unit_of_measurement": "lx", "state_class": "measurement"},
    {"component": "sensor", "object_id": "health_state", "name": "Health state", "icon": "mdi:heart-pulse"},
    {"component": "sensor", "object_id": "active_backend", "name": "Active backend"},
    {"component": "sensor", "object_id": "active_mode", "name": "Active mode"},
    {"component": "sensor", "object_id": "stream_url", "name": "OBS stream URL", "entity_category": "diagnostic"},
    {"component": "sensor", "object_id": "health_reason", "name": "Health reason", "entity_category": "diagnostic"},
]


def publish_once(client: MQTTClient, config: dict[str, object]) -> None:
    try:
        petcam = parse_config()
    except Exception:
        petcam = {}
    snapshot = collect_snapshot({**petcam, **config})
    hostname = socket.gethostname()
    try:
        model = Path("/proc/device-tree/model").read_text(encoding="utf-8").strip("\x00\n ")
    except OSError:
        model = "Raspberry Pi"
    node_id = _node_identifier(config)
    entities = ENTITIES if config.get("MQTT_PUBLISH_STREAM_URL") else [
        entity for entity in ENTITIES if entity["object_id"] != "stream_url"
    ]
    client.publish_discovery(node_id, hostname, model, entities)
    if not config.get("MQTT_PUBLISH_STREAM_URL"):
        topic = f"{config['MQTT_DISCOVERY_PREFIX']}/sensor/{node_id}/stream_url/config"
        client.publish(topic, "")
    client.publish_availability("online")
    client.publish(client._topic("health_availability"), "healthy" if snapshot["health_available"] == "ON" else "unhealthy")
    client.publish_state({key: value for key, value in snapshot.items() if key != "health_available" and key != "service_active" and (key != "stream_url" or config.get("MQTT_PUBLISH_STREAM_URL"))})


def run(config: dict[str, object] | None = None, stop=lambda: _STOP, sleep=time.sleep) -> int:
    settings = config if config is not None else load_config()
    if not settings["MQTT_ENABLED"]:
        print("Home Assistant MQTT integration is disabled.", flush=True)
        return 0
    delay = 5
    while not stop():
        client = MQTTClient(settings)
        try:
            client.connect()
            client.publish_availability("online")
            last_publish = 0.0
            while not stop():
                now = time.monotonic()
                if now - last_publish >= POLL_SECONDS:
                    publish_once(client, settings)
                    last_publish = now
                sleep(5)
                client.ping()
                delay = 5
        except (OSError, MQTTError, ssl.SSLError, subprocess.SubprocessError) as error:
            print(f"Home Assistant MQTT connection unavailable: {error}", file=sys.stderr, flush=True)
        finally:
            client.close(graceful=not stop())
        if not stop():
            sleep(delay)
            delay = min(delay * 2, 300)
    return 0


def _stop_handler(_signum, _frame):
    global _STOP
    _STOP = True


def remove_discovery(config: dict[str, object]) -> None:
    if not config["MQTT_HOST"]:
        raise MQTTError("MQTT_HOST must be configured before removing Home Assistant discovery entities.")
    client = MQTTClient(config)
    client.connect()
    try:
        node_id = _node_identifier(config)
        for entity in ENTITIES:
            topic = f"{config['MQTT_DISCOVERY_PREFIX']}/{entity['component']}/{node_id}/{entity['object_id']}/config"
            client.publish(topic, "")
            client.publish(client._topic(f"state/{entity['object_id']}"), "")
        client.publish(client._topic("health_availability"), "")
        client.publish_availability("offline")
    finally:
        client.close()


def main() -> int:
    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    try:
        if sys.argv[1:] == ["--remove"]:
            remove_discovery(load_config())
            return 0
        if sys.argv[1:]:
            print("Usage: home_assistant.py [--remove]", file=sys.stderr)
            return 2
        return run()
    except MQTTError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
