"""Local IPC client for the PetCam-owned Python supervisor."""

from __future__ import annotations

import json
import os
import socket
from types import SimpleNamespace
from pathlib import Path
from typing import Any

SOCKET_PATH = Path(os.environ.get("PETCAM_SUPERVISOR_SOCKET", "/run/petcam/supervisor.sock"))
MAX_RESPONSE_BYTES = 65536


class SupervisorUnavailable(RuntimeError):
    """Raised when the PetCam supervisor cannot accept a control request."""


def request(action: str, worker: str | None = None, *, timeout: float = 5) -> dict[str, Any]:
    if action not in {"status", "restart", "stop", "stop_all", "reconcile"}:
        raise ValueError("Unsupported supervisor action")
    payload = {"action": action}
    if worker is not None:
        if not worker or len(worker) > 64 or not worker.replace("-", "").isalnum():
            raise ValueError("Invalid worker name")
        payload["worker"] = worker
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(SOCKET_PATH))
            connection.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            response = bytearray()
            while len(response) <= MAX_RESPONSE_BYTES:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
                if b"\n" in response:
                    break
    except OSError as error:
        raise SupervisorUnavailable(f"PetCam supervisor is unavailable: {error}") from error
    if not response or len(response) > MAX_RESPONSE_BYTES:
        raise SupervisorUnavailable("PetCam supervisor returned an empty or oversized response")
    try:
        result = json.loads(bytes(response).split(b"\n", 1)[0])
    except (ValueError, TypeError) as error:
        raise SupervisorUnavailable("PetCam supervisor returned invalid JSON") from error
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise SupervisorUnavailable(str(result.get("error", "Supervisor request failed")))
    return result


def restart_worker(worker: str) -> dict[str, Any]:
    return request("restart", worker)


def worker_snapshot(worker: str) -> dict[str, Any]:
    snapshot = request("status").get("snapshot", {})
    workers = snapshot.get("workers", {}) if isinstance(snapshot, dict) else {}
    return workers.get(worker, {"running": False, "state": "unknown", "started_at": None})


def run_command(command: list[str], **_options: Any) -> dict[str, Any]:
    """Compatibility adapter for existing transactional callers; never executes a host service manager."""
    if not isinstance(command, (list, tuple)) or len(command) < 2 or command[0] != "@supervisor":
        raise ValueError("Only supervisor control commands are supported")
    result = request(command[1], command[2] if len(command) > 2 else None)
    return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(result))


def supervisor_command(action: str, worker: str | None = None) -> list[str]:
    if action not in {"status", "restart", "stop", "stop_all", "reconcile"}:
        raise ValueError("Unsupported supervisor action")
    return ["@supervisor", action, worker] if worker is not None else ["@supervisor", action]
