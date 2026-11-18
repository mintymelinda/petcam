"""Decode the shared PetCam RTSP feed once and serve fresh JPEG samples over a Unix socket."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import socketserver
import struct
import threading
import time
from pathlib import Path

RTSP_URL = "rtsp://127.0.0.1:8554/petcam"
SOCKET_PATH = Path("/run/petcam/rtsp-sampler.sock")
STATUS_PATH = Path("/run/petcam/rtsp-sampler-status.json")
MAX_FRAME_BYTES = 32 * 1024 * 1024
MAX_FRAME_AGE_SECONDS = 5.0
SAMPLE_RATE = 1
_running = True


class SamplerError(RuntimeError):
    """Raised when the RTSP sampler cannot initialize or deliver a frame."""


class FrameUnavailableError(OSError):
    """Raised when the sampler has no sufficiently recent decoded frame."""


class LatestFrameBuffer:
    """Thread-safe, one-frame buffer; new frames always replace older frames."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._frame = None
        self._captured_at = None

    def publish(self, frame):
        if not isinstance(frame, bytes) or not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
            raise ValueError("The sampler can only publish complete JPEG frames.")
        with self._lock:
            self._frame = frame
            self._captured_at = self._clock()

    def latest(self, max_age=MAX_FRAME_AGE_SECONDS):
        with self._lock:
            if self._frame is None or self._captured_at is None:
                return None
            if self._clock() - self._captured_at > max_age:
                return None
            return self._frame

    def clear(self):
        with self._lock:
            self._frame = None
            self._captured_at = None


class _FrameRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        command = self.rfile.readline(32)
        frame = self.server.frame_buffer.latest(self.server.max_frame_age)
        if command != b"FRAME\n" or frame is None:
            self.wfile.write(struct.pack("!I", 0))
            return
        self.wfile.write(struct.pack("!I", len(frame)))
        self.wfile.write(frame)


class FrameServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Small local IPC endpoint for consumers of the shared latest frame."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path=SOCKET_PATH, frame_buffer=None, max_frame_age=MAX_FRAME_AGE_SECONDS):
        self.socket_path = Path(socket_path)
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            self.socket_path.unlink()
        self.frame_buffer = frame_buffer or LatestFrameBuffer()
        self.max_frame_age = max_frame_age
        super().__init__(str(self.socket_path), _FrameRequestHandler)
        os.chmod(self.socket_path, 0o660)

    def server_close(self):
        super().server_close()
        self.socket_path.unlink(missing_ok=True)


