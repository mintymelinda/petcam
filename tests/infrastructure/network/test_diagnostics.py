from petcam.infrastructure.network.diagnostics import redact_text


def test_diagnostics_redact_passwords_and_bearer_tokens():
    value = "MQTT_PASSWORD=secret-value\nAuthorization: Bearer abc.def.ghi"
    redacted = redact_text(value)
    assert "secret-value" not in redacted
    assert "abc.def.ghi" not in redacted
