from petcam.infrastructure.streaming import metrics


def test_stream_metrics_count_jpeg_frames_without_decoding():
    client_id = metrics.register_client("browser")
    parser = {
        "previous_byte": None,
        "in_jpeg": False,
        "last_frame_monotonic": None,
    }
    try:
        metrics.record_chunk(client_id, b"\xff\xd8frame-data\xff\xd9", parser)
        report = metrics.snapshot()
        assert report["active_clients"] == 1
        assert report["clients"][0]["frames"] == 1
        assert report["clients"][0]["bytes"] > 0
    finally:
        metrics.unregister_client(client_id)
