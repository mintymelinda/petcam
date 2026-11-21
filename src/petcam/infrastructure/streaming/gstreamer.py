#!/usr/bin/env python3
"""Serve PetCam camera video over RTSP with GStreamer (no transcoding)."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
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
FALLBACK_REQUEST_PATH = Path(os.environ.get("PETCAM_RUN", "/run/petcam")) / "camera-fallback-request.json"
STATE_PATH = Path(os.environ.get("PETCAM_STATE", "/var/lib/petcam"))
RTSP_QUEUE_MAX_BYTES = 100 * 1024 * 1024


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


def _framerate_caps(fps):
    """Convert an advertised decimal FPS into a valid GStreamer fraction."""
    try:
        value = Fraction(str(fps)).limit_denominator(1001)
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise GStreamerError("Native H.264 frame rate is invalid.") from error
    if value <= 0:
        raise GStreamerError("Native H.264 frame rate is invalid.")
    return f"{value.numerator}/{value.denominator}"


def build_gstreamer_launch(camera_status, mjpeg_url="http://127.0.0.1:8081/stream"):
    """Build a GStreamer RTSP factory pipeline; compressed video is never decoded."""
    if camera_status.get("native_h264") is True:
        resolution = camera_status.get("resolution", "")
        fps = camera_status.get("fps", "")
        if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", str(resolution)):
            raise GStreamerError("Native H.264 resolution is invalid.")
        framerate = _framerate_caps(fps)
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
            f"video/x-h264,width={width},height={height},framerate={framerate} ! "
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


def request_camera_fallback(camera_status, reason, path=FALLBACK_REQUEST_PATH):
    """Ask the camera owner to switch from automatic native H.264 to MJPEG."""
    if camera_status.get("native_h264") is not True or camera_status.get("automatic_format") is not True:
        return False
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": camera_status.get("owner_pid") or camera_status.get("pid"),
        "reason": str(reason),
        "requested_at": time.time(),
    }
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    logging.error("Requesting automatic camera fallback from native H.264: %s", reason)
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
        "videorate", "jpegenc", "appsink", "appsrc", "v4l2h264dec",
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


def verify_native_h264_v4l2_caps(pipeline, camera_status):
    """Confirm the live V4L2 source negotiated the requested H.264 mode."""
    source = pipeline.get_by_name("camera_source")
    if source is None:
        raise GStreamerError("Native H.264 pipeline is missing its V4L2 source.")
    pad = source.get_static_pad("src")
    caps = pad.get_current_caps() if pad is not None else None
    if caps is None or caps.is_empty():
        raise GStreamerError("V4L2 did not negotiate capture caps; refusing to report the requested camera mode as active.")
    structure = caps.get_structure(0)
    expected_width, expected_height = (int(value) for value in camera_status["resolution"].split("x", 1))
    expected_fps = float(camera_status["fps"])
    try:
        media_type = structure.get_name()
        width = structure.get_value("width")
        height = structure.get_value("height")
        fraction = structure.get_fraction("framerate")
        if not fraction or not fraction[0]:
            raise ValueError("Missing framerate")
        numerator, denominator = fraction[1], fraction[2]
        actual_fps = float(numerator) / float(denominator)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError) as error:
        raise GStreamerError("V4L2 returned incomplete or invalid negotiated capture caps.") from error
    if media_type != "video/x-h264" or int(width) != expected_width or int(height) != expected_height or abs(actual_fps - expected_fps) >= 0.1:
        raise GStreamerError(f"V4L2 negotiated {media_type} {width}x{height} at {actual_fps:g} FPS, but PetCam requested H.264 {expected_width}x{expected_height} at {expected_fps:g} FPS.")
    logging.info("V4L2 negotiated native H.264 capture caps: %sx%s at %s FPS", width, height, actual_fps)

def build_native_capture_launch(camera_status):
    """Build one persistent H.264 source with hardware-decoded sampled frames."""
    resolution = camera_status.get("resolution", "")
    fps = camera_status.get("fps", "")
    if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", str(resolution)):
        raise GStreamerError("Native H.264 resolution is invalid.")
    framerate = _framerate_caps(fps)

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
            f"v4l2src name=camera_source device={shlex.quote(device)} ! "
            f"video/x-h264,width={width},height={height},framerate={framerate}"
        )

    return (
        f"{source} ! h264parse config-interval=-1 ! "
        "video/x-h264,stream-format=byte-stream,alignment=au ! tee name=source_tee "
        f"source_tee. ! queue max-size-buffers=0 max-size-bytes={RTSP_QUEUE_MAX_BYTES} "
        "max-size-time=0 leaky=downstream ! "
        "appsink name=rtsp_sink emit-signals=true max-buffers=2 drop=true "
        "sync=false wait-on-eos=false "
        "source_tee. ! queue max-size-buffers=4 leaky=downstream ! "
        "valve name=frame_valve drop=true ! h264parse ! "
        "video/x-h264,stream-format=byte-stream,alignment=au ! "
        "v4l2h264dec name=frame_decoder ! video/x-raw,format=I420 ! "
        "videorate drop-only=true max-rate=1 ! "
        "video/x-raw,framerate=1/1 ! jpegenc quality=85 ! "
        "appsink name=frame_sink emit-signals=true max-buffers=1 drop=true "
        "sync=false wait-on-eos=false"
    )


def build_native_rtsp_launch():
    """Accept encoded access units directly from the persistent capture pipeline."""
    return (
        "( appsrc name=rtsp_source is-live=true format=time do-timestamp=true min-latency=0 "
        "block=false emit-signals=false max-bytes=1048576 "
        "caps=video/x-h264,stream-format=byte-stream,alignment=au ! "
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


def track_rtsp_client(clients, client):
    """Track and log a connected RTSP client until its control connection closes."""
    if client in clients:
        return

    clients.append(client)
    logging.info("RTSP client connected (%d active)", len(clients))

    def forget_closed_client(closed_client):
        try:
            clients.remove(closed_client)
        except ValueError:
            pass
        logging.info("RTSP client disconnected (%d active)", len(clients))

    client.connect("closed", forget_closed_client)


def retain_rtsp_clients(clients, reason):
    """Keep existing RTSP sessions alive while the native camera source is rebuilt."""
    if clients:
        logging.info("Retaining %d RTSP client session(s) during %s", len(clients), reason)
    return len(clients)


def close_rtsp_clients(clients, reason):
    """Close existing RTSP control connections so clients negotiate fresh media."""
    pending = tuple(clients)
    if pending:
        logging.info("Closing %d RTSP client connection(s): %s", len(pending), reason)

    for client in pending:
        try:
            client.close()
        except Exception:
            logging.exception("Unable to close an RTSP client connection")
        finally:
            try:
                clients.remove(client)
            except ValueError:
                pass

    return len(pending)


def _run_native_h264_server(GLib, Gst, GstRtspServer, server, mounts, camera_status, source):
    """Keep RTSP mounted while replacing capture and reconnecting stale RTSP clients."""
    from petcam.infrastructure.streaming import sampler

    frame_buffer = sampler.LatestFrameBuffer()
    frame_server = sampler.FrameServer(sampler.SOCKET_PATH, frame_buffer)
    frame_thread = threading.Thread(
        target=frame_server.serve_forever, name="petcam-frame-socket", daemon=True
    )
    frame_thread.start()

    frame_state = {"enabled": frame_consumers_enabled(), "published": False}
    current_state = {"value": "starting", "fps": None, "source": source}
    active = {"pipeline": None, "bus": None, "signature": None, "started_at": None, "fallback_requested": False}
    camera_unavailable = {"value": False}
    rtsp_clients = []
    rtsp_media = {"appsrc": None, "prepared": False}
    frame_times = []

    def rtsp_sample_ready(sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        appsrc = rtsp_media["appsrc"]
        if appsrc is not None and rtsp_media["prepared"]:
            # Keep the RTSP appsrc bounded if a slow client cannot consume in real time.
            if appsrc.get_property("current-level-bytes") < 1048576:
                result = appsrc.emit("push-sample", sample)
                if result not in (Gst.FlowReturn.OK, Gst.FlowReturn.FLUSHING):
                    logging.debug("Dropping H.264 access unit after RTSP appsrc returned %s", result)
        return Gst.FlowReturn.OK

    def client_connected(_server, client):
        track_rtsp_client(rtsp_clients, client)

    server.connect("client-connected", client_connected)

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
        active.update(pipeline=None, bus=None, signature=None, started_at=None, fallback_requested=False)
        frame_buffer.clear()
        frame_state["published"] = False
        frame_times.clear()
        current_state["fps"] = None
        current_state["last_frame_at"] = None
        _set_status_state(current_state, "ready", current_state["source"])

    def start_capture_pipeline(status):
        decoder_name = sampler.require_h264_hardware_decoder(Gst)
        required = ("valve", "videorate", "jpegenc", "appsink", decoder_name)
        missing = [name for name in required if Gst.ElementFactory.find(name) is None]
        if missing:
            raise GStreamerError(
                "Required H.264 frame-branch element(s) are missing: " + ", ".join(missing)
            )

        pipeline = Gst.parse_launch(build_native_capture_launch(status))
        if pipeline is None:
            raise GStreamerError("GStreamer could not create the persistent H.264 capture pipeline.")
        frame_valve = pipeline.get_by_name("frame_valve")
        frame_decoder = pipeline.get_by_name("frame_decoder")
        frame_sink = pipeline.get_by_name("frame_sink")
        rtsp_sink = pipeline.get_by_name("rtsp_sink")
        if frame_valve is None or frame_decoder is None or frame_sink is None or rtsp_sink is None:
            pipeline.set_state(Gst.State.NULL)
            raise GStreamerError("The persistent H.264 pipeline is missing a required branch element.")
        frame_decoder.set_property("capture-io-mode", 2)
        frame_decoder.set_property("output-io-mode", 2)

        frame_sink.connect("new-sample", sample_ready)
        rtsp_sink.connect("new-sample", rtsp_sample_ready)
        frame_valve.set_property("drop", not frame_state["enabled"])
        sink_pad = rtsp_sink.get_static_pad("sink")
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
        bus = pipeline.get_bus()
        error_message = bus.pop_filtered(Gst.MessageType.ERROR)
        if error_message is not None:
            error, debug = error_message.parse_error()
            pipeline.set_state(Gst.State.NULL)
            detail = f": {debug}" if debug else ""
            raise GStreamerError(f"Native H.264 capture negotiation failed: {error}{detail}")
        if status.get("backend") != "csi":
            try:
                verify_native_h264_v4l2_caps(pipeline, status)
            except GStreamerError:
                pipeline.set_state(Gst.State.NULL)
                raise

        active.update(
            pipeline=pipeline,
            bus=bus,
            signature=camera_status_signature(status),
            started_at=time.monotonic(),
            fallback_requested=False,
        )
        current_state["source"] = (
            "native_h264_csi" if status.get("backend") == "csi" else "native_h264"
        )
        _write_frame_status("decoding" if frame_state["enabled"] else "disabled")
        _set_status_state(current_state, "ready", current_state["source"])
        logging.info(
            "Persistent H.264 capture pipeline started at %s %s FPS with %s decoder",
            status.get("resolution"), status.get("fps"), "v4l2h264dec",
        )

    def reconcile_camera_source():
        latest = load_camera_status()
        if not latest:
            camera_unavailable["value"] = True
            if active["pipeline"] is not None:
                retain_rtsp_clients(rtsp_clients, "camera capture restart")
                logging.info("Camera capture marker disappeared; holding RTSP server for camera restart")
                stop_capture_pipeline()
            return True
        if latest.get("fallback_attempted") is True:
            camera_unavailable["value"] = True
            _set_status_state(current_state, "error", current_state["source"])
            return True
        if latest.get("native_h264") is not True:
            close_rtsp_clients(rtsp_clients, "camera source changed away from native H.264")
            if active["pipeline"] is not None:
                stop_capture_pipeline()
            logging.error("Camera source changed away from native H.264; restarting RTSP mode")
            loop.quit()
            return False

        signature = camera_status_signature(latest)
        if signature != active["signature"]:
            if active["pipeline"] is not None or camera_unavailable["value"] or active["signature"] is not None:
                retain_rtsp_clients(
                    rtsp_clients, f"camera mode change to {latest.get('resolution')}"
                )
            if active["pipeline"] is not None:
                logging.info(
                    "Camera mode changed to %s at %s FPS; rebuilding capture while keeping RTSP mounted",
                    latest.get("resolution"), latest.get("fps"),
                )
                stop_capture_pipeline()
            camera_unavailable["value"] = True
            try:
                start_capture_pipeline(latest)
                camera_unavailable["value"] = False
            except Exception as error:
                logging.exception("Unable to start the updated native H.264 camera pipeline")
                active["signature"] = signature
                request_camera_fallback(latest, error)
                _set_status_state(current_state, "error", current_state["source"])
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
        element = media.get_element()
        appsrc = element.get_by_name("rtsp_source") if element is not None else None
        if appsrc is None:
            logging.error("Native RTSP media pipeline is missing its appsrc bridge")
            return
        rtsp_media.update(appsrc=appsrc, prepared=False)

        def media_prepared(_media):
            if rtsp_media["appsrc"] is appsrc:
                rtsp_media["prepared"] = True
                # A prepared RTSP media pipeline does not prove that the camera
                # is delivering buffers. count_frame() marks publishing on data.

        def media_unprepared(_media):
            if rtsp_media["appsrc"] is appsrc:
                rtsp_media.update(appsrc=None, prepared=False)

        media.connect("prepared", media_prepared)
        media.connect("unprepared", media_unprepared)

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
            close_rtsp_clients(rtsp_clients, "capture pipeline stopped producing valid media")
            request_camera_fallback(load_camera_status(), "capture pipeline reported ERROR/EOS")
            camera_unavailable["value"] = True
            stop_capture_pipeline()
        return True

    def heartbeat():
        now = time.monotonic()
        last_frame_at = current_state.get("last_frame_at")
        if last_frame_at is not None and now - last_frame_at > 3.0:
            current_state["fps"] = None
            if current_state["value"] == "publishing":
                _set_status_state(current_state, "ready", current_state["source"])
        if (
            active["pipeline"] is not None
            and not active["fallback_requested"]
            and active["started_at"] is not None
            and now - (last_frame_at or active["started_at"]) > 8.0
        ):
            active["fallback_requested"] = request_camera_fallback(
                load_camera_status(), "no H.264 video buffers received within eight seconds"
            )
            if active["fallback_requested"]:
                _set_status_state(current_state, "error", current_state["source"])
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
        try:
            start_capture_pipeline(camera_status)
        except Exception as error:
            logging.exception("Initial native H.264 camera pipeline failed")
            active["signature"] = camera_status_signature(camera_status)
            request_camera_fallback(camera_status, error)
            _set_status_state(current_state, "error", current_state["source"])
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
    check_gstreamer_runtime()
    GLib, Gst, GstRtspServer = _load_gstreamer()
    if args.check:
        if not camera_status:
            raise GStreamerError("No active camera capture marker is available.")
        native_h264 = camera_status.get("native_h264") is True
        source = (
            ("native_h264_csi" if camera_status.get("backend") == "csi" else "native_h264")
            if native_h264 else "mjpeg_copy"
        )
        launch = build_gstreamer_launch(camera_status)
        output = {
            "source": source,
            "pipeline": launch,
            "rtsp_url": "rtsp://<petcam-host>:8554/petcam",
        }
        if native_h264:
            from petcam.infrastructure.streaming import sampler

            sampler.require_h264_hardware_decoder(Gst)
            output["pipeline"] = build_native_capture_launch(camera_status)
            output["rtsp_pipeline"] = build_native_rtsp_launch()
        print(json.dumps(output))
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = GstRtspServer.RTSPServer()
    configure_rtsp_server(server)
    mounts = server.get_mount_points()
    # Bind the RTSP socket before waiting for camera discovery. The mount is
    # installed as soon as a viable capture marker appears; until then clients
    # can reach the service but the camera path is not advertised as ready.
    if server.attach(None) == 0:
        raise GStreamerError("GStreamer RTSP server could not attach to the GLib main context.")

    if not camera_status:
        wait_loop = GLib.MainLoop()
        waiting = {"status": None, "stopping": False}

        def discover_camera():
            status = load_camera_status()
            if not status:
                _write_status("starting", "camera_discovery")
                return True
            waiting["status"] = status
            wait_loop.quit()
            return False

        def stop_waiting(_signum, _frame):
            waiting["stopping"] = True
            wait_loop.quit()

        signal.signal(signal.SIGTERM, stop_waiting)
        signal.signal(signal.SIGINT, stop_waiting)
        GLib.timeout_add_seconds(1, discover_camera)
        logging.info("RTSP listener is bound; waiting for camera discovery")
        wait_loop.run()
        if waiting["stopping"]:
            _write_status("stopped", "camera_discovery")
            return
        camera_status = waiting["status"] or load_camera_status()
        if not camera_status:
            raise GStreamerError("Camera discovery ended without an active capture marker.")

    native_h264 = camera_status.get("native_h264") is True
    source = (
        ("native_h264_csi" if camera_status.get("backend") == "csi" else "native_h264")
        if native_h264 else "mjpeg_copy"
    )
    launch = build_gstreamer_launch(camera_status)

    if native_h264:
        _run_native_h264_server(GLib, Gst, GstRtspServer, server, mounts, camera_status, source)
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
        if current_state["value"] != "publishing":
            set_state("publishing")
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
        media.connect("prepared", lambda _media: set_state("ready"))
        media.connect("unprepared", media_unprepared)

    factory.connect("media-configure", media_configured)
    mounts.add_factory("/petcam", factory)
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
