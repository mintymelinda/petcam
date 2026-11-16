import pytest

from petcam.infrastructure.persistence.configuration import (
    ConfigError,
    DEFAULTS,
    serialize_config,
    validate_config,
)


def test_default_configuration_validates_and_serializes_deterministically():
    config = validate_config({})
    assert config["PORT"] == DEFAULTS["PORT"]
    serialized = serialize_config(config)
    assert serialized.startswith(b"# PetCam camera settings")
    assert b"PORT=8081\n" in serialized


def test_unknown_configuration_keys_are_rejected():
    with pytest.raises(ConfigError, match="Unknown configuration key"):
        validate_config({"UNEXPECTED": "value"})
