#!/usr/bin/env python3
"""Small, dependency-free PetCam camera management HTTP interface."""
import copy
import json
import os
import ssl
import socket
import subprocess
import threading
import time
import hmac
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import management_routes
from ..infrastructure.persistence.configuration import apply_config, ensure_config_lock, parse_config
from ..infrastructure.camera.cli import (
    camera_identity, discover_csi_cameras, discover_devices, mode_supports_fps,
)
from ..application.camera_inventory import build_camera_inventory
from ..infrastructure.network.diagnostics import collect_diagnostics, create_support_bundle
from ..infrastructure.network.wifi_metrics import collect_network_performance
from ..features.timelapse.service import load_config as load_timelapse_config, save_config as save_timelapse_config, state_snapshot as timelapse_snapshot
from ..features.motion.service import load_config as load_motion_config, save_config as save_motion_config, state_snapshot as motion_snapshot, FRAMES as MOTION_FRAMES
from ..features.light_sensor.service import load_config as load_light_config, save_config as save_light_config, read_status as light_sensor_status
from ..security.sessions import SESSION_TTL, get_session, initialize_password, invalidate_session, is_configured, new_session, verify_password
from ..bootstrap import setup_portal
from ..infrastructure.camera import controls as camera_controls
from ..application import feature_configuration as feature_services
from ..application import camera_configuration, capture_status, service_transactions, diagnostics as application_diagnostics
from ..infrastructure.system import metrics as system_metrics, processes as process_control
from ..infrastructure.streaming import status as g_streamer_status

CONFIG = Path("/etc/petcam/petcam.conf")
TLS_CERT = Path("/etc/petcam/web-manager.crt")
TLS_KEY = Path("/etc/petcam/web-manager.key")
HEALTH_FILE = Path("/var/lib/petcam/health.json")
G_STREAMER_STATUS_FILE = Path("/run/petcam/g-streamer-status.json")
SUPERVISOR_STATUS_FILE = Path("/run/petcam/supervisor-status.json")
_login_attempts = {}
_login_lock = threading.Lock()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_ASSETS = {
    "dashboard.js": "application/javascript; charset=utf-8",
    "dashboard-core.js": "application/javascript; charset=utf-8",
    "dashboard-api.js": "application/javascript; charset=utf-8",
    "dashboard-camera.js": "application/javascript; charset=utf-8",
    "dashboard-features.js": "application/javascript; charset=utf-8",
}


def serve_static_asset(handler, name):
    content_type = STATIC_ASSETS.get(name)
    if content_type is None:
        handler.send_error(404)
        return
    try:
        body = (STATIC_DIR / name).read_bytes()
    except OSError:
        handler.send_error(404)
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def device_mdns_hostname():
    """Prefer the hostname configured in Imager, then its resolved FQDN."""
    hostname = socket.gethostname().strip().rstrip(".")
    if "." not in hostname:
        resolved_hostname = socket.getfqdn().strip().rstrip(".")
        if "." in resolved_hostname:
            hostname = resolved_hostname
    if not hostname:
        raise RuntimeError("Unable to determine the configured device hostname")
    return hostname if "." in hostname else f"{hostname}.local"


PAGE = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")


def camera_inventory():
    return build_camera_inventory(
        discover_devices,
        discover_csi_cameras,
        camera_identity,
    )


_CAMERA_INVENTORY_CACHE_SECONDS = 3.0
_camera_inventory_cache = None
_camera_inventory_cache_at = 0.0
_camera_inventory_cache_lock = threading.Lock()


def cached_camera_inventory():
    """Reuse a very recent discovery result for related manager API requests."""
    global _camera_inventory_cache, _camera_inventory_cache_at
    with _camera_inventory_cache_lock:
        now = time.monotonic()
        if (
            _camera_inventory_cache is not None
            and now - _camera_inventory_cache_at < _CAMERA_INVENTORY_CACHE_SECONDS
        ):
            return copy.deepcopy(_camera_inventory_cache)
        inventory = camera_inventory()
        _camera_inventory_cache = copy.deepcopy(inventory)
        _camera_inventory_cache_at = time.monotonic()
        return copy.deepcopy(inventory)


def active_camera_config():
    try:
        config = parse_config(CONFIG, check_hardware=False)
    except Exception:
        return None
    return {
        key: config[key]
        for key in ("SOURCE", "DEVICE", "USB_PHYSICAL_PATH", "CSI_DEVICE_PATH", "CAMERA", "FORMAT", "RESOLUTION", "FPS")
    }


def live_capture_status():
    return capture_status.live_status(
        CONFIG, parse_config, urlopen=urllib.request.urlopen, kill=os.kill, path_factory=Path,
    )

def parse_v4l2_controls(output):
    """Compatibility adapter for the camera-control service."""
    return camera_controls.parse_controls(output)

def active_usb_camera():
    """Resolve the configured primary USB camera through current discovery, never a client path."""
    config = active_camera_config()
    if not config or config.get("SOURCE") != "usb":
        return None
    physical_path = config.get("USB_PHYSICAL_PATH", "")
    device = config.get("DEVICE", "")
    for camera in cached_camera_inventory():
        if camera.get("kind") != "usb":
            continue
        if physical_path and camera.get("physical_path") == physical_path:
            return camera
        if not physical_path and device and camera.get("device") == device:
            return camera
    return None


