import unittest
from datetime import datetime

from petcam.features.light_sensor import policy as light_sensor_policy
from petcam.domain.timelapse import policy as timelapse_policy


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



