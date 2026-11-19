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
from pathlib import Path

STATUS_PATH = Path(os.environ.get("PETCAM_G_STREAMER_STATUS", "/run/petcam/g-streamer-status.json"))
RTSP_URL = "rtsp://127.0.0.1:8554/petcam"
CAMERA_STATUS_PATH = Path("/var/lib/petcam/camera-status.json")


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
    required = ("v4l2src", "tcpclientsrc", "h264parse", "rtph264pay", "souphttpsrc", "multipartdemux", "jpegparse", "rtpjpegpay")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate GStreamer RTSP dependencies and camera selection")
    args = parser.parse_args()
    camera_status = load_camera_status()
    native_h264 = camera_status.get("native_h264") is True
    source = ("native_h264_csi" if camera_status.get("backend") == "csi" else "native_h264") if native_h264 else "mjpeg_copy"
    launch = build_gstreamer_launch(camera_status)
    check_gstreamer_runtime()
    GLib, Gst, GstRtspServer = _load_gstreamer()
    if args.check:
        print(json.dumps({
            "source": source,
            "pipeline": launch,
            "rtsp_url": "rtsp://<petcam-host>:8554/petcam",
        }))
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = GstRtspServer.RTSPServer()
    configure_rtsp_server(server)
    mounts = server.get_mount_points()
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
