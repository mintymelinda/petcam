"""MQTT 3.1.1 client transport for infrastructure integrations."""

import hashlib
import json
import re
import socket
import ssl
import struct
from pathlib import Path


KEEPALIVE_SECONDS = 60


class MQTTError(RuntimeError):
    """Raised for invalid MQTT settings or protocol failures."""

def _remaining_length(length: int) -> bytes:
    if not 0 <= length <= 268435455:
        raise MQTTError("MQTT packet is too large.")
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def _field(value: str | bytes) -> bytes:
    data = value.encode("utf-8") if isinstance(value, str) else value
    if len(data) > 65535:
        raise MQTTError("MQTT field is too long.")
    return struct.pack("!H", len(data)) + data


def _packet(packet_type: int, payload: bytes, flags: int = 0) -> bytes:
    return bytes([(packet_type << 4) | flags]) + _remaining_length(len(payload)) + payload


def _read_exact(connection: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = connection.recv(count - len(chunks))
        if not chunk:
            raise MQTTError("MQTT broker closed the connection.")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_packet(connection: socket.socket) -> tuple[int, bytes]:
    header = _read_exact(connection, 1)[0]
    multiplier = 1
    remaining = 0
    for _ in range(4):
        digit = _read_exact(connection, 1)[0]
        remaining += (digit & 127) * multiplier
        if not digit & 128:
            break
        multiplier *= 128
    else:
        raise MQTTError("Invalid MQTT remaining-length field.")
    return header >> 4, _read_exact(connection, remaining)


def _client_identifier(config: dict[str, object]) -> str:
    configured = str(config["MQTT_CLIENT_ID"]).strip()
    if configured:
        return configured
    machine_id = Path("/etc/machine-id")
    try:
        identity = machine_id.read_text(encoding="ascii").strip()
    except OSError:
        identity = socket.gethostname()
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"petcam-{digest}"


def _node_identifier(config: dict[str, object]) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", _client_identifier(config)).strip("_")
    return value or "petcam_device"


class MQTTClient:
    def __init__(self, config: dict[str, object]):
        self.config = config
        self.connection: socket.socket | None = None

    def connect(self) -> None:
        raw = socket.create_connection(
            (str(self.config["MQTT_HOST"]), int(self.config["MQTT_PORT"])), timeout=10
        )
        if self.config["MQTT_TLS"]:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=str(self.config["MQTT_HOST"]))
        raw.settimeout(10)
        flags = 0x02 | 0x04 | 0x20
        payload = _field(_client_identifier(self.config))
        will_topic = self._topic("broker")
        payload += _field(will_topic) + _field("offline")
        username = str(self.config["MQTT_USERNAME"])
        password = str(self.config["MQTT_PASSWORD"])
        if username:
            flags |= 0x80
            payload += _field(username)
        if password:
            flags |= 0x40
            payload += _field(password)
        variable = _field("MQTT") + bytes([4, flags]) + struct.pack("!H", KEEPALIVE_SECONDS)
        raw.sendall(_packet(1, variable + payload))
        packet_type, response = _read_packet(raw)
        if packet_type != 2 or len(response) != 2 or response[0] != 0 or response[1] != 0:
            raw.close()
            raise MQTTError("MQTT broker rejected the connection.")
        self.connection = raw

    def _topic(self, suffix: str) -> str:
        return f"{self.config['MQTT_TOPIC_PREFIX']}/{_node_identifier(self.config)}/{suffix}"

    def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        if self.connection is None:
            raise MQTTError("MQTT client is not connected.")
        body = _field(topic) + payload.encode("utf-8")
        self.connection.sendall(_packet(3, body, 1 if retain else 0))

    def publish_availability(self, state: str) -> None:
        self.publish(self._topic("broker"), state)

    def publish_discovery(self, node_id: str, hostname: str, model: str, entities: list[dict]) -> None:
        device = {
            "identifiers": [node_id],
            "name": hostname,
            "manufacturer": "PetCam",
            "model": model or "Raspberry Pi",
        }
        for entity in entities:
            component = entity["component"]
            object_id = entity["object_id"]
            topic = f"{self.config['MQTT_DISCOVERY_PREFIX']}/{component}/{node_id}/{object_id}/config"
            document = {
                "name": entity["name"],
                "unique_id": f"{node_id}_{object_id}",
                "state_topic": self._topic(f"state/{object_id}"),
                "device": device,
                "availability_mode": "all",
                "availability": [
                    {"topic": self._topic("broker"), "payload_available": "online", "payload_not_available": "offline"},
                    {"topic": self._topic("health_availability"), "payload_available": "healthy", "payload_not_available": "unhealthy"},
                ],
            }
            if component == "binary_sensor":
                document.update({"payload_on": entity.get("payload_on", "ON"), "payload_off": entity.get("payload_off", "OFF"), "device_class": entity.get("device_class")})
            if entity.get("device_class") and component == "sensor":
                document["device_class"] = entity["device_class"]
            if entity.get("unit_of_measurement"):
                document["unit_of_measurement"] = entity["unit_of_measurement"]
            if entity.get("state_class"):
                document["state_class"] = entity["state_class"]
            if entity.get("icon"):
                document["icon"] = entity["icon"]
            if entity.get("entity_category"):
                document["entity_category"] = entity["entity_category"]
            self.publish(topic, json.dumps(document, separators=(",", ":")))

    def publish_state(self, snapshot: dict[str, str]) -> None:
        for key, value in snapshot.items():
            self.publish(self._topic(f"state/{key}"), value)

    def ping(self) -> None:
        if self.connection is None:
            raise MQTTError("MQTT client is not connected.")
        self.connection.sendall(b"\xc0\x00")
        packet_type, _ = _read_packet(self.connection)
        if packet_type != 13:
            raise MQTTError("MQTT broker did not acknowledge keepalive.")

    def close(self, graceful: bool = True) -> None:
        if self.connection is None:
            return
        try:
            if graceful:
                self.publish_availability("offline")
                self.connection.sendall(b"\xe0\x00")
        except OSError:
            pass
        finally:
            try:
                self.connection.close()
            except OSError:
                pass
            self.connection = None
