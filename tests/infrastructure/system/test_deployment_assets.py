import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"


class DeploymentAssetTests(unittest.TestCase):
    def test_systemd_units_use_the_installed_virtual_environment(self):
        units = sorted((DEPLOY / "systemd").glob("*.service"))
        self.assertTrue(units)
        for unit in units:
            text = unit.read_text(encoding="utf-8")
            self.assertIn("/opt/petcam/venv/bin/python", text, unit.name)
            self.assertNotIn("/opt/petcam/current/lib", text, unit.name)

    def test_installer_and_all_runtime_defaults_are_shipped(self):
        self.assertTrue((DEPLOY / "install.sh").is_file())
        self.assertTrue((DEPLOY / "etc/petcam/petcam.conf").is_file())
        for feature in ("motion", "timelapse"):
            config = DEPLOY / "var/lib/petcam" / feature / "config.json"
            self.assertIs(json.loads(config.read_text(encoding="utf-8"))["enabled"], False)

    def test_legacy_stream_drop_in_is_not_shipped(self):
        self.assertFalse((DEPLOY / "systemd/petcam-stream.service.d").exists())

    def test_full_web_ui_is_disabled_by_default(self):
        config = json.loads(
            (DEPLOY / "etc/petcam/web-manager.json").read_text(encoding="utf-8")
        )
        self.assertIs(config["enabled"], False)


if __name__ == "__main__":
    unittest.main()
