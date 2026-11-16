from petcam.features.timelapse.service import load_config
from petcam.domain.timelapse.policy import DEFAULTS


def test_missing_timelapse_config_uses_validated_defaults(tmp_path):
    config = load_config(tmp_path / "missing.json")
    assert config["enabled"] is False
    assert config["interval_seconds"] == DEFAULTS["interval_seconds"]
