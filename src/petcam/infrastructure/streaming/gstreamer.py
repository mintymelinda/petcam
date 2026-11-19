#!/usr/bin/env python3
"""Serve PetCam camera video over RTSP with GStreamer (no transcoding)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import shlex
import time
import threading
from pathlib import Path

STATUS_PATH = Path(os.environ.get("PETCAM_G_STREAMER_STATUS", "/run/petcam/g-streamer-status.json"))
RTSP_URL = "rtsp://127.0.0.1:8554/petcam"
CAMERA_STATUS_PATH = Path("/var/lib/petcam/camera-status.json")
FRAME_STATUS_PATH = Path("/run/petcam/rtsp-sampler-status.json")
STATE_PATH = Path(os.environ.get("PETCAM_STATE", "/var/lib/petcam"))
NATIVE_RTP_PORT = 5004


class GStreamerError(ValueError):
    """Raised when GStreamer runtime or camera metadata is invalid."""


def load_camera_status(path=CAMERA_STATUS_PATH):
    try:
        status = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(status, dict):
        return {}
    pid = status.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        return {}
    try:
        os.kill(pid, 0)
    except OSError:
        return {}
    return status


def native_h264_available(status_url=None, timeout=0, marker_path=CAMERA_STATUS_PATH):
    """Detect the native V4L2 H.264 capture selection held by petcam-stream."""
    del status_url, timeout
    status = load_camera_status(marker_path)
    return status.get("native_h264") is True and (bool(status.get("device")) or status.get("backend") == "csi")


def build_gstreamer_launch(camera_status, mjpeg_url="http://127.0.0.1:8081/stream"):
    """Build a GStreamer RTSP factory pipeline; compressed video is never decoded."""
    if camera_status.get("native_h264") is True:
        resolution = camera_status.get("resolution", "")
        fps = camera_status.get("fps", "")
        if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", str(resolution)):
            raise GStreamerError("Native H.264 resolution is invalid.")
        if not re.fullmatch(r"[1-9][0-9]{0,2}", str(fps)):
            raise GStreamerError("Native H.264 frame rate is invalid.")
        width, height = resolution.split("x", 1)
        if camera_status.get("backend") == "csi":
            port = camera_status.get("tcp_port", 8556)
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise GStreamerError("CSI H.264 bridge port is invalid.")
            return (
                f"( tcpclientsrc host=127.0.0.1 port={port} do-timestamp=true ! "
                "h264parse config-interval=-1 ! video/x-h264,alignment=au ! "
                "rtph264pay name=pay0 pt=96 config-interval=1 )"
            )
        device = camera_status.get("device", "")
        if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+_-]+)", device):
            raise GStreamerError("Native H.264 camera device path is invalid.")
        return (
            f"( v4l2src device={shlex.quote(device)} ! "
            f"video/x-h264,width={width},height={height},framerate={fps}/1 ! "
            "h264parse config-interval=-1 ! video/x-h264,alignment=au ! "
            "rtph264pay name=pay0 pt=96 config-interval=1 )"
        )
    if mjpeg_url != "http://127.0.0.1:8081/stream":
        raise GStreamerError("MJPEG source URL must be the local PetCam stream.")
    return (
        '( souphttpsrc location="http://127.0.0.1:8081/stream" is-live=true do-timestamp=true ! '
        "multipartdemux ! jpegparse ! rtpjpegpay name=pay0 pt=26 )"
    )


def refresh_camera_source(factory, camera_status, active_launch, active_source):
    """Apply newly discovered capture metadata to future RTSP media sessions."""
    launch = build_gstreamer_launch(camera_status)
    source = (
        ("native_h264_csi" if camera_status.get("backend") == "csi" else "native_h264")
        if camera_status.get("native_h264") is True else "mjpeg_copy"
    )
    if launch == active_launch["value"]:
        return False
    factory.set_launch(launch)
    active_launch["value"] = launch
    active_source["value"] = source
    return True


def _write_status(state, source, path=STATUS_PATH, fps=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "active": state == "publishing",
        "fps": round(fps, 2) if isinstance(fps, (int, float)) and fps > 0 else None,
        "updated_at": time.time(),
        "source": source,
    }
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _set_status_state(current_state, state, source, path=STATUS_PATH):
    """Update the in-memory lifecycle state and publish it immediately."""
    current_state["value"] = state
    _write_status(state, source, path, current_state.get("fps"))


def _write_heartbeat(current_state, source, path=STATUS_PATH):
    """Refresh the heartbeat and discard stale frame-rate measurements."""
    last_frame_at = current_state.get("last_frame_at")
    if last_frame_at is None or time.monotonic() - last_frame_at > 3.0:
        current_state["fps"] = None
    _write_status(current_state["value"], source, path, current_state.get("fps"))
    return True


def check_gstreamer_runtime():
    """Validate the RTSP server bindings and the elements used by both camera modes."""
    _GLib, Gst, _GstRtspServer = _load_gstreamer()
    required = (
        "v4l2src", "tcpclientsrc", "h264parse", "rtph264pay", "souphttpsrc",
        "multipartdemux", "jpegparse", "rtpjpegpay", "tee", "queue", "valve",
        "videoconvert", "videorate", "jpegenc", "appsink", "udpsrc", "udpsink",
        "rtpjitterbuffer", "rtph264depay",
    )
    missing = [name for name in required if Gst.ElementFactory.find(name) is None]
    if missing:
        raise GStreamerError("Required GStreamer element(s) are missing: " + ", ".join(missing))
    return True


def _load_gstreamer():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtspServer", "1.0")
        from gi.repository import GLib, Gst, GstRtspServer
    except (ImportError, ValueError) as error:
        raise GStreamerError(
            "GStreamer RTSP Server bindings are missing. Install python3-gi and gir1.2-gst-rtsp-server-1.0."
        ) from error
    Gst.init(None)
    return GLib, Gst, GstRtspServer


def configure_rtsp_server(server):
    """Bind RTSP on IPv6 with dual-stack IPv4 compatibility."""
    server.set_address("::")
    server.set_service("8554")


def frame_consumers_enabled(state_path=STATE_PATH):
    """Return whether motion or timelapse currently needs decoded frames."""
    for feature in ("motion", "timelapse"):
        try:
            payload = json.loads(
                (Path(state_path) / feature / "config.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("enabled") is True:
            return True
    return False


def build_native_capture_launch(camera_status, decoder_name="avdec_h264", rtp_port=NATIVE_RTP_PORT):
    """Build one persistent H.264 source with independent RTSP and sampled-frame branches."""
    if decoder_name not in {"v4l2h264dec", "avdec_h264"}:
        raise GStreamerError(f"Unsupported H.264 decoder: {decoder_name!r}")
    resolution = camera_status.get("resolution", "")
    fps = camera_status.get("fps", "")
    if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", str(resolution)):
        raise GStreamerError("Native H.264 resolution is invalid.")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", str(fps)):
        raise GStreamerError("Native H.264 frame rate is invalid.")
    if not isinstance(rtp_port, int) or not 1 <= rtp_port <= 65535:
        raise GStreamerError("Native H.264 RTP bridge port is invalid.")

    if camera_status.get("backend") == "csi":
        port = camera_status.get("tcp_port", 8556)
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise GStreamerError("CSI H.264 bridge port is invalid.")
        source = f"tcpclientsrc host=127.0.0.1 port={port} do-timestamp=true"
    else:
        device = camera_status.get("device", "")
        if not re.fullmatch(r"/dev/(?:video[0-9]+|v4l/by-id/[A-Za-z0-9._:+_-]+)", device):
            raise GStreamerError("Native H.264 camera device path is invalid.")
        width, height = resolution.split("x", 1)
        source = (
            f"v4l2src device={shlex.quote(device)} ! "
            f"video/x-h264,width={width},height={height},framerate={fps}/1"
        )

    return (
        f"{source} ! h264parse config-interval=-1 ! tee name=source_tee "
        "source_tee. ! queue max-size-buffers=60 leaky=downstream ! "
        "h264parse config-interval=-1 ! rtph264pay name=rtp_pay pt=96 config-interval=1 ! "
        f"udpsink host=127.0.0.1 port={rtp_port} sync=false async=false "
        "source_tee. ! queue max-size-buffers=4 leaky=downstream ! "
        "h264parse ! video/x-h264,stream-format=byte-stream,alignment=au ! "
        "valve name=frame_valve drop=true ! "
        f"{decoder_name} name=frame_decoder ! videoconvert ! videorate drop-only=true max-rate=1 ! "
        "video/x-raw,framerate=1/1 ! jpegenc quality=85 ! "
        "appsink name=frame_sink emit-signals=true max-buffers=1 drop=true "
        "sync=false wait-on-eos=false"
    )


def build_native_rtsp_launch(rtp_port=NATIVE_RTP_PORT):
    """Expose the persistent capture pipeline's local RTP feed through RTSP."""
    if not isinstance(rtp_port, int) or not 1 <= rtp_port <= 65535:
        raise GStreamerError("Native H.264 RTP bridge port is invalid.")
    return (
        f'( udpsrc port={rtp_port} buffer-size=1048576 '
        'caps="application/x-rtp,media=(string)video,clock-rate=(int)90000,'
        'encoding-name=(string)H264,payload=(int)96" ! '
        "rtpjitterbuffer latency=0 ! rtph264depay ! "
        "h264parse config-interval=-1 ! "
        "rtph264pay name=pay0 pt=96 config-interval=1 )"
    )


