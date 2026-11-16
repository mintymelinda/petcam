"""Application-level diagnostics aggregation."""


def live_snapshot(
    *,
    capture_status,
    stream_metrics,
    network_status,
    system_metrics,
    rtsp_status,
    captured_at,
):
    """Combine independent infrastructure readings into the manager API payload."""
    return {
        "capture_status": capture_status,
        "capture_status_updated_at": captured_at,
        "stream_metrics": stream_metrics,
        "network_status": network_status,
        "system_metrics": system_metrics,
        "g_streamer_status": rtsp_status,
    }
