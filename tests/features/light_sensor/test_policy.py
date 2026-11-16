import unittest

from petcam.features.light_sensor import policy as light_sensor_policy

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