def _write_frame_status(state, codec="H264", path=FRAME_STATUS_PATH, error=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "codec": codec,
        "updated_at": time.time(),
        "last_error": error,
    }
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def camera_status_signature(camera_status):
    """Return the fields that require the native capture pipeline to be rebuilt."""
    return tuple(
        camera_status.get(key)
        for key in ("pid", "backend", "device", "camera", "tcp_port", "resolution", "fps", "native_h264")
    )


def _run_native_h264_server(GLib, Gst, GstRtspServer, mounts, camera_status, source):
    """Keep RTSP mounted while independently replacing the persistent camera pipeline."""
    from petcam.infrastructure.streaming import sampler

    frame_buffer = sampler.LatestFrameBuffer()
    frame_server = sampler.FrameServer(sampler.SOCKET_PATH, frame_buffer)
    frame_thread = threading.Thread(
        target=frame_server.serve_forever, name="petcam-frame-socket", daemon=True
    )
    frame_thread.start()

    frame_state = {"enabled": frame_consumers_enabled(), "published": False}
    current_state = {"value": "starting", "fps": None, "source": source}
    active = {"pipeline": None, "bus": None, "signature": None}
    frame_times = []

    def sample_ready(sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        success, mapped = buffer.map(Gst.MapFlags.READ)
        if success:
            try:
                if frame_state["enabled"]:
                    frame_buffer.publish(bytes(mapped.data))
                    if not frame_state["published"]:
                        frame_state["published"] = True
                        _write_frame_status("streaming")
            finally:
                buffer.unmap(mapped)
        return Gst.FlowReturn.OK

    def count_frame(_pad, _info):
        now = time.monotonic()
        frame_times.append(now)
        current_state["last_frame_at"] = now
        cutoff = now - 2.0
        while frame_times and frame_times[0] < cutoff:
            frame_times.pop(0)
        if len(frame_times) >= 2:
            elapsed = frame_times[-1] - frame_times[0]
            if elapsed > 0:
                current_state["fps"] = (len(frame_times) - 1) / elapsed
        if current_state["value"] != "publishing":
            _set_status_state(current_state, "publishing", current_state["source"])
        return Gst.PadProbeReturn.OK

    def stop_capture_pipeline():
        pipeline = active["pipeline"]
        if pipeline is not None:
            pipeline.set_state(Gst.State.NULL)
        active.update(pipeline=None, bus=None, signature=None)
        frame_buffer.clear()
        frame_state["published"] = False
        frame_times.clear()
        current_state["fps"] = None
        current_state["last_frame_at"] = None
        _set_status_state(current_state, "ready", current_state["source"])

    def start_capture_pipeline(status):
        decoder_name = sampler.select_h264_decoder(Gst)
        required = ("valve", "videoconvert", "videorate", "jpegenc", "appsink", decoder_name)
        missing = [name for name in required if Gst.ElementFactory.find(name) is None]
        if missing:
            raise GStreamerError(
                "Required H.264 frame-branch element(s) are missing: " + ", ".join(missing)
            )

        pipeline = Gst.parse_launch(build_native_capture_launch(status, decoder_name))
        if pipeline is None:
            raise GStreamerError("GStreamer could not create the persistent H.264 capture pipeline.")
        frame_valve = pipeline.get_by_name("frame_valve")
        frame_decoder = pipeline.get_by_name("frame_decoder")
        frame_sink = pipeline.get_by_name("frame_sink")
        rtp_pay = pipeline.get_by_name("rtp_pay")
        if frame_valve is None or frame_decoder is None or frame_sink is None or rtp_pay is None:
            pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("The persistent H.264 pipeline is missing a required branch element.")
        if decoder_name == "v4l2h264dec":
            frame_decoder.set_property("capture-io-mode", 2)
            frame_decoder.set_property("output-io-mode", 2)

        frame_sink.connect("new-sample", sample_ready)
        frame_valve.set_property("drop", not frame_state["enabled"])
        sink_pad = rtp_pay.get_static_pad("sink")
        if sink_pad is not None:
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, count_frame)

        result = pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("GStreamer could not start the persistent H.264 capture pipeline.")
        state_result, _current, _pending = pipeline.get_state(5 * Gst.SECOND)
        if state_result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("The persistent H.264 capture pipeline failed to enter PLAYING.")

        active.update(
            pipeline=pipeline,
            bus=pipeline.get_bus(),
            signature=camera_status_signature(status),
        )
        current_state["source"] = (
            "native_h264_csi" if status.get("backend") == "csi" else "native_h264"
        )
        _write_frame_status("decoding" if frame_state["enabled"] else "disabled")
        _set_status_state(current_state, "ready", current_state["source"])
        logging.info(
            "Persistent H.264 capture pipeline started at %s %s FPS with %s decoder",
            status.get("resolution"), status.get("fps"), decoder_name,
        )

    def reconcile_camera_source():
        latest = load_camera_status()
        if not latest:
            if active["pipeline"] is not None:
                logging.info("Camera capture marker disappeared; holding RTSP server for camera restart")
                stop_capture_pipeline()
            return True
        if latest.get("native_h264") is not True:
            if active["pipeline"] is not None:
                stop_capture_pipeline()
            logging.error("Camera source changed away from native H.264; RTSP server requires mode restart")
            return True

        signature = camera_status_signature(latest)
        if signature != active["signature"]:
            if active["pipeline"] is not None:
                logging.info(
                    "Camera mode changed to %s at %s FPS; rebuilding capture while keeping RTSP mounted",
                    latest.get("resolution"), latest.get("fps"),
                )
                stop_capture_pipeline()
            try:
                start_capture_pipeline(latest)
            except Exception:
                logging.exception("Unable to start the updated native H.264 camera pipeline")
                _write_frame_status("error", error="Updated H.264 capture pipeline failed to start")
        return True

    def reconcile_frame_branch():
        enabled = frame_consumers_enabled()
        if enabled != frame_state["enabled"]:
            frame_state["enabled"] = enabled
            frame_state["published"] = False
            frame_buffer.clear()
            pipeline = active["pipeline"]
            valve = pipeline.get_by_name("frame_valve") if pipeline is not None else None
            if valve is not None:
                valve.set_property("drop", not enabled)
            _write_frame_status("decoding" if enabled else "disabled")
        return True

    factory = GstRtspServer.RTSPMediaFactory()
    factory.set_shared(True)
    factory.set_launch(build_native_rtsp_launch())

    def media_configured(_factory, media):
        media.connect(
            "prepared",
            lambda _media: (
                _set_status_state(current_state, "publishing", current_state["source"])
                if active["pipeline"] is not None else None
            ),
        )

    factory.connect("media-configure", media_configured)
    mounts.add_factory("/petcam", factory)

    loop = GLib.MainLoop()

    def check_capture_bus():
        bus = active["bus"]
        if bus is None:
            return True
        message = bus.timed_pop_filtered(
            0, Gst.MessageType.ERROR | Gst.MessageType.EOS
        )
        if message is not None:
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                logging.error("Persistent H.264 capture pipeline failed: %s; %s", error, debug or "")
            else:
                logging.error("Persistent H.264 capture pipeline reached EOS.")
            stop_capture_pipeline()
        return True

    def heartbeat():
        last_frame_at = current_state.get("last_frame_at")
        if last_frame_at is not None and time.monotonic() - last_frame_at > 3.0:
            current_state["fps"] = None
            if current_state["value"] == "publishing":
                _set_status_state(current_state, "ready", current_state["source"])
        _write_heartbeat(current_state, current_state["source"])
        return True

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    GLib.timeout_add_seconds(1, check_capture_bus)
    GLib.timeout_add_seconds(1, reconcile_camera_source)
    GLib.timeout_add_seconds(2, reconcile_frame_branch)
    GLib.timeout_add_seconds(2, heartbeat)
    try:
        start_capture_pipeline(camera_status)
        loop.run()
    finally:
        stop_capture_pipeline()
        _write_frame_status("stopped")
        frame_server.shutdown()
        frame_server.server_close()
        frame_thread.join(timeout=2)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate GStreamer RTSP dependencies and camera selection")
    args = parser.parse_args()
    camera_status = load_camera_status()
    native_h264 = camera_status.get("native_h264") is True
    source = (
        ("native_h264_csi" if camera_status.get("backend") == "csi" else "native_h264")
        if native_h264 else "mjpeg_copy"
    )
    launch = build_gstreamer_launch(camera_status)
    check_gstreamer_runtime()
    GLib, Gst, GstRtspServer = _load_gstreamer()
    if args.check:
        output = {
            "source": source,
            "pipeline": launch,
            "rtsp_url": "rtsp://<petcam-host>:8554/petcam",
        }
        if native_h264:
            from petcam.infrastructure.streaming import sampler

            output["pipeline"] = build_native_capture_launch(
                camera_status, sampler.select_h264_decoder(Gst)
            )
            output["rtsp_pipeline"] = build_native_rtsp_launch()
        print(json.dumps(output))
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = GstRtspServer.RTSPServer()
    configure_rtsp_server(server)
    mounts = server.get_mount_points()

    if native_h264:
        if server.attach(None) == 0:
            raise GStreamerError("GStreamer RTSP server could not attach to the GLib main context.")
        _run_native_h264_server(GLib, Gst, GstRtspServer, mounts, camera_status, source)
        return

    factory = GstRtspServer.RTSPMediaFactory()
    factory.set_shared(True)
    factory.set_launch(launch)

    current_state = {"value": "starting", "fps": None}
    frame_times = []

    def set_state(state):
        _set_status_state(current_state, state, source)

    def count_frame(_pad, _info):
        now = time.monotonic()
        frame_times.append(now)
        current_state["last_frame_at"] = now
        cutoff = now - 2.0
        while frame_times and frame_times[0] < cutoff:
            frame_times.pop(0)
        if len(frame_times) >= 2:
            elapsed = frame_times[-1] - frame_times[0]
            if elapsed > 0:
                current_state["fps"] = (len(frame_times) - 1) / elapsed
        return Gst.PadProbeReturn.OK

    def media_unprepared(_media):
        current_state["fps"] = None
        current_state["last_frame_at"] = None
        frame_times.clear()
        set_state("ready")

    def media_configured(_factory, media):
        logging.info("GStreamer RTSP media configured from %s", source)
        element = media.get_element()
        payloader = element.get_by_name("pay0") if element else None
        sink_pad = payloader.get_static_pad("sink") if payloader else None
        if sink_pad is not None:
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, count_frame)
        media.connect("prepared", lambda _media: set_state("publishing"))
        media.connect("unprepared", media_unprepared)

    factory.connect("media-configure", media_configured)
    mounts.add_factory("/petcam", factory)
    if server.attach(None) == 0:
        raise GStreamerError("GStreamer RTSP server could not attach to the GLib main context.")
    set_state("ready")
    GLib.timeout_add_seconds(2, lambda: _write_heartbeat(current_state, source))
    logging.info("Serving %s directly over RTSP at %s", source, RTSP_URL)
    loop = GLib.MainLoop()

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        loop.run()
    finally:
        _write_status("stopped", source)


if __name__ == "__main__":
    main()
