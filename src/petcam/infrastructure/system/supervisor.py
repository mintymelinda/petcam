"""Single-process-tree supervisor for all PetCam runtime workers.

Run with python -m petcam.infrastructure.system.supervisor from a source checkout. The supervisor
owns child lifetimes, restart backoff, optional feature activation and shutdown;
it deliberately has no dependency on a host service manager.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import socketserver
import threading
import subprocess
import urllib.request
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ETC = Path(os.environ.get("PETCAM_ETC", "/etc/petcam"))
STATE = Path(os.environ.get("PETCAM_STATE", "/var/lib/petcam"))
RUN = Path(os.environ.get("PETCAM_RUN", "/run/petcam"))
POLL_SECONDS = 3
RESTART_BASE_SECONDS = 2
RESTART_MAX_SECONDS = 60


@dataclass
class Worker:
    name: str
    command: tuple[str, ...]
    enabled: Callable[[], bool] = lambda: True
    process: subprocess.Popen | None = None
    failures: int = 0
    next_start: float = 0.0
    started_at: float = 0.0

    def should_run(self) -> bool:
        try:
            return bool(self.enabled())
        except Exception:
            logging.exception("Unable to determine whether %s should run", self.name)
            return False


def read_enabled(path: Path, *, default: bool = False) -> bool:
    """Read JSON feature flags and the existing KEY=value integration configs."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return default
    legacy = False
    try:
        payload = json.loads(raw)
    except ValueError:
        legacy = True
        payload = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            payload[key.strip()] = value.strip()
    if not isinstance(payload, dict):
        return default
    for key in ("enabled", "ENABLED", "MQTT_ENABLED"):
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if legacy and isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
    return default


def capture_source_ready() -> bool:
    try:
        marker = json.loads((STATE / "camera-status.json").read_text(encoding="utf-8"))
        pid = int(marker.get("pid", 0))
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def gstreamer_ready() -> bool:
    try:
        status = json.loads((RUN / "g-streamer-status.json").read_text(encoding="utf-8"))
        age = time.time() - float(status.get("updated_at", 0))
    except (OSError, ValueError, TypeError):
        return False
    return status.get("state") in ("ready", "publishing") and 0 <= age <= 15


