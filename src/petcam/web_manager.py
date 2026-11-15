#!/usr/bin/env python3
import http.client
"""Small, dependency-free PetCam camera management HTTP interface."""
import copy
import json
import os
import re
import ssl
import socket
import subprocess
import threading
import time
import hmac
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import apply_config, ensure_config_lock, parse_config
from camera import PIXEL_BUDGETS, USTREAMER_FORMATS, camera_identity, discover_csi_cameras, discover_devices, mode_supports_fps, model_tier, read_model
from camera_service import build_camera_inventory, build_capture_modes as _build_capture_modes
from network_diagnostics import collect_diagnostics, create_support_bundle
from wifi_metrics import collect_network_performance
from timelapse import load_config as load_timelapse_config, save_config as save_timelapse_config, state_snapshot as timelapse_snapshot
from motion_detection import load_config as load_motion_config, save_config as save_motion_config, state_snapshot as motion_snapshot, FRAMES as MOTION_FRAMES
from light_sensor import load_config as load_light_config, save_config as save_light_config, read_status as light_sensor_status
from rtmp_output import load_config as load_rtmp_config, save_config as save_rtmp_config, public_config as public_rtmp_config, check_gstreamer_runtime
from web_auth import SESSION_TTL, get_session, initialize_password, invalidate_session, is_configured, new_session, verify_password
import camera_controls
import service_transactions
import stream_metrics
import system_metrics
import camera_configuration

