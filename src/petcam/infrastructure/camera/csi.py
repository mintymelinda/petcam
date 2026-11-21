#!/usr/bin/env python3
"""Capture a CSI camera as hardware-encoded H.264 and bridge it to RTSP."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import threading
from pathlib import Path

from .discovery import detect_hardware_h264_encoder

RUN_DIR = Path(os.environ.get("PETCAM_RUN", f"/tmp/petcam-{os.getuid()}"))
CAMERA_STATUS = RUN_DIR / "camera-status.json"


class H264TCPBridge:
    """Forward the hardware-encoded CSI byte stream to the local GStreamer server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8556):
        self.host = host
        self.port = port
        self.listener: socket.socket | None = None
        self.clients: set[socket.socket] = set()
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(2)
        listener.settimeout(0.5)
        self.listener = listener
        self.thread = threading.Thread(target=self._accept, name="petcam-csi-h264", daemon=True)
        self.thread.start()

    def _accept(self) -> None:
        assert self.listener is not None
        while not self.stopping.is_set():
            try:
                client, _ = self.listener.accept()
                client.settimeout(1.0)
                with self.lock:
                    self.clients.add(client)
            except socket.timeout:
                continue
            except OSError:
                return

    def publish(self, data: bytes) -> None:
        stale = []
        with self.lock:
            for client in self.clients:
                try:
                    client.sendall(data)
                except OSError:
                    stale.append(client)
            for client in stale:
                self.clients.discard(client)
                try:
                    client.close()
                except OSError:
                    pass

    def stop(self) -> None:
        self.stopping.set()
        if self.listener is not None:
            self.listener.close()
        with self.lock:
            clients = tuple(self.clients)
            self.clients.clear()
        for client in clients:
            try:
                client.close()
            except OSError:
                pass
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2)


def _write_camera_marker(config: dict, encoder: dict, tcp_port: int) -> None:
    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = {
        "pid": os.getpid(),
        "backend": "csi",
        "camera": config["camera"],
        "sensor": config.get("sensor", ""),
        "device_path": config.get("device_path", ""),
        "resolution": config["resolution"],
        "fps": config["fps"],
        "tcp_port": tcp_port,
        "native_h264": True,
        "encoder": encoder["encoder"],
    }
    temporary = CAMERA_STATUS.with_name(CAMERA_STATUS.name + ".tmp")
    temporary.write_text(json.dumps(marker) + "\n", encoding="utf-8")
    os.replace(temporary, CAMERA_STATUS)


def _remove_camera_marker() -> None:
    try:
        marker = json.loads(CAMERA_STATUS.read_text(encoding="utf-8"))
        if marker.get("pid") == os.getpid():
            CAMERA_STATUS.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def run_h264(camera: int, resolution: str, fps: float, tcp_port: int = 8556) -> int:
    encoder = detect_hardware_h264_encoder()
    if not encoder.get("available"):
        raise RuntimeError(
            "No Raspberry Pi hardware H.264 encoder was detected. "
            "CSI streaming requires a hardware encoder; software encoding is not used."
        )
    if not shutil_which("rpicam-vid"):
        raise RuntimeError("rpicam-vid is required for CSI H.264 capture; install rpicam-apps.")

    bridge = H264TCPBridge(port=tcp_port)
    bridge.start()
    process = None
    stopping = threading.Event()

    def stop(_signum, _frame):
        stopping.set()
        if process is not None and process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _write_camera_marker(
        {"camera": camera, "resolution": resolution, "fps": fps}, encoder, tcp_port
    )
    command = [
        "rpicam-vid", "--camera", str(camera), "--timeout", "0", "--nopreview",
        "--codec", "h264", "--inline", "--width", resolution.split("x", 1)[0],
        "--height", resolution.split("x", 1)[1], "--framerate", str(fps), "--output", "-",
    ]
    try:
        logging.info(
            "Starting CSI camera %s at %s %s FPS with hardware encoder %s",
            camera, resolution, fps, encoder["encoder"],
        )
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, bufsize=0)
        assert process.stdout is not None
        while not stopping.is_set():
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            bridge.publish(chunk)
        code = process.wait()
        if not stopping.is_set() and code != 0:
            raise RuntimeError(f"rpicam-vid exited with status {code}.")
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        bridge.stop()
        _remove_camera_marker()


def shutil_which(command: str) -> str | None:
    """Resolve an executable without introducing a third-party dependency."""
    import shutil

    return shutil.which(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, required=True)
    parser.add_argument("--resolution", required=True)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--tcp-port", type=int, default=8556)
    args = parser.parse_args()
    if args.camera < 0 or args.fps <= 0 or not 1 <= args.tcp_port <= 65535:
        parser.error("camera, FPS, and TCP port must be positive values")
    if "x" not in args.resolution:
        parser.error("resolution must use WIDTHxHEIGHT format")
    try:
        return run_h264(args.camera, args.resolution, args.fps, args.tcp_port)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        logging.error("CSI H.264 capture failed: %s", error)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
