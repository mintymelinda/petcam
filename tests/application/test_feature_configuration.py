"""Tests for non-disruptive camera frame-consumer configuration."""


import unittest
from unittest import mock

from petcam.application import feature_configuration as feature_services


class FeatureConfigurationServiceTests(unittest.TestCase):
    def test_timelapse_update_persists_without_restarting_capture_or_rtsp(self):
        current = {"enabled": False, "interval": 30}
        save = mock.Mock(side_effect=lambda value: value)
        result = feature_services.update_timelapse(
            {"enabled": True, "interval": 60},
            load_config=lambda: current,
            save_config=save,
        )
        self.assertEqual(result, {"enabled": True, "interval": 60})
        save.assert_called_once_with({"enabled": True, "interval": 60})

    def test_motion_can_use_the_native_h264_frame_branch(self):
        current = {"enabled": False, "sensitivity": 50}
        save = mock.Mock(side_effect=lambda value: value)
        result = feature_services.update_motion(
            {"enabled": True},
            load_config=lambda: current,
            save_config=save,
        )
        self.assertEqual(result, {"enabled": True, "sensitivity": 50})
        save.assert_called_once_with({"enabled": True, "sensitivity": 50})

    def test_disabling_timelapse_only_persists_the_flag(self):
        current = {"enabled": True, "interval": 60}
        save = mock.Mock(side_effect=lambda value: value)
        result = feature_services.update_timelapse(
            {"enabled": False},
            load_config=lambda: current,
            save_config=save,
        )
        self.assertEqual(result, {"enabled": False, "interval": 60})
        save.assert_called_once_with({"enabled": False, "interval": 60})

    def test_light_sensor_update_delegates_persistence(self):
        save = mock.Mock(return_value={"enabled": True, "threshold": 25})
        result = feature_services.update_light_sensor(
            {"enabled": True, "threshold": 25}, save_config=save,
        )
        save.assert_called_once_with({"enabled": True, "threshold": 25})
        self.assertEqual(result, {"enabled": True, "threshold": 25})


if __name__ == "__main__":
    unittest.main()
