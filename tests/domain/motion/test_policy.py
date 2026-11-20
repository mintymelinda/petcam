import unittest
from datetime import datetime

from petcam.domain.motion import policy as MODULE


class MotionPolicyTests(unittest.TestCase):
    def test_defaults_are_opt_in_and_bounded(self):
        config = MODULE.validate_config({})
        self.assertFalse(config["enabled"])
        self.assertEqual(config["sample_interval_seconds"], 2)
        self.assertEqual(config["max_events"], 100)

    def test_configuration_rejects_unknown_and_invalid_values(self):
        for values in (
            {"sample_interval_seconds": 0},
            {"sensitivity": 101},
            {"minimum_changed_percent": 0},
            {"quiet_hours_start": "25:00"},
            {"enabled": "true"},
            {"unexpected": True},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MODULE.validate_config(values)

    def test_quiet_hours_handles_daytime_and_overnight_windows(self):
        self.assertTrue(MODULE.in_quiet_hours(datetime(2026, 1, 1, 12), "09:00", "17:00"))
        self.assertFalse(MODULE.in_quiet_hours(datetime(2026, 1, 1, 18), "09:00", "17:00"))
        self.assertTrue(MODULE.in_quiet_hours(datetime(2026, 1, 1, 23), "22:00", "07:00"))
        self.assertTrue(MODULE.in_quiet_hours(datetime(2026, 1, 1, 6), "22:00", "07:00"))
        self.assertFalse(MODULE.in_quiet_hours(datetime(2026, 1, 1, 12), "22:00", "22:00"))

    def test_sensitivity_maps_to_pixel_delta_threshold(self):
        self.assertLess(MODULE.pixel_delta_threshold(100), MODULE.pixel_delta_threshold(1))

    def test_cooldown_boundary_is_inclusive(self):
        self.assertFalse(MODULE.cooldown_elapsed(159, 100, 60))
        self.assertTrue(MODULE.cooldown_elapsed(160, 100, 60))


if __name__ == "__main__":
    unittest.main()
