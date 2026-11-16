from petcam.features.home_assistant import service


def test_home_assistant_integration_is_disabled_by_default(tmp_path):
    config = service.load_config(tmp_path / "missing.conf")
    assert config["MQTT_ENABLED"] is False
