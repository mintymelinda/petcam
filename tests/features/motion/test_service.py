from petcam.features.motion.service import load_config
from petcam.domain.motion.policy import DEFAULTS


def test_missing_motion_config_uses_validated_defaults(tmp_path):
    config = load_config(tmp_path / "missing.json")
    assert config == DEFAULTS
    assert config["enabled"] is False