def _read_exact(connection, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise FrameUnavailableError("The RTSP sampler closed an incomplete frame response.")
        chunks.extend(chunk)
    return bytes(chunks)


def read_latest_frame(socket_path=SOCKET_PATH, timeout=3):
    """Request the newest decoded frame without opening another RTSP session."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(b"FRAME\n")
            size = struct.unpack("!I", _read_exact(connection, 4))[0]
            if size == 0:
                raise FrameUnavailableError("The RTSP sampler has no recent frame available.")
            if size > MAX_FRAME_BYTES:
                raise FrameUnavailableError("The RTSP sampler returned an oversized frame.")
            frame = _read_exact(connection, size)
    except FrameUnavailableError:
        raise
    except OSError as error:
        raise FrameUnavailableError(f"The shared RTSP frame sampler is unavailable: {error}") from error
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise FrameUnavailableError("The RTSP sampler returned an invalid JPEG frame.")
    return frame


def rtp_codec_elements(encoding_name, h264_decoder="avdec_h264"):
    """Return the depayloader, parser, and decoder for an RTSP video codec."""
    codec = str(encoding_name or "").upper()
    if codec == "H264":
        if h264_decoder not in {"v4l2h264dec", "avdec_h264"}:
            raise SamplerError(f"Unsupported H.264 decoder: {h264_decoder!r}")
        return "rtph264depay", "h264parse", h264_decoder
    if codec in {"JPEG", "MJPEG"}:
        return "rtpjpegdepay", "jpegparse", "jpegdec"
    raise SamplerError(f"Unsupported RTSP video encoding: {encoding_name!r}")


def rtp_pipeline_element_names(encoding_name, depay_name, parser_name, decoder_name):
    """Return codec-specific elements for the RTSP sampler output chain."""
    names = [depay_name, parser_name]
    if str(encoding_name).upper() == "H264":
        names.append("capsfilter")
    names.append(decoder_name)
    if str(encoding_name).upper() == "H264":
        names.append("capsfilter")
    names.extend(("videoconvert", "videorate", "capsfilter", "jpegenc", "appsink"))
    return tuple(names)


def _load_gstreamer():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtsp", "1.0")
        from gi.repository import Gst, GstRtsp
    except (ImportError, ValueError) as error:
        raise SamplerError("GStreamer RTSP client bindings are missing.") from error
    Gst.init(None)
    return Gst, GstRtsp


def check_gstreamer_runtime():
    Gst, _GstRtsp = _load_gstreamer()
    required = (
        "rtspsrc",
        "rtph264depay",
        "rtpjpegdepay",
        "h264parse",
        "jpegparse",
        "jpegdec",
        "videoconvert",
        "videorate",
        "capsfilter",
        "jpegenc",
        "appsink",
    )
    missing = [name for name in required if Gst.ElementFactory.find(name) is None]
    h264_decoders = ("v4l2h264dec", "avdec_h264")
    if not any(Gst.ElementFactory.find(name) is not None for name in h264_decoders):
        missing.append("an H.264 decoder (v4l2h264dec or avdec_h264)")
    if missing:
        raise SamplerError("Required GStreamer sampler element(s) are missing: " + ", ".join(missing))
    return True


def build_pipeline(Gst, GstRtsp, frame_buffer, rtsp_url=RTSP_URL, on_codec=None, on_frame=None):
    """Create an RTSP client that decodes H.264 or MJPEG and emits at most 1 JPEG/s."""
    pipeline = Gst.Pipeline.new("petcam-rtsp-frame-sampler")
    source = Gst.ElementFactory.make("rtspsrc", "rtsp-source")
    if pipeline is None or source is None:
        raise SamplerError("Unable to create the GStreamer RTSP sampler pipeline.")
    source.set_property("location", rtsp_url)
    source.set_property("latency", 250)
    source.set_property("drop-on-latency", True)
    source.set_property("protocols", GstRtsp.RTSPLowerTrans.TCP)
    pipeline.add(source)

    branch_state = {"linked": False}

    def sample_ready(sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        success, mapped = buffer.map(Gst.MapFlags.READ)
        if success:
            try:
                frame = bytes(mapped.data)
                if on_frame:
                    on_frame(frame)
                else:
                    frame_buffer.publish(frame)
            finally:
                buffer.unmap(mapped)
        return Gst.FlowReturn.OK

    def rtp_pad_added(_source, pad):
        if branch_state["linked"]:
            return
        caps = pad.get_current_caps() or pad.query_caps(None)
        if caps is None or caps.get_size() == 0:
            return
        structure = caps.get_structure(0)
        if structure.get_name() != "application/x-rtp" or structure.get_string("media") != "video":
            return
        encoding = structure.get_string("encoding-name")
        is_h264 = str(encoding).upper() == "H264"
        h264_decoder = "avdec_h264"
        if Gst.ElementFactory.find("v4l2h264dec") is not None:
            h264_decoder = "v4l2h264dec"

        try:
            depay_name, parser_name, decoder_name = rtp_codec_elements(
                encoding, h264_decoder
            )
        except SamplerError as error:
            logging.error("%s", error)
            return

        names = rtp_pipeline_element_names(
            encoding, depay_name, parser_name, decoder_name
        )

        elements = [
            Gst.ElementFactory.make(name, f"sampler-{index}")
            for index, name in enumerate(names)
        ]
        if any(element is None for element in elements):
            logging.error("Unable to create GStreamer elements for RTSP codec %s", encoding)
            return

        depay, parser = elements[:2]
        index = 2
        if is_h264:
            parser_caps_filter = elements[index]
            index += 1
            parser_caps_filter.set_property(
                "caps",
                Gst.Caps.from_string(
                    "video/x-h264,stream-format=byte-stream,alignment=au"
                ),
            )

        decoder = elements[index]
        index += 1
        if is_h264:
            decoder_caps_filter = elements[index]
            index += 1
            decoder_caps_filter.set_property(
                "caps", Gst.Caps.from_string("video/x-raw,format=I420")
            )
            if decoder_name == "v4l2h264dec":
                decoder.set_property("capture-io-mode", 2)
                decoder.set_property("output-io-mode", 2)

        converter, rate, caps_filter, encoder, sink = elements[index:]
        for element in elements:
            pipeline.add(element)

        for upstream, downstream in zip(elements, elements[1:]):
            if not upstream.link(downstream):
                logging.error(
                    "Unable to link the RTSP %s sampler chain between %s and %s.",
                    encoding,
                    upstream.get_name(),
                    downstream.get_name(),
                )
                return

        rate.set_property("drop-only", True)
        rate.set_property("max-rate", SAMPLE_RATE)
        caps_filter.set_property("caps", Gst.Caps.from_string(f"video/x-raw,framerate={SAMPLE_RATE}/1"))
        encoder.set_property("quality", 85)
        sink.set_property("emit-signals", True)
        sink.set_property("max-buffers", 1)
        sink.set_property("drop", True)
        sink.set_property("sync", False)
        sink.set_property("wait-on-eos", False)
        sink.connect("new-sample", sample_ready)
        if pad.link(depay.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            logging.error("Unable to link the RTSP %s stream to its depayloader.", encoding)
            return
        branch_state["linked"] = True
        for element in elements:
            element.sync_state_with_parent()
        if on_codec:
            on_codec(str(encoding).upper())
        logging.info("RTSP sampler connected to %s video", encoding)

    source.connect("pad-added", rtp_pad_added)
    return pipeline


def _write_status(path, state, codec=None, error=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "codec": codec, "updated_at": time.time(), "last_error": error}
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def run_sampler(rtsp_url=RTSP_URL, socket_path=SOCKET_PATH, status_path=STATUS_PATH):
    Gst, GstRtsp = _load_gstreamer()
    check_gstreamer_runtime()
    frame_buffer = LatestFrameBuffer()
    frame_server = FrameServer(socket_path, frame_buffer)
    server_thread = threading.Thread(target=frame_server.serve_forever, name="rtsp-frame-socket", daemon=True)
    server_thread.start()
    retry_delay = 1
    try:
        while _running:
            pipeline = None
            codec = {"value": None}
            first_frame = {"at": None}

            def on_codec(value):
                codec["value"] = value
                _write_status(status_path, "decoding", value)

            try:
                frame_buffer.clear()
                _write_status(status_path, "connecting")
                def publish(frame):
                    now = time.monotonic()
                    first = first_frame["at"] is None
                    first_frame["at"] = now
                    frame_buffer.publish(frame)
                    if first and codec["value"]:
                        _write_status(status_path, "streaming", codec["value"])

                pipeline = build_pipeline(Gst, GstRtsp, frame_buffer, rtsp_url, on_codec, publish)
                result = pipeline.set_state(Gst.State.PLAYING)
                if result == Gst.StateChangeReturn.FAILURE:
                    raise SamplerError("GStreamer could not start the RTSP sampler pipeline.")
                bus = pipeline.get_bus()
                started_at = time.monotonic()
                while _running:
                    message = bus.timed_pop_filtered(
                        int(Gst.SECOND),
                        Gst.MessageType.ERROR | Gst.MessageType.EOS,
                    )
                    if message is not None:
                        if message.type == Gst.MessageType.ERROR:
                            error, debug = message.parse_error()
                            raise SamplerError(f"RTSP sampler pipeline error: {error}; {debug or ''}")
                        raise SamplerError("The RTSP sampler stream ended.")
                    if time.monotonic() - started_at > 15 and first_frame["at"] is None:
                        raise SamplerError("The RTSP stream did not produce a fresh decoded frame.")
                    if first_frame["at"] is not None and time.monotonic() - first_frame["at"] > 10:
                        raise SamplerError("The RTSP stream stopped producing frames.")
                retry_delay = 1
            except Exception as error:
                logging.warning("%s; retrying in %s seconds", error, retry_delay)
                _write_status(status_path, "reconnecting", codec["value"], str(error))
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
            finally:
                frame_buffer.clear()
                if pipeline is not None:
                    pipeline.set_state(Gst.State.NULL)
    finally:
        frame_server.shutdown()
        frame_server.server_close()
        server_thread.join(timeout=2)
        _write_status(status_path, "stopped")


def _stop(_signum, _frame):
    global _running
    _running = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check GStreamer sampler dependencies")
    parser.add_argument("--rtsp-url", default=RTSP_URL)
    parser.add_argument("--socket", type=Path, default=SOCKET_PATH)
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.check:
        check_gstreamer_runtime()
        return 0
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_sampler(args.rtsp_url, args.socket, args.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
