import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from petcam.infrastructure.system import feature_services as MODULE


class OptionalFeatureServiceTests(unittest.TestCase):
    def test_motion_and_timelapse_start_only_after_capture_is_ready(self):
        desired = MODULE.desired_services(
            capture_ready=False,
            web_enabled=True,
            motion={"enabled": True},
            timelapse={"enabled": True},
        )
        self.assertEqual(desired, {
            "web-ui": True,
            "motion": False,
            "timelapse": False,
        })

    def test_web_ui_is_independent_of_camera_capture_readiness(self):
        desired = MODULE.desired_services(
            capture_ready=False,
            web_enabled=False,
            motion={"enabled": True},
            timelapse={"enabled": True},
        )
        self.assertFalse(desired["web-ui"])
        self.assertFalse(desired["motion"])
        self.assertFalse(desired["timelapse"])

    def test_disabled_optional_features_remain_stopped(self):
        desired = MODULE.desired_services(
            capture_ready=True,
            web_enabled=False,
            motion={"enabled": False},
            timelapse={"enabled": False},
        )
        self.assertFalse(any(desired.values()))

    def test_reconciliation_is_delegated_to_supervisor(self):
        from unittest.mock import patch
        with patch("petcam.infrastructure.system.processes.request") as request:
            MODULE.reconcile_services({"motion": True, "timelapse": False})
        request.assert_called_once_with("reconcile")

    def test_reconciliation_does_not_spawn_host_service_manager(self):
        from unittest.mock import patch
        with patch("petcam.infrastructure.system.processes.request") as request:
            MODULE.reconcile_services({"web-ui": True})
        request.assert_called_once_with("reconcile")

    def test_capture_readiness_requires_sampler_streaming_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps({"state": "connecting"}), encoding="utf-8")
            self.assertFalse(MODULE.capture_is_ready(path))
            path.write_text(json.dumps({"state": "streaming", "codec": "H264"}), encoding="utf-8")
            self.assertTrue(MODULE.capture_is_ready(path))

    def test_web_manager_requires_explicit_boolean_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "web-manager.json"
            self.assertFalse(MODULE._enabled(path))
            path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
            self.assertTrue(MODULE._enabled(path))
            path.write_text(json.dumps({"enabled": "yes"}), encoding="utf-8")
            self.assertFalse(MODULE._enabled(path))


if __name__ == "__main__":
    unittest.main()
