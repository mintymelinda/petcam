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
            "petcam-web.service": True,
            "petcam-motion.service": False,
            "petcam-timelapse.service": False,
        })

    def test_web_ui_is_independent_of_camera_capture_readiness(self):
        desired = MODULE.desired_services(
            capture_ready=False,
            web_enabled=False,
            motion={"enabled": True},
            timelapse={"enabled": True},
        )
        self.assertFalse(desired["petcam-web.service"])
        self.assertFalse(desired["petcam-motion.service"])
        self.assertFalse(desired["petcam-timelapse.service"])

    def test_disabled_optional_features_remain_stopped(self):
        desired = MODULE.desired_services(
            capture_ready=True,
            web_enabled=False,
            motion={"enabled": False},
            timelapse={"enabled": False},
        )
        self.assertFalse(any(desired.values()))

    def test_enabled_features_are_started_and_disabled_features_stopped(self):
        calls = []
        active = {"petcam-motion.service"}

        def run(command, **_kwargs):
            calls.append(command)
            if command[1:3] == ["is-active", "--quiet"]:
                return SimpleNamespace(returncode=0 if command[3] in active else 3, stderr="")
            if command[1] == "start":
                active.add(command[2])
            elif command[1] == "stop":
                active.discard(command[2])
            return SimpleNamespace(returncode=0, stderr="")

        MODULE.reconcile_services({
            "petcam-motion.service": False,
            "petcam-timelapse.service": True,
        }, run=run)
        self.assertIn(["/usr/bin/systemctl", "stop", "petcam-motion.service"], calls)
        self.assertIn(["/usr/bin/systemctl", "start", "petcam-timelapse.service"], calls)

    def test_healthy_enabled_service_is_not_restarted(self):
        run = Mock(return_value=SimpleNamespace(returncode=0, stderr=""))
        MODULE.reconcile_services({"petcam-web.service": True}, run=run)
        run.assert_called_once_with(
            ["/usr/bin/systemctl", "is-active", "--quiet", "petcam-web.service"],
            capture_output=True, text=True, check=False, timeout=10,
        )

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