def read_camera_controls(camera=None):
    """Read controls through the dedicated camera-control service."""
    camera = camera or active_usb_camera()
    return camera_controls.read_controls(camera, subprocess.run)


def set_camera_control(data):
    """Apply a validated control through the dedicated camera-control service."""
    return camera_controls.set_control(
        data,
        active_usb_camera(),
        read_camera_controls,
        subprocess.run,
    )

def _run_service_commands(commands):
    return service_transactions.run_service_commands(commands, process_control.run_command)


def apply_service_config_transaction(save, previous, candidate, commands, rollback_commands):
    """Compatibility adapter for the service-configuration transaction."""
    return service_transactions.apply_config_transaction(
        save, previous, candidate, commands, rollback_commands, process_control.run_command,
    )


def update_timelapse(data):
    return feature_services.update_timelapse(
        data,
        parse_config=parse_config,
        config_path=CONFIG,
        load_config=load_timelapse_config,
        save_config=save_timelapse_config,
        supervisor_command=process_control.supervisor_command,
        apply_transaction=apply_service_config_transaction,
    )


def update_motion(data):
    return feature_services.update_motion(
        data,
        parse_config=parse_config,
        config_path=CONFIG,
        load_config=load_motion_config,
        save_config=save_motion_config,
        supervisor_command=process_control.supervisor_command,
        apply_transaction=apply_service_config_transaction,
    )


def update_light_sensor(data):
    return feature_services.update_light_sensor(data, save_config=save_light_config)


def save_selection(data):
    """Delegate camera selection validation and application to its service."""
    return camera_configuration.save_selection(
        data,
        discover_cameras=camera_inventory,
        mode_supports_fps=mode_supports_fps,
        apply_config=apply_config,
    )


def system_resource_metrics():
    return system_metrics.resource_metrics()


def installed_version():
    return system_metrics.installed_version(__file__)


def web_ui_enabled():
    return setup_portal.web_ui_enabled()


def set_web_ui_enabled(enabled):
    setup_portal.set_web_ui_enabled(enabled)

def _origin_ok(handler):
    origin = urlparse(handler.headers.get("Origin", ""))
    return origin.scheme == "https" and origin.netloc.lower() == handler.headers.get("Host", "").lower()


def _cookie(handler):
    for part in handler.headers.get("Cookie", "").split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key == "petcam_session":
            return value
    return ""


def _body(handler, maximum=8192):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        raise ValueError("Invalid request size")
    if not 1 <= length <= maximum:
        raise ValueError("Invalid request size")
    return json.loads(handler.rfile.read(length))


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _session(self):
        return get_session(_cookie(self))

    def _require_auth(self):
        if self._session():
            return True
        self.send_json(401, {"error": "Authentication required"})
        return False

    def _require_csrf(self):
        session = self._session()
        supplied = self.headers.get("X-PetCam-CSRF", "")
        if not session or not _origin_ok(self) or not hmac.compare_digest(session["csrf"], supplied):
            self.send_json(403, {"error": "Request origin or CSRF token is not valid"})
            return False
        return True

    def do_GET(self):
        management_routes.handle_get(self, sys.modules[__name__])

    def do_POST(self):
        management_routes.handle_post(self, sys.modules[__name__])

    def log_message(self, fmt, *args):
        pass


def diagnostics_snapshot():
    return application_diagnostics.live_snapshot(
        capture_status=live_capture_status(),
        network_status=collect_network_performance(),
        system_metrics=system_resource_metrics(),
        rtsp_status=g_streamer_status_snapshot(),
        captured_at=time.time(),
    )


def g_streamer_status_snapshot():
    return g_streamer_status.snapshot(G_STREAMER_STATUS_FILE, supervisor_file=SUPERVISOR_STATUS_FILE, clock=time.time)

def health_monitor_loop():
    from ..infrastructure.system.health import check_health
    last_summary = None
    while True:
        started = time.monotonic()
        try:
            report = check_health()
            summary = (report["state"], report.get("reason", ""), report.get("recovery_count", 0))
            if summary != last_summary:
                print(f"PetCam health: {summary[0]} - {summary[1]}", flush=True)
                last_summary = summary
        except Exception as error:
            print(f"PetCam health monitor failed: {error}", file=sys.stderr, flush=True)
        time.sleep(max(1, 30 - (time.monotonic() - started)))


def main():
    if not TLS_CERT.is_file() or not TLS_KEY.is_file():
        raise SystemExit("PetCam HTTPS certificate is missing.")
    ensure_config_lock()
    threading.Thread(target=health_monitor_loop, name="petcam-health-monitor", daemon=True).start()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(TLS_CERT, TLS_KEY)
    manager = ThreadingHTTPServer(("127.0.0.1", 8444), Handler)
    manager.socket = context.wrap_socket(manager.socket, server_side=True)
    threads = [
        threading.Thread(target=manager.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        manager.server_close()


if __name__ == "__main__":
    main()
