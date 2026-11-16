from petcam.domain.streaming.status import status_snapshot


def test_fresh_publishing_heartbeat_is_active():
    result = status_snapshot(
        True,
        {"state": "publishing", "updated_at": 98, "fps": 30, "source": "native_h264"},
        now=100,
    )
    assert result["service_active"] is True
    assert result["active"] is True
    assert result["state"] == "publishing"
    assert result["fps"] == 30


def test_stale_heartbeat_is_stalled_and_does_not_expose_old_metrics():
    result = status_snapshot(
        True,
        {"state": "publishing", "updated_at": 80, "fps": 30, "source": "native_h264"},
        now=100,
    )
    assert result["state"] == "stalled"
    assert result["active"] is False
    assert result["fps"] is None
    assert result["source"] is None
