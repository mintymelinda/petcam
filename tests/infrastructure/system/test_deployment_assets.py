import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"


class DeploymentAssetTests(unittest.TestCase):
    def test_source_supervisor_is_the_runtime_entrypoint(self):
        self.assertTrue((ROOT / "src/infrastructure/system/supervisor.py").is_file())
        installer = (DEPLOY / "install.sh").read_text(encoding="utf-8")
        self.assertIn("petcam.infrastructure.system.supervisor", installer)
        self.assertNotIn(".whl", installer)
        self.assertNotIn("pip install", installer)

    def test_petcam_does_not_ship_systemd_units(self):
        self.assertFalse((DEPLOY / "systemd").exists())

    def test_runtime_defaults_are_shipped(self):
        self.assertTrue((DEPLOY / "etc/petcam/petcam.conf").is_file())
        for feature in ("motion", "timelapse"):
            config = DEPLOY / "var/lib/petcam" / feature / "config.json"
            self.assertTrue(config.is_file())
