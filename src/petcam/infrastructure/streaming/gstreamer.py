#!/usr/bin/env python3
"""Publish a camera's already-encoded H.264 access units over RTSP."""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

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
    """Build an H.264-only source pipeline; no decoder or fallback is present."""
    if status.get("native_h264") is not True:
        raise GStreamerError("PetCam accepts only native H.264 camera sources.")
    width, height, fps = _validate_mode(status)
    common = (
        " ! h264parse config-interval=-1 ! "
        "video/x-h264,stream-format=byte-stream,alignment=au ! "
        "appsink name=rtsp_sink emit-signals=true max-buffers=2 drop=true "
        "sync=false wait-on-eos=false"
    )
    if status.get("backend") == "usb":
        device = str(status.get("device", ""))
        if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+-]+)", device):
            raise GStreamerError("Configured USB camera device path is invalid.")
        escaped_device = device.replace("\\", "\\\\").replace('"', '\\"')
        frame_rate = Fraction(str(fps)).limit_denominator(1001)
        return (
            f'v4l2src name=camera_source device="{escaped_device}" do-timestamp=true'
            f" ! video/x-h264,width={width},height={height},framerate={frame_rate.numerator}/{frame_rate.denominator}"
            + common
        )
    if status.get("backend") == "csi":
        port = status.get("tcp_port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise GStreamerError("Configured CSI H.264 bridge port is invalid.")
        return f"tcpclientsrc host=127.0.0.1 port={port} do-timestamp=true" + common
    raise GStreamerError("Configured camera source must be USB or CSI.")


def build_rtsp_launch() -> str:
    """Bridge encoded H.264 access units into the RTSP payloader unchanged."""
    return (
        "( appsrc name=rtsp_source is-live=true format=time do-timestamp=true "
        "block=false max-bytes=1048576 "
        "caps=video/x-h264,stream-format=byte-stream,alignment=au ! "
        "h264parse config-interval=-1 ! "
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
    required = ["h264parse", "appsink", "appsrc", "rtph264pay"]
    required.append("v4l2src" if backend == "usb" else "tcpclientsrc")
    missing = [name for name in required if Gst.ElementFactory.find(name) is None]
    if missing:
        raise GStreamerError("Missing H.264 GStreamer element(s): " + ", ".join(missing))


def _hostname() -> str:
    try:
        return socket.getfqdn() or socket.gethostname()
    except OSError:
        return "<device-hostname>"


def run_server(camera_status: dict) -> int:
    GLib, Gst, GstRtspServer = _load_gstreamer()
    check_gstreamer_runtime(Gst, str(camera_status.get("backend")))

    try:
        source_pipeline = Gst.parse_launch(build_source_launch(camera_status))
    except Exception as error:
        raise GStreamerError(f"Unable to construct the H.264 camera pipeline: {error}") from error
    if source_pipeline is None:
        raise GStreamerError("GStreamer could not create the H.264 camera pipeline.")
    source_sink = source_pipeline.get_by_name("rtsp_sink")
    if source_sink is None:
        raise GStreamerError("H.264 source pipeline is missing its appsink.")

    loop = GLib.MainLoop()
    active_media = {"appsrc": None, "prepared": False}
    output_times: deque[float] = deque()
    capture_state = {"last_frame": None}
    state = {"value": "starting", "fps": None}

    def push_sample(sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        capture_state["last_frame"] = time.monotonic()
        appsrc = active_media["appsrc"]
        if appsrc is not None and active_media["prepared"]:
            if appsrc.get_property("current-level-bytes") < 1048576:
                source_buffer = sample.get_buffer()
                if source_buffer is not None:
                    buffer = source_buffer.copy()
                    buffer.pts = Gst.CLOCK_TIME_NONE
                    buffer.dts = Gst.CLOCK_TIME_NONE
                    buffer.duration = Gst.CLOCK_TIME_NONE
                    result = appsrc.emit("push-buffer", buffer)
                    if result not in (Gst.FlowReturn.OK, Gst.FlowReturn.FLUSHING):
                        logging.debug("Dropping an H.264 access unit after appsrc returned %s", result)
        if state["value"] == "starting":
            state["value"] = "ready"
        return Gst.FlowReturn.OK

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
        active_media.update(appsrc=appsrc, prepared=False)
        sink_pad = payloader.get_static_pad("sink")
        if sink_pad is not None:
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, count_streamed_frame)

        def prepared(_media):
            if active_media["appsrc"] is appsrc:
                active_media["prepared"] = True

        def unprepared(_media):
            if active_media["appsrc"] is appsrc:
                active_media.update(appsrc=None, prepared=False)
                output_times.clear()
                state.update(value="ready", fps=None)

        media.connect("prepared", prepared)
        media.connect("unprepared", unprepared)

    factory.connect("media-configure", configure_media)
    mounts.add_factory(RTSP_PATH, factory)
    if server.attach(None) == 0:
        raise GStreamerError("GStreamer RTSP server could not attach to the main loop.")

    source_bus = source_pipeline.get_bus()
    result = source_pipeline.set_state(Gst.State.PLAYING)
    if result == Gst.StateChangeReturn.FAILURE:
        raise GStreamerError("GStreamer could not start the H.264 camera source.")
    state_result, _current, _pending = source_pipeline.get_state(5 * Gst.SECOND)
    if state_result == Gst.StateChangeReturn.FAILURE:
        raise GStreamerError("The H.264 camera source failed to enter PLAYING.")

    def verify_usb_caps() -> None:
        if camera_status.get("backend") != "usb":
            return
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
            raise GStreamerError("The USB camera did not negotiate capture caps.")
        structure = caps.get_structure(0)
        try:
            media_type = structure.get_name()
            width = int(structure.get_value("width"))
            height = int(structure.get_value("height"))
            rate_num, rate_den = structure.get_fraction("framerate")[1:]
            actual_fps = rate_num / rate_den
        except (AttributeError, TypeError, ValueError, ZeroDivisionError) as error:
            raise GStreamerError("The USB camera returned incomplete H.264 capture caps.") from error
        expected_width, expected_height, expected_fps = _validate_mode(camera_status)
        if (
            media_type != "video/x-h264"
            or width != expected_width
            or height != expected_height
            or abs(actual_fps - expected_fps) >= 0.1
        ):
            raise GStreamerError(
                f"USB camera negotiated {media_type} {width}x{height} at {actual_fps:g} FPS; "
                f"requested H.264 {expected_width}x{expected_height} at {expected_fps:g} FPS."
            )

    verify_usb_caps()
    logging.info("H.264 RTSP endpoint: rtsp://%s:%s%s", _hostname(), RTSP_PORT, RTSP_PATH)
    write_status("starting", camera_status)

    def heartbeat():
        message = source_bus.timed_pop_filtered(
            0, Gst.MessageType.ERROR | Gst.MessageType.EOS
        )
        if message is not None:
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                detail = f" ({debug})" if debug else ""
                text = f"H.264 camera source failed: {error}{detail}"
            else:
                text = "H.264 camera source reached end-of-stream."
            logging.error(text)
            write_status("error", camera_status, message=text)
            loop.quit()
            return False

        now = time.monotonic()
        last_frame = capture_state["last_frame"]
        if last_frame is not None and now - last_frame > 3:
            output_times.clear()
            state.update(value="ready", fps=None)
        if last_frame is None and now - started_at[0] > 12:
            text = "No H.264 frames received from the selected camera."
            logging.error(text)
            write_status("error", camera_status, message=text)
            loop.quit()
            return False
        write_status(state["value"], camera_status, state["fps"])
        return True

    started_at = [time.monotonic()]
    GLib.timeout_add_seconds(1, heartbeat)

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        loop.run()
    finally:
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
