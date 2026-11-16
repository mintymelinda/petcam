from datetime import datetime

import pytest

from petcam.domain.motion.policy import (
    DEFAULTS,
    cooldown_elapsed,
    in_quiet_hours,
    pixel_delta_threshold,
    validate_config,
)


def test_motion_configuration_rejects_out_of_range_sensitivity():
    with pytest.raises(ValueError, match="sensitivity"):
        validate_config({**DEFAULTS, "sensitivity": 101})


def test_quiet_hours_support_overnight_windows():
    assert in_quiet_hours(datetime(2026, 1, 1, 23, 30), "22:00", "06:00")
    assert in_quiet_hours(datetime(2026, 1, 2, 5, 30), "22:00", "06:00")
    assert not in_quiet_hours(datetime(2026, 1, 2, 12, 0), "22:00", "06:00")


def test_sensitivity_and_cooldown_behave_monotonically():
    assert pixel_delta_threshold(90) < pixel_delta_threshold(20)
    assert cooldown_elapsed(125, 100, 25)
    assert not cooldown_elapsed(124, 100, 25)
