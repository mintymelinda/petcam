from petcam.features.light_sensor.service import load_config, read_status


def test_missing_light_sensor_files_return_safe_defaults(tmp_path):
    config = load_config(tmp_path / "missing.conf")
    assert config["ENABLED"] is False
    status = read_status(tmp_path / "missing.json")
    assert status["state"] == "unknown"
    assert status["available"] is False