def capture_ready() -> bool:
    try:
        payload = json.loads((RUN / "rtsp-sampler-status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("state") == "streaming"


def workers() -> list[Worker]:
    py = sys.executable
    return [
        Worker("setup-portal", (py, "-m", "petcam.bootstrap.setup_portal")),
        Worker("camera-capture", (py, "-m", "petcam.infrastructure.camera.capture")),
        Worker("gstreamer-rtsp", (py, "-m", "petcam.infrastructure.streaming.gstreamer"), capture_source_ready),
        Worker("rtsp-sampler", (py, "-m", "petcam.infrastructure.streaming.sampler"), gstreamer_ready),
        Worker("web-ui", (py, "-m", "petcam.api.application"),
               lambda: read_enabled(ETC / "web-manager.json")),
        Worker("home-assistant", (py, "-m", "petcam.features.home_assistant.worker"),
               lambda: read_enabled(ETC / "home-assistant.conf") and capture_ready()),
        Worker("light-sensor", (py, "-m", "petcam.features.light_sensor.worker"),
               lambda: read_enabled(ETC / "light-sensor.conf")),
        Worker("motion", (py, "-m", "petcam.features.motion.worker"),
               lambda: read_enabled(STATE / "motion/config.json") and capture_ready()),
        Worker("timelapse", (py, "-m", "petcam.features.timelapse.worker"),
               lambda: read_enabled(STATE / "timelapse/config.json") and capture_ready()),
    ]


class ControlServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class Supervisor:
    def __init__(self, entries: list[Worker] | None = None, *, clock=time.monotonic):
        self.entries = entries if entries is not None else workers()
        self.clock = clock
        self.stopping = False
        self.started_at = clock()
        self.control_server = None
        self.control_thread = None

    def start(self, worker: Worker) -> None:
        if self.clock() < worker.next_start:
            return
        logging.info("Starting %s: %s", worker.name, " ".join(worker.command))
        try:
            worker.process = subprocess.Popen(
                worker.command, stdin=subprocess.DEVNULL,
                start_new_session=True, close_fds=True,
            )
            worker.started_at = self.clock()
        except OSError:
            worker.failures += 1
            worker.next_start = self.clock() + min(
                RESTART_BASE_SECONDS * 2 ** min(worker.failures - 1, 5),
                RESTART_MAX_SECONDS,
            )
            logging.exception("Could not start %s", worker.name)

    def stop(self, worker: Worker, *, timeout: float = 8) -> None:
        process = worker.process
        if process is None:
            return
        if process.poll() is None:
            logging.info("Stopping %s", worker.name)
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        worker.process = None

    def tick(self) -> None:
        now = self.clock()
        for worker in self.entries:
            desired = worker.should_run()
            process = worker.process
            if not desired:
                if process is not None:
                    self.stop(worker)
                continue
            if process is not None and process.poll() is None:
                continue
            if process is not None:
                runtime = now - worker.started_at
                worker.process = None
                worker.failures = 0 if runtime >= 60 else worker.failures + 1
                delay = min(RESTART_BASE_SECONDS * 2 ** min(worker.failures, 5), RESTART_MAX_SECONDS)
                worker.next_start = now + delay
                logging.warning("%s exited (%s); retrying in %.0fs", worker.name, process.returncode, delay)
            self.start(worker)

    def snapshot(self) -> dict:
        return {
            "pid": os.getpid(), "started_at": self.started_at, "updated_at": self.clock(),
            "workers": {
                worker.name: {
                    "pid": worker.process.pid if worker.process and worker.process.poll() is None else None,
                    "running": bool(worker.process and worker.process.poll() is None),
                    "failures": worker.failures, "next_start": worker.next_start, "started_at": worker.started_at,
                } for worker in self.entries
            },
        }

    def publish(self) -> None:
        RUN.mkdir(parents=True, exist_ok=True)
        destination = RUN / "supervisor-status.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.snapshot(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def handle_control(self, request: dict) -> dict:
        action = request.get("action")
        worker_name = request.get("worker")
        allowed = {worker.name: worker for worker in self.entries}
        if action == "status":
            return {"ok": True, "snapshot": self.snapshot()}
        if action in ("restart", "stop"):
            worker = allowed.get(worker_name)
            if worker is None:
                return {"ok": False, "error": "Unknown worker"}
            self.stop(worker)
            worker.next_start = 0
            if action == "restart":
                worker.failures = 0
                self.start(worker)
            self.publish()
            return {"ok": True, "worker": worker_name}
        if action == "stop_all":
            for worker in reversed(self.entries):
                self.stop(worker)
            self.publish()
            return {"ok": True}
        if action == "reconcile":
            self.tick()
            self.publish()
            return {"ok": True}
        return {"ok": False, "error": "Unsupported supervisor action"}

    def start_control_server(self) -> None:
        RUN.mkdir(parents=True, exist_ok=True)
        socket_path = RUN / "supervisor.sock"
        socket_path.unlink(missing_ok=True)
        supervisor = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                raw = self.rfile.readline(4097)
                if len(raw) > 4096 or not raw.endswith(b"\n"):
                    result = {"ok": False, "error": "Invalid request size"}
                else:
                    try:
                        payload = json.loads(raw)
                        if not isinstance(payload, dict):
                            raise ValueError("Request must be an object")
                        result = supervisor.handle_control(payload)
                    except (ValueError, TypeError) as error:
                        result = {"ok": False, "error": str(error)}
                self.wfile.write(json.dumps(result).encode("utf-8") + b"\n")

        self.control_server = ControlServer(str(socket_path), Handler)
        os.chmod(socket_path, 0o660)
        self.control_thread = threading.Thread(
            target=self.control_server.serve_forever, name="supervisor-control", daemon=True
        )
        self.control_thread.start()

    def stop_control_server(self) -> None:
        if self.control_server is not None:
            self.control_server.shutdown()
            self.control_server.server_close()
            (RUN / "supervisor.sock").unlink(missing_ok=True)
            if self.control_thread is not None:
                self.control_thread.join(timeout=2)

    def run(self) -> int:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self.start_control_server()
        try:
            while not self.stopping:
                self.tick()
                self.publish()
                time.sleep(POLL_SECONDS)
        finally:
            self.stop_control_server()
            for worker in reversed(self.entries):
                self.stop(worker)
            self.publish()
        return 0

    def request_stop(self, _signum, _frame) -> None:
        self.stopping = True


def main() -> int:
    return Supervisor().run()


if __name__ == "__main__":
    raise SystemExit(main())
