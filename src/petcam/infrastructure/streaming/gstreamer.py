#!/usr/bin/env python3
"""Publish a camera's already-encoded H.264 access units over RTSP."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

from ..camera.discovery import detect_hardware_h264_encoder
from ..camera.h264 import H264AccessUnitFramer, inspect_h264_access_unit

RUN_DIR = Path(os.environ.get("PETCAM_RUN", f"/tmp/petcam-{os.getuid()}"))
CAMERA_STATUS = RUN_DIR / "camera-status.json"
STREAM_STATUS = RUN_DIR / "stream-status.json"
RTSP_PORT = 8554
RTSP_PATH = "/petcam"


class GStreamerError(RuntimeError):
    """Raised when native H.264 capture or the RTSP pipeline cannot start."""


def load_camera_status(path: Path | str = CAMERA_STATUS) -> dict:
    try:
        status = json.loads(Path(path).read_text(encoding="utf-8"))
        pid = int(status.get("pid", 0))
        if status.get("native_h264") is not True or pid <= 1:
            return {}
        os.kill(pid, 0)
        return status
    except (OSError, ValueError, TypeError):
        return {}


def _validate_mode(status: dict) -> tuple[int, int, float]:
    resolution = str(status.get("resolution", ""))
    match = re.fullmatch(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})", resolution)
    if not match:
        raise GStreamerError("Configured H.264 resolution is invalid.")
    try:
        fps = float(status.get("fps"))
    except (TypeError, ValueError) as error:
        raise GStreamerError("Configured H.264 frame rate is invalid.") from error
    if not 0 < fps <= 1000:
        raise GStreamerError("Configured H.264 frame rate is invalid.")
    return int(match.group(1)), int(match.group(2)), fps


def build_source_launch(status: dict) -> str:
    """Build the USB source path without parsing or decoding the encoded H.264."""
    if status.get("native_h264") is not True:
        raise GStreamerError("PetCam accepts only native H.264 camera sources.")
    if status.get("backend") != "usb":
        raise GStreamerError("CSI capture supplies complete H.264 access units directly.")
    width, height, fps = _validate_mode(status)
    device = str(status.get("device", ""))
    if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+-]+)", device):
        raise GStreamerError("Configured USB camera device path is invalid.")
    escaped_device = device.replace("\\", "\\\\").replace('"', '\\"')
    frame_rate = Fraction(str(fps)).limit_denominator(1001)
    return (
        f'v4l2src name=camera_source device="{escaped_device}" do-timestamp=true'
        " ! "
        f"video/x-h264,width={width},height={height},"
        f"framerate={frame_rate.numerator}/{frame_rate.denominator},"
        "stream-format=byte-stream,alignment=au ! "
        "appsink name=rtsp_sink emit-signals=true max-buffers=2 drop=true "
        "sync=false wait-on-eos=false"
    )


def build_rtsp_launch() -> str:
    """Packetize complete encoded H.264 access units directly into RTP."""
    return (
        "( appsrc name=rtsp_source is-live=true format=time do-timestamp=true "
        "block=false max-bytes=1048576 "
        "caps=video/x-h264,stream-format=byte-stream,alignment=au ! "
        "rtph264pay name=pay0 pt=96 config-interval=1 )"
    )


def write_status(state: str, source: dict, fps: float | None = None, message: str = "") -> None:
    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "state": state,
        "source": source.get("backend"),
        "resolution": source.get("resolution"),
        "capture_fps": source.get("fps"),
        "streamed_fps": round(fps, 2) if fps is not None and fps > 0 else None,
        "updated_at": time.time(),
        "message": message,
    }
    temporary = STREAM_STATUS.with_name(STREAM_STATUS.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, STREAM_STATUS)


def _load_gstreamer():
    try:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtspServer", "1.0")
        from gi.repository import GLib, Gst, GstRtspServer
    except (ImportError, ValueError) as error:
        raise GStreamerError(
            "GStreamer RTSP bindings are missing. Install python3-gi and "
            "gir1.2-gst-rtsp-server-1.0."
        ) from error
    Gst.init(None)
    return GLib, Gst, GstRtspServer


def check_gstreamer_runtime(Gst, backend: str) -> None:
    required = ["appsink", "appsrc", "rtph264pay"]
    if backend == "usb":
        required.append("v4l2src")
    missing = [name for name in required if Gst.ElementFactory.find(name) is None]
    if missing:
        raise GStreamerError("Missing H.264 GStreamer element(s): " + ", ".join(missing))


def _hostname() -> str:
    try:
        return socket.getfqdn() or socket.gethostname()
    except OSError:
        return "<device-hostname>"


def _csi_capture_command(camera_status: dict) -> list[str]:
    width, height, fps = _validate_mode(camera_status)
    try:
        camera = int(camera_status.get("camera"))
    except (TypeError, ValueError) as error:
        raise GStreamerError("Configured CSI camera index is invalid.") from error
    if camera < 0:
        raise GStreamerError("Configured CSI camera index is invalid.")
    if not shutil.which("rpicam-vid"):
        raise GStreamerError("rpicam-vid is missing; install rpicam-apps-lite.")
    encoder = detect_hardware_h264_encoder()
    if encoder.get("available") is not True:
        raise GStreamerError(
            "No Raspberry Pi hardware H.264 encoder was detected. "
            "CSI capture will not use software encoding."
        )
    return [
        "rpicam-vid", "--camera", str(camera), "--timeout", "0",
        "--nopreview", "--codec", "h264", "--inline",
        "--width", str(width), "--height", str(height),
        "--framerate", str(fps), "--output", "-",
    ]


def run_server(camera_status: dict) -> int:
    backend = str(camera_status.get("backend", ""))
    GLib, Gst, GstRtspServer = _load_gstreamer()
    check_gstreamer_runtime(Gst, backend)

    source_pipeline = None
    source_sink = None
    source_bus = None
    csi_process = None
    csi_reader = None
    csi_stop = threading.Event()
    csi_error = {"message": ""}
    loop = GLib.MainLoop()
    active_media = {"appsrc": None, "prepared": False, "awaiting_idr": True}
    codec_config = {"sps": b"", "pps": b""}
    output_times: deque[float] = deque()
    capture_state = {"last_frame": None}
    state = {"value": "starting", "fps": None}

    def push_access_unit(data: bytes) -> None:
        capture_state["last_frame"] = time.monotonic()
        if state["value"] == "starting":
            state["value"] = "ready"

        metadata = inspect_h264_access_unit(data)
        if metadata["sps"]:
            codec_config["sps"] = metadata["sps"]
        if metadata["pps"]:
            codec_config["pps"] = metadata["pps"]

        appsrc = active_media["appsrc"]
        if appsrc is None or not active_media["prepared"]:
            return
        awaiting_idr = active_media["awaiting_idr"]
        if awaiting_idr:
            if not metadata["has_idr"]:
                return
            prefix = b""
            if not metadata["has_sps"]:
                prefix += codec_config["sps"]
            if not metadata["has_pps"]:
                prefix += codec_config["pps"]
            data = prefix + data
        if appsrc.get_property("current-level-bytes") >= 1048576:
            return
        buffer = Gst.Buffer.new_allocate(None, len(data), None)
        buffer.fill(0, data)
        result = appsrc.emit("push-buffer", buffer)
        if result == Gst.FlowReturn.OK:
            if awaiting_idr:
                active_media["awaiting_idr"] = False
        else:
            logging.debug("Dropping an H.264 access unit after appsrc returned %s", result)

    def push_sample(sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        encoded = sample.get_buffer()
        if encoded is None:
            return Gst.FlowReturn.ERROR
        push_access_unit(encoded.extract_dup(0, encoded.get_size()))
        return Gst.FlowReturn.OK

    if backend == "usb":
        try:
            source_pipeline = Gst.parse_launch(build_source_launch(camera_status))
        except Exception as error:
            raise GStreamerError(f"Unable to construct the USB H.264 pipeline: {error}") from error
        if source_pipeline is None:
            raise GStreamerError("GStreamer could not create the USB H.264 pipeline.")
        source_sink = source_pipeline.get_by_name("rtsp_sink")
        if source_sink is None:
            raise GStreamerError("USB H.264 source pipeline is missing its appsink.")
        source_sink.connect("new-sample", push_sample)

    server = GstRtspServer.RTSPServer()
    server.set_address("0.0.0.0")
    server.set_service(str(RTSP_PORT))
    mounts = server.get_mount_points()
    factory = GstRtspServer.RTSPMediaFactory()
    factory.set_shared(True)
    factory.set_launch(build_rtsp_launch())

    def count_streamed_frame(_pad, _info):
        now = time.monotonic()
        output_times.append(now)
        while output_times and output_times[0] < now - 2.0:
            output_times.popleft()
        if len(output_times) >= 2:
            elapsed = output_times[-1] - output_times[0]
            if elapsed > 0:
                state["fps"] = (len(output_times) - 1) / elapsed
        state["value"] = "publishing"
        return Gst.PadProbeReturn.OK

    def configure_media(_factory, media):
        element = media.get_element()
        appsrc = element.get_by_name("rtsp_source") if element is not None else None
        payloader = element.get_by_name("pay0") if element is not None else None
        if appsrc is None or payloader is None:
            logging.error("RTSP media pipeline is missing its H.264 appsrc or payloader")
            return
        active_media.update(appsrc=appsrc, prepared=False, awaiting_idr=True)
        sink_pad = payloader.get_static_pad("sink")
        if sink_pad is not None:
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, count_streamed_frame)

        def prepared(_media):
            if active_media["appsrc"] is appsrc:
                active_media["prepared"] = True

        def unprepared(_media):
            if active_media["appsrc"] is appsrc:
                active_media.update(appsrc=None, prepared=False, awaiting_idr=True)
                output_times.clear()
                state.update(value="ready", fps=None)

        media.connect("prepared", prepared)
        media.connect("unprepared", unprepared)

    factory.connect("media-configure", configure_media)
    mounts.add_factory(RTSP_PATH, factory)
    if server.attach(None) == 0:
        raise GStreamerError("GStreamer RTSP server could not attach to the main loop.")

    if source_pipeline is not None:
        source_bus = source_pipeline.get_bus()
        result = source_pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            raise GStreamerError("GStreamer could not start the USB H.264 camera source.")
        state_result, _current, _pending = source_pipeline.get_state(5 * Gst.SECOND)
        if state_result == Gst.StateChangeReturn.FAILURE:
            raise GStreamerError("The USB H.264 camera source failed to enter PLAYING.")

        source = source_pipeline.get_by_name("camera_source")
        pad = source.get_static_pad("src") if source is not None else None
        caps = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            caps = pad.get_current_caps() if pad is not None else None
            if caps is not None and not caps.is_empty():
                break
            time.sleep(0.1)
        if caps is None or caps.is_empty():
            source_pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("The USB camera did not negotiate H.264 capture caps.")
        structure = caps.get_structure(0)
        try:
            media_type = structure.get_name()
            width = int(structure.get_value("width"))
            height = int(structure.get_value("height"))
            rate_num, rate_den = structure.get_fraction("framerate")[1:]
            actual_fps = rate_num / rate_den
            stream_format = structure.get_string("stream-format")
            alignment = structure.get_string("alignment")
        except (AttributeError, TypeError, ValueError, ZeroDivisionError) as error:
            source_pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("The USB camera returned incomplete H.264 capture caps.") from error
        expected_width, expected_height, expected_fps = _validate_mode(camera_status)
        if (
            media_type != "video/x-h264"
            or width != expected_width
            or height != expected_height
            or abs(actual_fps - expected_fps) >= 0.1
            or stream_format != "byte-stream"
            or alignment != "au"
        ):
            source_pipeline.set_state(Gst.State.NULL)
            raise GStreamerError(
                f"USB camera negotiated {media_type} {width}x{height} at {actual_fps:g} FPS "
                f"({stream_format}/{alignment}); requested byte-stream H.264 access units "
                f"{expected_width}x{expected_height} at {expected_fps:g} FPS."
            )

    logging.info("H.264 RTSP endpoint: rtsp://%s:%s%s", _hostname(), RTSP_PORT, RTSP_PATH)
    write_status("starting", camera_status)

    started_at = time.monotonic()

    def csi_reader() -> None:
        assert csi_process is not None and csi_process.stdout is not None
        framer = H264AccessUnitFramer()
        try:
            while not csi_stop.is_set():
                chunk = csi_process.stdout.read(65536)
                if not chunk:
                    break
                for access_unit in framer.feed(chunk):
                    push_access_unit(access_unit)
            for access_unit in framer.flush():
                push_access_unit(access_unit)
            if not csi_stop.is_set():
                csi_error["message"] = "rpicam-vid stopped producing H.264 data."
        except Exception as error:
            csi_error["message"] = str(error)
            logging.exception("CSI H.264 access-unit framing failed")

    if backend == "csi":
        command = _csi_capture_command(camera_status)
        csi_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        csi_reader = threading.Thread(target=csi_reader, name="petcam-csi-h264-reader", daemon=True)
        csi_reader.start()

    def heartbeat():
        if source_bus is not None:
            message = source_bus.timed_pop_filtered(
                0, Gst.MessageType.ERROR | Gst.MessageType.EOS
            )
            if message is not None:
                if message.type == Gst.MessageType.ERROR:
                    error, debug = message.parse_error()
                    detail = f" ({debug})" if debug else ""
                    text = f"USB H.264 camera source failed: {error}{detail}"
                else:
                    text = "USB H.264 camera source reached end-of-stream."
                logging.error(text)
                write_status("error", camera_status, message=text)
                loop.quit()
                return False

        if csi_process is not None:
            code = csi_process.poll()
            if code is not None:
                text = csi_error["message"] or f"rpicam-vid exited with status {code}."
                logging.error(text)
                write_status("error", camera_status, message=text)
                loop.quit()
                return False

        now = time.monotonic()
        last_frame = capture_state["last_frame"]
        if last_frame is not None and now - last_frame > 3:
            output_times.clear()
            state.update(value="ready", fps=None)
        if last_frame is None and now - started_at > 12:
            text = "No H.264 access units received from the selected camera."
            logging.error(text)
            write_status("error", camera_status, message=text)
            loop.quit()
            return False
        write_status(state["value"], camera_status, state["fps"])
        return True

    GLib.timeout_add_seconds(1, heartbeat)

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        loop.run()
    finally:
        csi_stop.set()
        if csi_process is not None and csi_process.poll() is None:
            csi_process.terminate()
            try:
                csi_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                csi_process.kill()
                csi_process.wait(timeout=2)
        if csi_reader is not None and csi_reader.is_alive():
            csi_reader.join(timeout=2)
        if source_pipeline is not None:
            source_pipeline.set_state(Gst.State.NULL)
        write_status("stopped", camera_status)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    camera_status = load_camera_status()
    if not camera_status:
        logging.error("No active native H.264 camera capture was found.")
        return 1
    try:
        return run_server(camera_status)
    except Exception as error:
        logging.exception("Unable to start the H.264 RTSP server")
        try:
            write_status("error", camera_status, message=str(error))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
