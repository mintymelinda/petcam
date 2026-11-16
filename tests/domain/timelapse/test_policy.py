from datetime import datetime

import pytest

from petcam.domain.timelapse.policy import DEFAULTS, in_schedule, validate_config


def test_timelapse_policy_rejects_storage_outside_managed_roots():
    with pytest.raises(ValueError, match="inside"):
        validate_config({**DEFAULTS, "storage_path": "/tmp/petcam"})


def test_schedule_supports_midnight_wraparound():
    assert in_schedule(datetime(2026, 1, 1, 23, 30), "22:00", "06:00")
    assert in_schedule(datetime(2026, 1, 2, 5, 30), "22:00", "06:00")
    assert not in_schedule(datetime(2026, 1, 2, 12, 0), "22:00", "06:00")
