import pytest

from petcam.infrastructure.mqtt import client


class SocketChunks:
    def __init__(self, payload):
        self.payload = bytearray(payload)

    def recv(self, count):
        chunk = bytes(self.payload[:count])
        del self.payload[:count]
        return chunk


def test_remaining_length_encodes_mqtt_variable_integer_boundaries():
    assert client._remaining_length(0) == b"\x00"
    assert client._remaining_length(127) == b"\x7f"
    assert client._remaining_length(128) == b"\x80\x01"
    assert client._remaining_length(16_384) == b"\x80\x80\x01"


def test_remaining_length_rejects_values_outside_mqtt_limit():
    with pytest.raises(client.MQTTError, match="too large"):
        client._remaining_length(268_435_456)


def test_mqtt_field_and_packet_encode_protocol_headers():
    assert client._field("cam") == b"\x00\x03cam"
    assert client._field(b"\x01\x02") == b"\x00\x02\x01\x02"
    assert client._packet(3, b"payload", flags=1) == b"\x31\x07payload"


def test_read_exact_accumulates_partial_socket_reads():
    assert client._read_exact(SocketChunks(b"abcdef"), 6) == b"abcdef"


def test_read_packet_decodes_packet_type_and_payload():
    packet_type, payload = client._read_packet(SocketChunks(b"\x20\x02\x00\x00"))
    assert packet_type == 2
    assert payload == b"\x00\x00"


def test_publish_requires_a_connected_client():
    instance = client.MQTTClient({
        "MQTT_HOST": "broker",
        "MQTT_PORT": 1883,
        "MQTT_TLS": False,
        "MQTT_USERNAME": "",
        "MQTT_PASSWORD": "",
        "MQTT_CLIENT_ID": "petcam-test",
        "MQTT_TOPIC_PREFIX": "petcam",
        "MQTT_DISCOVERY_PREFIX": "homeassistant",
    })
    with pytest.raises(client.MQTTError, match="not connected"):
        instance.publish("petcam/test", "payload")
