"""Reconcile optional PetCam services from persisted feature settings."""

from __future__ import annotations

import json
import logging
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from ...features.motion.service import load_config as load_motion_config
from ...features.timelapse.service import load_config as load_timelapse_config

WEB_CONFIG = Path("/etc/petcam/web-manager.json")
POLL_SECONDS = 5
SERVICES = {
    "web_ui": "petcam-web.service",
    "motion": "petcam-motion.service",
    "timelapse": "petcam-timelapse.service",
}
_running = True


def _web_enabled(path: Path = WEB_CONFIG) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as error:
        logging.error("Unable to read web manager feature configuration: %s", error)
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        logging.error("Web manager feature configuration must contain a boolean enabled value.")
        return False
    return payload["enabled"]


def desired_services(*, capture_ready: bool, web_enabled: bool, motion: dict, timelapse: dict):
    """Return the optional services that should currently be running."""
    return {
        SERVICES["web_ui"]: web_enabled,
        SERVICES["motion"]: capture_ready and motion.get("enabled") is True,
        SERVICES["timelapse"]: capture_ready and timelapse.get("enabled") is True,
    }


def capture_is_ready(status_path="/run/petcam/rtsp-sampler-status.json") -> bool:
    try:
        status = json.loads(Path(status_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(status, dict) and status.get("state") == "streaming"


def reconcile_services(
    desired: dict[str, bool],
    *,
    run: Callable = subprocess.run,
) -> None:
    """Start enabled services and stop disabled ones without restarting healthy units."""
    for service, enabled in desired.items():
        try:
            active = run(
                ["/usr/bin/systemctl", "is-active", "--quiet", service],
                capture_output=True, text=True, check=False, timeout=10,
            ).returncode == 0
            if enabled and not active:
                action = "start"
            elif not enabled and active:
                action = "stop"
            else:
                continue
            result = run(
                ["/usr/bin/systemctl", action, service],
                capture_output=True, text=True, check=False, timeout=30,
            )
            if result.returncode:
                logging.error("systemctl %s %s failed: %s", action, service, result.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as error:
            logging.error("Unable to reconcile %s: %s", service, error)


def run_loop(
    *,
    web_config: Path = WEB_CONFIG,
    capture_status: Path = Path("/run/petcam/rtsp-sampler-status.json"),
    motion_loader: Callable = load_motion_config,
    timelapse_loader: Callable = load_timelapse_config,
    run: Callable = subprocess.run,
    sleep: Callable = time.sleep,
) -> None:
    """Continuously follow feature settings and camera availability."""
    while _running:
        try:
            desired = desired_services(
                capture_ready=capture_is_ready(capture_status),
                web_enabled=_web_enabled(web_config),
                motion=motion_loader(),
                timelapse=timelapse_loader(),
            )
            reconcile_services(desired, run=run)
        except Exception:
            logging.exception("Optional feature service reconciliation failed")
        sleep(POLL_SECONDS)


def _stop(_signum, _frame):
    global _running
    _running = False


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