CONFIG = Path("/etc/petcam/petcam.conf")
TLS_CERT = Path("/etc/petcam/web-manager.crt")
TLS_KEY = Path("/etc/petcam/web-manager.key")
HEALTH_FILE = Path("/var/lib/petcam/health.json")
RTMP_STATUS_FILE = Path("/run/petcam/rtmp-status.json")
_login_attempts = {}
_login_lock = threading.Lock()
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_ASSETS = {
    "dashboard.js": "application/javascript; charset=utf-8",
    "browser-source.js": "application/javascript; charset=utf-8",
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
    """Return the configured device hostname as an mDNS name for UI links."""
    hostname = socket.gethostname().strip().rstrip(".")
    if not hostname:
        raise RuntimeError("Unable to determine the configured device hostname")
    return hostname if "." in hostname else f"{hostname}.local"


PAGE = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")


def build_capture_modes(camera, performance_budget):
    """Return the server-approved capture-mode catalog for one camera."""
    return _build_capture_modes(camera, performance_budget)


def camera_inventory():
    return build_camera_inventory(
        discover_devices,
        discover_csi_cameras,
        model_tier,
        read_model,
        PIXEL_BUDGETS,
        USTREAMER_FORMATS,
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
    """Read capture metrics directly from the active stream backend.

    The general-purpose petcam-status command also performs hardware discovery,
    diagnostics, and a throughput sample. Running that command for a UI refresh
    can exceed the manager's timeout on slower Pis, hiding otherwise available
    capture-rate data. These two local endpoints expose only the live metrics.
    """
    try:
        config = parse_config(CONFIG)
        port = int(config["PORT"])
    except Exception:
        config = {}
        port = 8081

    # Native H.264 has no MJPEG HTTP backend. Report the actual runtime mode.
    try:
        marker = json.loads(Path("/var/lib/petcam/camera-status.json").read_text(encoding="utf-8"))
        pid = int(marker.get("pid", 0))
        if marker.get("native_h264") is True and pid > 1:
            os.kill(pid, 0)
            result = {"active_capture_format": "H264", "active_resolution": marker.get("resolution") or config.get("RESOLUTION"),
                      "configured_fps": marker.get("fps") or config.get("FPS"),
                      "capture_mode": "native_h264_csi" if marker.get("backend") == "csi" else "native_h264",
                      "hardware_encoder": marker.get("encoder")}
            try:
                status = json.loads(Path("/run/petcam/rtmp-status.json").read_text(encoding="utf-8"))
                if status.get("source") in ("native_h264", "native_h264_csi"):
                    result["latest_captured_fps"] = status.get("fps")
                    result["rtsp_output_ready"] = status.get("active") is True and status.get("state") == "publishing"
            except (OSError, ValueError, TypeError):
                pass
            return result
    except (OSError, ValueError, TypeError, ProcessLookupError):
        pass

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        state = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(state, dict):
            source = state.get("source") or {}
            resolution = source.get("resolution") or {}
            result = {
                "latest_captured_fps": source.get("captured_fps"),
                "active_resolution": (
                    f"{resolution['width']}x{resolution['height']}"
                    if resolution.get("width") and resolution.get("height") else None
                ),
                "active_capture_format": (
                    "MJPEG" if (state.get("encoder") or {}).get("type") == "HW" else None
                ),
            }
            if config.get("FPS") is not None:
                result["configured_fps"] = config["FPS"]
            return result
    except (OSError, urllib.error.URLError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError, AttributeError):
        pass

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("backend") == "csi":
            result = {
                "latest_captured_fps": payload.get("captured_fps_average"),
                "active_resolution": config.get("RESOLUTION"),
                "active_capture_format": "MJPEG",
            }
            if config.get("FPS") is not None:
                result["configured_fps"] = config["FPS"]
            for key in ("frames_received", "last_frame_age_seconds", "capture_process_running"):
                if key in payload:
                    result[key] = payload[key]
            if payload.get("error"):
                result["capture_error"] = payload["error"]
            return result
    except (OSError, urllib.error.URLError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass
    return {}



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
    return service_transactions.run_service_commands(commands, subprocess.run)


def apply_service_config_transaction(save, previous, candidate, commands, rollback_commands):
    """Compatibility adapter for the service-configuration transaction."""
    return service_transactions.apply_config_transaction(
        save, previous, candidate, commands, rollback_commands, subprocess.run,
    )

def rtmp_service_command(action):
    commands = {
        "enable": ["/usr/bin/systemctl", "enable", "--now", "petcam-rtmp.service"],
        "disable": ["/usr/bin/systemctl", "disable", "--now", "petcam-rtmp.service"],
        "restart": ["/usr/bin/systemctl", "restart", "petcam-rtmp.service"],
    }
    try:
        return commands[action]
    except KeyError as error:
        raise ValueError(f"Unsupported OBS RTSP output action: {action}") from error


def set_rtmp_service(action):
    result = subprocess.run(
        rtmp_service_command(action),
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Unable to {action} OBS RTSP output service.")


def save_selection(data):
    """Delegate camera selection validation and application to its service."""
    return camera_configuration.save_selection(
        data,
        discover_cameras=camera_inventory,
        mode_supports_fps=mode_supports_fps,
        pixel_budgets=PIXEL_BUDGETS,
        model_tier=model_tier,
        read_model=read_model,
        config_path=CONFIG,
        parse_config=parse_config,
        load_rtmp_config=load_rtmp_config,
        save_rtmp_config=save_rtmp_config,
        load_timelapse_config=load_timelapse_config,
        load_motion_config=load_motion_config,
        check_gstreamer_runtime=check_gstreamer_runtime,
        run=subprocess.run,
        set_rtmp_service=set_rtmp_service,
        apply_config=apply_config,
    )


def register_stream_client(source):
    return stream_metrics.register_client(source)


def unregister_stream_client(client_id):
    return stream_metrics.unregister_client(client_id)


def record_stream_chunk(client_id, chunk, parser_state):
    return stream_metrics.record_chunk(client_id, chunk, parser_state)


def stream_metrics_snapshot():
    return stream_metrics.snapshot()


def system_resource_metrics():
    return system_metrics.resource_metrics()


def installed_version():
    return system_metrics.installed_version(__file__)

def proxy_stream(handler, port):
    """Proxy MJPEG, returning a useful HTTP error if capture is not ready yet."""
    query = parse_qs(urlparse(handler.path).query)
    source = ("obs_media_source" if query.get("client") == ["obs-media-source"] else "browser_source")
    if parse_config(CONFIG).get("FORMAT") == "H264":
        handler.send_error(503, "HTTP MJPEG streaming is disabled while H.264 capture is selected. Use the OBS RTSP Media Source.")
        return
    client_id = register_stream_client(source)
    parser_state = {
        "previous_byte": None,
        "in_jpeg": False,
        "last_frame_monotonic": None,
    }
    headers_sent = False
    retry_delay = 0.1
    try:
        while True:
            streamed_data = False
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/stream", timeout=5) as upstream:
                    if not headers_sent:
                        handler.send_response(upstream.status)
                        handler.send_header(
                            "Content-Type",
                            upstream.headers.get("Content-Type", "multipart/x-mixed-replace"),
                        )
                        handler.send_header("Cache-Control", "no-store")
                        handler.end_headers()
                        headers_sent = True
                    read_chunk = getattr(upstream, "read1", upstream.read)
                    while chunk := read_chunk(65536):
                        # Forward original bytes unchanged; metrics only scan JPEG markers.
                        handler.wfile.write(chunk)
                        record_stream_chunk(client_id, chunk, parser_state)
                        streamed_data = True
                if streamed_data:
                    retry_delay = 0.1
                else:
                    retry_delay = min(2.0, retry_delay * 1.7)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except (OSError, urllib.error.URLError, TimeoutError, http.client.HTTPException):
                if not headers_sent:
                    handler.send_error(503, "Camera MJPEG stream is unavailable")
                    return
                retry_delay = min(2.0, retry_delay * 1.7)
            time.sleep(retry_delay)
    finally:
        unregister_stream_client(client_id)


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
        path = urlparse(self.path).path
        if path == "/static/dashboard.js":
            serve_static_asset(self, "dashboard.js")
            return
        if path == "/api/setup/status":
            self.send_json(200, {"configured": is_configured()})
            return
        if path == "/":
            body = PAGE.replace("__PETCAM_HOST__", device_mdns_hostname()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if not self._require_auth():
            return
        if path == "/api/session":
            self.send_json(200, {"csrf_token": self._session()["csrf"]})
            return
        if path == "/api/timelapse":
            try:
                config = load_timelapse_config()
                self.send_json(200, {"config": config, "status": timelapse_snapshot(config)})
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/motion":
            try:
                config = load_motion_config()
                self.send_json(200, {"config": config, "status": motion_snapshot(config)})
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/light-sensor":
            try:
                self.send_json(200, {"config": load_light_config(), "status": light_sensor_status()})
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path.startswith("/api/motion/events/"):
            filename = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z(?:-[0-9]{3})?\.jpg", filename):
                self.send_error(404)
                return
            image_path = MOTION_FRAMES / filename
            try:
                payload = image_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "private, no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/api/diagnostics":
            try:
                self.send_json(200, collect_diagnostics())
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/support-bundle":
            try:
                body = create_support_bundle(performance={
                    "capture_status": live_capture_status(),
                    "stream_metrics": stream_metrics_snapshot(),
                    "network_status": collect_network_performance(),
                    "captured_at": time.time(),
                })
                self.send_response(200)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Disposition", "attachment; filename=\"petcam-support.tar.gz\"")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/live-status":
            self.send_json(200, {
                "capture_status": live_capture_status(),
                "capture_status_updated_at": time.time(),
                "stream_metrics": stream_metrics_snapshot(),
                "network_status": collect_network_performance(),
                "system_metrics": system_resource_metrics(),
                "rtmp_output_status": rtmp_status_snapshot(),
            })
            return
        if path == "/api/system":
            self.send_json(200, {"installed_version": installed_version()})
            return
        if path == "/api/rtmp":
            try:
                self.send_json(200, {"config": public_rtmp_config(load_rtmp_config()), "status": rtmp_status_snapshot()})
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/health":
            try:
                health = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
                if not isinstance(health, dict):
                    raise ValueError("Invalid health status document")
                self.send_json(200, health)
            except (OSError, ValueError):
                self.send_json(200, {"state": "not_checked", "reason": "The periodic health monitor has not reported yet.", "recovery_count": 0})
            return
        if path == "/api/camera-controls":
            try:
                self.send_json(200, read_camera_controls())
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/cameras":
            try:
                self.send_json(200, {"cameras": camera_inventory(), "active_config": active_camera_config(), "capture_status": live_capture_status()})
            except Exception as error:
                self.send_json(500, {"error": str(error)})
            return
        if path == "/stream":
            try:
                proxy_stream(self, int(parse_config(CONFIG)["PORT"]))
            except Exception as error:
                self.send_json(503, {"error": str(error)})
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/setup":
            if is_configured():
                self.send_json(409, {"error": "PetCam administrator setup has already been completed."})
                return
            if not _origin_ok(self):
                self.send_json(403, {"error": "Request origin is not allowed"})
                return
            try:
                data = _body(self, 4096)
                if data.get("password") != data.get("password_confirmation"):
                    self.send_json(400, {"error": "The passwords do not match."})
                    return
                initialize_password(data.get("password", ""))
                token, csrf = new_session()
                self.send_json(201, {"ok": True, "csrf_token": csrf}, {
                    "Set-Cookie": f"petcam_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}"
                })
            except ValueError as error:
                status = 409 if is_configured() else 400
                self.send_json(status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/api/login":
            if not _origin_ok(self):
                self.send_json(403, {"error": "Request origin is not allowed"})
                return
            try:
                data = _body(self, 4096)
                peer = self.client_address[0]
                now = time.time()
                with _login_lock:
                    attempts = [stamp for stamp in _login_attempts.get(peer, []) if stamp > now - 300]
                    if len(attempts) >= 5:
                        self.send_json(429, {"error": "Too many sign-in attempts. Wait five minutes and retry."})
                        return
                    attempts.append(now)
                    _login_attempts[peer] = attempts
                if not verify_password(data.get("password", "")):
                    self.send_json(401, {"error": "Invalid password"})
                    return
                with _login_lock:
                    _login_attempts.pop(peer, None)
                token, csrf = new_session()
                self.send_json(200, {"ok": True, "csrf_token": csrf}, {
                    "Set-Cookie": f"petcam_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}"
                })
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if not self._require_auth():
            return
        if not self._require_csrf():
            return
        try:
            data = _body(self)
            if path == "/api/camera-controls":
                self.send_json(200, set_camera_control(data))
                return
            if path == "/api/timelapse":
                if data.get("enabled") and parse_config(CONFIG).get("FORMAT") == "H264":
                    raise RuntimeError("Switch the camera back to MJPEG before enabling timelapse; timelapse requires MJPEG frames.")
                current = load_timelapse_config()
                commands = [
                    (["/usr/bin/systemctl", "restart", "petcam-stream.service"],
                     45, "Unable to restart camera after changing timelapse settings."),
                ]
                if load_rtmp_config()["enabled"]:
                    commands.append((
                        ["/usr/bin/systemctl", "restart", "petcam-rtmp.service"],
                        30, "Unable to restart OBS output after changing MJPEG consumer settings.",
                    ))
                updated = apply_service_config_transaction(
                    save_timelapse_config, current, {**current, **data},
                    commands, commands,
                )
                self.send_json(200, {"ok": True, "config": updated})
                return
            if path == "/api/motion":
                if data.get("enabled") and parse_config(CONFIG).get("FORMAT") == "H264":
                    raise RuntimeError("Switch the camera back to MJPEG before enabling motion detection; motion detection requires MJPEG frames.")
                current = load_motion_config()
                commands = [
                    (["/usr/bin/systemctl", "restart", "petcam-stream.service"],
                     45, "Unable to restart camera after changing motion settings."),
                ]
                if load_rtmp_config()["enabled"]:
                    commands.append((
                        ["/usr/bin/systemctl", "restart", "petcam-rtmp.service"],
                        30, "Unable to restart OBS output after changing MJPEG consumer settings.",
                    ))
                updated = apply_service_config_transaction(
                    save_motion_config, current, {**current, **data},
                    commands, commands,
                )
                self.send_json(200, {"ok": True, "config": updated})
                return
            if path == "/api/light-sensor":
                updated = save_light_config(data)
                self.send_json(200, {"ok": True, "config": updated})
                return
            if path == "/api/rtmp":
                current_camera = parse_config(CONFIG)
                if current_camera.get("FORMAT") == "H264" and data.get("enabled") is not True:
                    raise RuntimeError("OBS RTSP output is forced on while H.264 capture is selected.")
                if data.get("enabled"):
                    try:
                        check_gstreamer_runtime()
                    except ValueError as error:
                        raise RuntimeError(str(error)) from error
                current = load_rtmp_config()
                was_active = subprocess.run(
                    ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
                    check=False, timeout=5,
                ).returncode == 0
                candidate = {**current, **data}
                action = ("restart" if was_active else "enable") if candidate["enabled"] else "disable"
                previous_action = (
                    ("restart" if was_active else "enable") if current["enabled"] else "disable"
                )
                commands = [
                    (["/usr/bin/systemctl", "restart", "petcam-stream.service"],
                     45, "Unable to restart the camera with the saved OBS output settings."),
                    (rtmp_service_command(action),
                     30, "Unable to update OBS output service state."),
                ]
                rollback_commands = [
                    (["/usr/bin/systemctl", "restart", "petcam-stream.service"],
                     45, "Unable to restart the camera with the restored OBS output settings."),
                    (rtmp_service_command(previous_action),
                     30, "Unable to restore OBS output service state."),
                ]
                updated = apply_service_config_transaction(
                    save_rtmp_config, current, candidate, commands, rollback_commands,
                )
                self.send_json(200, {"ok": True, "config": public_rtmp_config(updated), "status": rtmp_status_snapshot()})
                return
            if path == "/api/logout":
                invalidate_session(_cookie(self))
                self.send_json(200, {"ok": True}, {
                    "Set-Cookie": "petcam_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
                })
                return
            if path == "/api/select":
                save_selection(data)
                self.send_json(200, {"ok": True})
                return
            self.send_error(404)
        except Exception as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, fmt, *args):
        pass


class StreamHandler(BaseHTTPRequestHandler):
    """Unauthenticated HTTP endpoint reserved for OBS stream clients."""

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/browser-source.js":
            serve_static_asset(self, "browser-source.js")
            return
        try:
            if parse_config(CONFIG).get("FORMAT") == "H264":
                self.send_error(503, "HTTP Browser Source is disabled while H.264 capture is selected. Use the OBS RTSP Media Source.")
                return
        except Exception:
            pass
        if path == "/":
            body = b'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PetCam Browser Source</title><style>html,body{margin:0;width:100%;height:100%;background:transparent;overflow:hidden}#status{position:absolute;inset:0;display:grid;place-items:center;color:#ddd;font:16px sans-serif;text-align:center;padding:1rem;box-sizing:border-box}img{position:relative;display:block;width:100%;height:100%;object-fit:contain}img:not([data-ready]){opacity:0}</style><div id="status">Connecting to PetCam camera...</div><img id="stream" src="/stream" alt="PetCam camera stream"><script src="/browser-source.js" defer></script></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/stream":
            self.send_error(404)
            return
        try:
            proxy_stream(self, int(parse_config(CONFIG)["PORT"]))
        except Exception:
            self.send_error(503)

    def log_message(self, fmt, *args):
        pass


def rtmp_status_snapshot():
    config = load_rtmp_config()
    try:
        active_service = subprocess.run(
            ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
            check=False, timeout=1,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        # A delayed systemd response must not turn the entire status API into
        # HTTP 500 or block every dashboard refresh.
        active_service = False
    status = {}
    try:
        status = json.loads(RTMP_STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    updated_at = status.get("updated_at")
    fresh = isinstance(updated_at, (int, float)) and time.time() - updated_at <= 10
    state = status.get("state", "starting") if active_service else "stopped"
    if active_service and updated_at is not None and not fresh:
        state = "stalled"
    return {
        "enabled": config["enabled"],
        "active": active_service and state == "publishing",
        "state": state,
        "fps": status.get("fps") if fresh else None,
        "updated_at": updated_at,
        "source": status.get("source") if fresh else None,
    }


def health_monitor_loop():
    from health_monitor import check_health
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
    manager = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    manager.socket = context.wrap_socket(manager.socket, server_side=True)
    stream = ThreadingHTTPServer(("0.0.0.0", 8080), StreamHandler)
    threads = [
        threading.Thread(target=manager.serve_forever, daemon=True),
        threading.Thread(target=stream.serve_forever, daemon=True),
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
        stream.shutdown()
        manager.server_close()
        stream.server_close()


if __name__ == "__main__":
    main()
