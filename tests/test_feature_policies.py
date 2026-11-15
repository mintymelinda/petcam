import unittest
from datetime import datetime

from petcam import light_sensor_policy, timelapse_policy


class TimelapsePolicyTests(unittest.TestCase):
    def test_schedule_handles_normal_and_overnight_windows(self):
        self.assertTrue(timelapse_policy.in_schedule(datetime(2026, 1, 1, 12), "09:00", "17:00"))
        self.assertTrue(timelapse_policy.in_schedule(datetime(2026, 1, 1, 23), "18:00", "06:00"))
        self.assertTrue(timelapse_policy.in_schedule(datetime(2026, 1, 1, 5), "18:00", "06:00"))
        self.assertFalse(timelapse_policy.in_schedule(datetime(2026, 1, 1, 12), "18:00", "06:00"))

    def test_rejects_storage_escape_and_invalid_clock(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            timelapse_policy.validate_config({"storage_path": "/etc/petcam"})
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            timelapse_policy.validate_config({"schedule_start": "25:00"})


class LightSensorPolicyTests(unittest.TestCase):
    def test_hysteresis_retains_prior_state_between_thresholds(self):
        self.assertEqual(light_sensor_policy.classify(120, "unknown", 100, 30), "bright")
        self.assertEqual(light_sensor_policy.classify(20, "unknown", 100, 30), "dark")
        self.assertEqual(light_sensor_policy.classify(60, "bright", 100, 30), "bright")
        self.assertEqual(light_sensor_policy.classify(60, "dark", 100, 30), "dark")

    def test_rejects_invalid_threshold_order(self):
        with self.assertRaisesRegex(light_sensor_policy.SensorError, "dark < bright"):
            light_sensor_policy.validate({
                **light_sensor_policy.DEFAULTS,
                "BRIGHT_THRESHOLD_LUX": "20",
                "DARK_THRESHOLD_LUX": "30",
            })


if __name__ == "__main__":
    unittest.main()
