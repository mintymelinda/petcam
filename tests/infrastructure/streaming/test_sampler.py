import socket
import threading

import pytest

from petcam.infrastructure.streaming import sampler as MODULE


JPEG = b"\xff\xd8sample\xff\xd9"


def test_latest_frame_buffer_replaces_old_frames_and_rejects_stale_frames():
    now = [10.0]
    buffer = MODULE.LatestFrameBuffer(clock=lambda: now[0])
    assert buffer.latest() is None
    buffer.publish(JPEG)
    assert buffer.latest() == JPEG
    now[0] += MODULE.MAX_FRAME_AGE_SECONDS + 0.1
    assert buffer.latest() is None
    buffer.publish(JPEG)
    assert buffer.latest() == JPEG
    buffer.clear()
    assert buffer.latest() is None


def test_latest_frame_buffer_rejects_incomplete_jpeg():
    buffer = MODULE.LatestFrameBuffer()
    with pytest.raises(ValueError, match="complete JPEG"):
        buffer.publish(b"not-jpeg")


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [
        ("H264", ("rtph264depay", "h264parse")),
        ("JPEG", ("rtpjpegdepay", "jpegparse")),
        ("mjpeg", ("rtpjpegdepay", "jpegparse")),
    ],
)
def test_rtp_codec_mapping_supports_h264_and_mjpeg(encoding, expected):
    assert MODULE.rtp_codec_elements(encoding) == expected


def test_unsupported_rtp_codec_is_rejected():
    with pytest.raises(MODULE.SamplerError, match="Unsupported RTSP video encoding"):
        MODULE.rtp_codec_elements("VP8")


def test_unix_socket_client_receives_the_latest_frame(tmp_path):
    path = tmp_path / "sampler.sock"
    buffer = MODULE.LatestFrameBuffer()
    buffer.publish(JPEG)
    server = MODULE.FrameServer(path, buffer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert MODULE.read_latest_frame(path) == JPEG
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unix_socket_client_reports_missing_or_stale_frame(tmp_path):
    path = tmp_path / "sampler.sock"
    now = [100.0]
    buffer = MODULE.LatestFrameBuffer(clock=lambda: now[0])
    buffer.publish(JPEG)
    now[0] += MODULE.MAX_FRAME_AGE_SECONDS + 0.1
    server = MODULE.FrameServer(path, buffer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(MODULE.FrameUnavailableError, match="no recent frame"):
            MODULE.read_latest_frame(path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unix_socket_client_reports_sampler_unavailable(tmp_path):
    with pytest.raises(MODULE.FrameUnavailableError, match="unavailable"):
        MODULE.read_latest_frame(tmp_path / "missing.sock", timeout=0.1)


def test_frame_server_rejects_unknown_commands(tmp_path):
    path = tmp_path / "sampler.sock"
    buffer = MODULE.LatestFrameBuffer()
    buffer.publish(JPEG)
    server = MODULE.FrameServer(path, buffer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))
            client.sendall(b"OTHER\n")
            assert client.recv(4) == b"\x00\x00\x00\x00"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_gstreamer_runtime_requires_decode_and_h264_support():
    names = {
        "rtspsrc", "rtph264depay", "rtpjpegdepay", "h264parse", "jpegparse",
        "decodebin", "videoconvert", "videorate", "capsfilter", "jpegenc",
        "appsink", "jpegdec", "avdec_h264",
    }

    class Factory:
        @staticmethod
        def find(name):
            return object() if name in names else None

    fake_gst = type("FakeGst", (), {"ElementFactory": Factory})
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(MODULE, "_load_gstreamer", lambda: (fake_gst, None))
        assert MODULE.check_gstreamer_runtime()


def test_gstreamer_runtime_rejects_missing_h264_decoder():
    class Factory:
        @staticmethod
        def find(name):
            return None if name in {"v4l2h264dec", "avdec_h264", "vah264dec", "nvh264dec"} else object()

    fake_gst = type("FakeGst", (), {"ElementFactory": Factory})
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(MODULE, "_load_gstreamer", lambda: (fake_gst, None))
        with pytest.raises(MODULE.SamplerError, match="H.264 decoder"):
            MODULE.check_gstreamer_runtime()


def test_sampler_systemd_unit_orders_after_rtsp_and_creates_local_ipc():
    from pathlib import Path

    root = Path(__file__).parents[3] / "deploy" / "systemd"
    unit = (root / "petcam-rtsp-sampler.service").read_text(encoding="utf-8")
    rtsp_unit = (root / "petcam-g-streamer-rtsp.service").read_text(encoding="utf-8")
    motion_unit = (root / "petcam-motion.service").read_text(encoding="utf-8")
    timelapse_unit = (root / "petcam-timelapse.service").read_text(encoding="utf-8")
    assert "After=network-online.target petcam-g-streamer-rtsp.service" in unit
    assert "Wants=network-online.target petcam-g-streamer-rtsp.service" in unit
    assert "Wants=network-online.target petcam-rtsp-sampler.service" in rtsp_unit
    assert "petcam-rtsp-sampler.service" in motion_unit
    assert "petcam-rtsp-sampler.service" in timelapse_unit
    assert "WantedBy=multi-user.target" in unit
