#!/usr/bin/env python3
"""Capture native H.264 NAL units and publish them through Live555."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from ..camera.discovery import detect_hardware_h264_encoder
from ..camera.h264 import AnnexBNalFramer, H264FramingError

RUN_DIR = Path(os.environ.get("PETCAM_RUN", f"/tmp/petcam-{os.getuid()}"))
CAMERA_STATUS = RUN_DIR / "camera-status.json"
STREAM_STATUS = RUN_DIR / "stream-status.json"
RTSP_PORT = 8554
RTSP_PATH = "/petcam"
MAX_NAL_BYTES = 16 * 1024 * 1024


class Live555Error(RuntimeError):
    """Raised when native capture or the Live555 RTSP server cannot start."""


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


def validate_mode(status: dict) -> tuple[int, int, float]:
    try:
        width_text, height_text = str(status.get("resolution", "")).split("x", 1)
        width, height = int(width_text), int(height_text)
        fps = float(status.get("fps"))
    except (ValueError, TypeError) as error:
        raise Live555Error("Configured H.264 capture mode is invalid.") from error
    if not (0 < width <= 65535 and 0 < height <= 65535 and 0 < fps <= 1000):
        raise Live555Error("Configured H.264 capture mode is outside supported limits.")
    return width, height, fps


def build_capture_command(status: dict) -> list[str]:
    if status.get("native_h264") is not True:
        raise Live555Error("PetCam accepts only native H.264 camera sources.")
    width, height, fps = validate_mode(status)
    if status.get("backend") == "usb":
        device = str(status.get("device", ""))
        if not (device.startswith("/dev/video") or device.startswith("/dev/v4l/by-id/")):
            raise Live555Error("Configured USB camera device path is invalid.")
        if not shutil.which("v4l2-ctl"):
            raise Live555Error("v4l2-ctl is missing; install v4l-utils.")
        return [
            "v4l2-ctl", f"--device={device}",
            f"--set-fmt-video=width={width},height={height},pixelformat=H264",
            f"--set-parm={fps:g}", "--stream-mmap=3", "--stream-to=-",
        ]
    if status.get("backend") == "csi":
        try:
            camera = int(status.get("camera"))
        except (TypeError, ValueError) as error:
            raise Live555Error("Configured CSI camera index is invalid.") from error
        if camera < 0:
            raise Live555Error("Configured CSI camera index is invalid.")
        if not shutil.which("rpicam-vid"):
            raise Live555Error("rpicam-vid is missing; install rpicam-apps-lite.")
        if detect_hardware_h264_encoder().get("available") is not True:
            raise Live555Error("No Raspberry Pi hardware H.264 encoder was detected.")
        return [
            "rpicam-vid", "--camera", str(camera), "--timeout", "0",
            "--nopreview", "--codec", "h264", "--inline",
            "--width", str(width), "--height", str(height),
            "--framerate", f"{fps:g}", "--output", "-",
        ]
    raise Live555Error("Configured camera backend must be usb or csi.")


class Live555Server:
    """ctypes binding to the small ARMHF Live555 server library."""

    def __init__(self, library_path: Path | None = None):
        if library_path is None:
            override = os.environ.get("PETCAM_LIVE555_LIBRARY")
            library_path = Path(override) if override else (
                Path(__file__).resolve().parents[4] / "lib" / "libpetcam_live555.so"
            )
        try:
            self.library = ctypes.CDLL(str(library_path))
        except OSError as error:
            raise Live555Error(f"Unable to load Live555 native library: {error}") from error
        self.library.petcam_start.argtypes = [ctypes.c_ushort, ctypes.c_char_p]
        self.library.petcam_start.restype = ctypes.c_int
        self.library.petcam_push_nal.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t, ctypes.c_int
        ]
        self.library.petcam_push_nal.restype = ctypes.c_int
        self.library.petcam_last_error.restype = ctypes.c_char_p
        self.library.petcam_stop.argtypes = []
        self.library.petcam_stop.restype = None

    def start(self, port: int = RTSP_PORT, path: str = RTSP_PATH) -> None:
        if self.library.petcam_start(port, path.encode("ascii")) != 0:
            detail = self.library.petcam_last_error()
            message = detail.decode("utf-8", "replace") if detail else "unknown error"
            raise Live555Error(f"Unable to start Live555 RTSP server: {message}")

    def push_nal(self, nal: bytes, keyframe: bool = False) -> None:
        if not nal or len(nal) > MAX_NAL_BYTES:
            raise Live555Error("H.264 NAL unit is empty or exceeds the size limit.")
        buffer = (ctypes.c_ubyte * len(nal)).from_buffer_copy(nal)
        if self.library.petcam_push_nal(buffer, len(nal), int(keyframe)) != 0:
            raise Live555Error("Live555 rejected an H.264 NAL unit.")

    def stop(self) -> None:
        self.library.petcam_stop()


class H264Publisher:
    """Cache parameter sets and prepend them at each independently decodable IDR."""

    def __init__(self, server: Live555Server):
        self.server = server
        self.sps = b""
        self.pps = b""
        self.started = False

    @staticmethod
    def nal_payload(nal: bytes) -> tuple[int, bytes]:
        if nal.startswith(b"\x00\x00\x00\x01"):
            payload = nal[4:]
        elif nal.startswith(b"\x00\x00\x01"):
            payload = nal[3:]
        else:
            raise Live555Error("Camera emitted an H.264 NAL without an Annex-B start code.")
        if not payload:
            raise Live555Error("Camera emitted an empty H.264 NAL unit.")
        return payload[0] & 0x1F, payload

    def publish(self, nal: bytes) -> None:
        nal_type, payload = self.nal_payload(nal)
        if nal_type == 7:
            self.sps = payload
        elif nal_type == 8:
            self.pps = payload
        elif nal_type == 5:
            if not self.sps or not self.pps:
                raise Live555Error("Camera emitted an IDR before SPS and PPS were available.")
            self.server.push_nal(self.sps, keyframe=True)
            self.server.push_nal(self.pps)
            self.server.push_nal(payload)
            self.started = True
        elif self.started:
            self.server.push_nal(payload)


def write_status(state: str, source: dict, message: str = "") -> None:
    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "state": state, "source": source.get("backend"),
        "resolution": source.get("resolution"), "capture_fps": source.get("fps"),
        "streamed_fps": None, "updated_at": time.time(), "message": message,
    }
    temporary = STREAM_STATUS.with_name(STREAM_STATUS.name + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, STREAM_STATUS)


def run_server(camera_status: dict) -> int:
    command = build_capture_command(camera_status)
    server = Live555Server()
    capture = None
    reader = None
    stop_reader = threading.Event()
    first_idr = threading.Event()
    reader_error = {"message": ""}
    publisher = H264Publisher(server)

    def read_capture() -> None:
        assert capture is not None and capture.stdout is not None
        framer = AnnexBNalFramer()
        try:
            while not stop_reader.is_set():
                chunk = capture.stdout.read(65536)
                if not chunk:
                    break
                for nal in framer.feed(chunk):
                    publisher.publish(nal)
                    if publisher.started:
                        first_idr.set()
            for nal in framer.flush():
                publisher.publish(nal)
                if publisher.started:
                    first_idr.set()
            if not stop_reader.is_set():
                reader_error["message"] = "Camera capture stopped producing H.264 data."
        except (OSError, H264FramingError, Live555Error) as error:
            reader_error["message"] = str(error)
            logging.exception("H.264 capture/publishing failed")

    started_at = time.monotonic()
    try:
        server.start()
        capture = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
        )
        reader = threading.Thread(target=read_capture, name="petcam-h264-capture", daemon=True)
        reader.start()
        logging.info("H.264 RTSP endpoint: rtsp://%s:%s%s", socket.getfqdn(), RTSP_PORT, RTSP_PATH)
        while True:
            if capture.poll() is not None:
                raise Live555Error(f"Camera capture exited with status {capture.returncode}.")
            if reader_error["message"]:
                raise Live555Error(reader_error["message"])
            if first_idr.is_set():
                write_status("ready", camera_status)
            elif time.monotonic() - started_at > 12:
                raise Live555Error("No H.264 IDR frame with SPS/PPS arrived within 12 seconds.")
            else:
                write_status("starting", camera_status)
            time.sleep(1)
    finally:
        stop_reader.set()
        if capture is not None:
            if capture.poll() is None:
                capture.terminate()
                try:
                    capture.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    capture.kill()
                    capture.wait(timeout=2)
            if capture.stdout is not None:
                capture.stdout.close()
        if reader is not None and reader.is_alive():
            reader.join(timeout=2)
        server.stop()
        write_status("stopped", camera_status)


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
            write_status("error", camera_status, str(error))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
