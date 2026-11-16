import unittest

from petcam.domain.camera import capture_policy as MODULE


class CameraCapturePolicyTests(unittest.TestCase):
    def test_estimated_pixel_rate_uses_dimensions_and_fractional_fps(self):
        self.assertEqual(MODULE.estimated_pixel_rate(1920, 1080, 29.5), 61_171_200)

    def test_over_budget_mjpeg_requires_explicit_override(self):
        with self.assertRaisesRegex(ValueError, "performance budget"):
            MODULE.validate_performance_budget(
                1920, 1080, 30, 50_000_000, capture_format="MJPEG",
            )

    def test_performance_override_allows_over_budget_mode(self):
        MODULE.validate_performance_budget(
            1920, 1080, 30, 50_000_000,
            capture_format="MJPEG", allow_override=True,
        )

    def test_h264_is_exempt_from_mjpeg_pixel_budget_warning(self):
        MODULE.validate_performance_budget(
            3840, 2160, 60, 1, capture_format="H264",
        )

    def test_mode_within_budget_is_accepted(self):
        MODULE.validate_performance_budget(
            1280, 720, 30, 30_000_000, capture_format="MJPEG",
        )

    def test_h264_conflicts_with_timelapse(self):
        with self.assertRaisesRegex(ValueError, "Disable timelapse and motion"):
            MODULE.validate_capture_feature_compatibility(
                "H264", timelapse_enabled=True, motion_enabled=False,
            )

    def test_h264_conflicts_with_motion_detection(self):
        with self.assertRaisesRegex(ValueError, "Disable timelapse and motion"):
            MODULE.validate_capture_feature_compatibility(
                "H264", timelapse_enabled=False, motion_enabled=True,
            )

    def test_h264_accepts_when_both_incompatible_features_are_disabled(self):
        MODULE.validate_capture_feature_compatibility(
            "H264", timelapse_enabled=False, motion_enabled=False,
        )

    def test_mjpeg_accepts_enabled_features(self):
        MODULE.validate_capture_feature_compatibility(
            "MJPEG", timelapse_enabled=True, motion_enabled=True,
        )


if __name__ == "__main__":
    unittest.main()
