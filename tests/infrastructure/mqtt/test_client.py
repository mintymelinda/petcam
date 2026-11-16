from petcam.infrastructure.mqtt.client import _field, _packet, _remaining_length


def test_mqtt_length_encoding_uses_continuation_bits():
    assert _remaining_length(127) == b"\x7f"
    assert _remaining_length(128) == b"\x80\x01"


def test_mqtt_string_field_is_utf8_length_prefixed():
    assert _field("abc") == b"\x00\x03abc"


def test_mqtt_packet_includes_fixed_header_and_remaining_length():
    assert _packet(0x10, b"abc") == b"\x10\x03abc"
