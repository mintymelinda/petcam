"""Tests for always-on GStreamer restarts in camera feature transactions."""

import unittest
from unittest import mock

from petcam.application import feature_configuration as feature_services


class FeatureConfigurationServiceTests(unittest.TestCase):
    def test_timelapse_update_always_restarts_stream_and_gstreamer(self):
        current = {"enabled": False, "interval": 30}
        transaction = mock.Mock(side_effect=lambda save, previous, candidate, commands, rollback: candidate)
        feature_services.update_timelapse(
            {"enabled": True, "interval": 60},
            parse_config=lambda path: {"FORMAT": "MJPEG"},
            config_path="/etc/petcam/petcam.conf",
            load_config=lambda: current,
            save_config=lambda value: value,
            systemctl_command=lambda *args: ["/usr/bin/systemctl", *args],
            apply_transaction=transaction,
        )
        commands = transaction.call_args.args[3]
        self.assertEqual([item[0] for item in commands], [
            ["/usr/bin/systemctl", "restart", "petcam-stream.service"],
            ["/usr/bin/systemctl", "restart", "petcam-g-streamer-rtsp.service"],
        ])

    def test_motion_update_rejects_mjpeg_only_feature_on_h264(self):
        transaction = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "motion detection requires MJPEG frames"):
            feature_services.update_motion(
                {"enabled": True}, parse_config=lambda path: {"FORMAT": "H264"},
                config_path="/etc/petcam/petcam.conf", load_config=mock.Mock(),
                save_config=mock.Mock(),
                systemctl_command=lambda *args: ["/usr/bin/systemctl", *args],
                apply_transaction=transaction,
            )
        transaction.assert_not_called()

    def test_light_sensor_update_delegates_persistence(self):
        save = mock.Mock(return_value={"enabled": True, "threshold": 25})
        result = feature_services.update_light_sensor(
            {"enabled": True, "threshold": 25}, save_config=save,
        )
        save.assert_called_once_with({"enabled": True, "threshold": 25})
        self.assertEqual(result, {"enabled": True, "threshold": 25})


if __name__ == "__main__":
    unittest.main()
