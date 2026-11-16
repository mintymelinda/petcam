from petcam.application.diagnostics import live_snapshot


def test_live_snapshot_combines_all_diagnostic_adapters_without_mutation():
    capture = {"state": "running"}
    network = {"type": "wired"}
    system = {"cpu_percent": 12.5}
    rtsp = {"state": "publishing"}

    result = live_snapshot(
        capture_status=capture,
        network_status=network,
        system_metrics=system,
        rtsp_status=rtsp,
        captured_at=123.5,
    )

    assert result == {
        "capture_status": capture,
        "capture_status_updated_at": 123.5,
        "network_status": network,
        "system_metrics": system,
        "g_streamer_status": rtsp,
    }
    assert result["capture_status"] is capture
