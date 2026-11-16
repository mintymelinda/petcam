from petcam.infrastructure.monitoring.health import timestamp


def test_health_timestamps_are_utc_and_deterministic():
    result = timestamp(1798761600)
    assert result.endswith("+00:00")
    assert result.startswith("2027-")
