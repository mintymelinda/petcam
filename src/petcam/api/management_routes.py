"""HTTP route dispatch for the authenticated management interface."""

import json
import re
import time
from urllib.parse import urlparse


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path.startswith("/static/"):
        services.serve_static_asset(handler, path.removeprefix("/static/"))
        return
    if path == "/api/setup/status":
        handler.send_json(200, {"configured": services.is_configured()})
        return
    if path == "/":
        body = services.PAGE.replace("__PETCAM_HOST__", services.device_mdns_hostname()).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        return
    if not handler._require_auth():
        return
    if path == "/api/session":
        handler.send_json(200, {"csrf_token": handler._session()["csrf"]})
        return
    if path == "/api/timelapse":
        try:
            config = services.load_timelapse_config()
            handler.send_json(200, {"config": config, "status": services.timelapse_snapshot(config)})
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path == "/api/motion":
        try:
            config = services.load_motion_config()
            handler.send_json(200, {"config": config, "status": services.motion_snapshot(config)})
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path == "/api/light-sensor":
        try:
            handler.send_json(200, {"config": services.load_light_config(), "status": services.light_sensor_status()})
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path.startswith("/api/motion/events/"):
        filename = path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z(?:-[0-9]{3})?\.jpg", filename):
            handler.send_error(404)
            return
        image_path = services.MOTION_FRAMES / filename
        try:
            payload = image_path.read_bytes()
        except OSError:
            handler.send_error(404)
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "private, no-store")
        handler.end_headers()
        handler.wfile.write(payload)
        return
    if path == "/api/diagnostics":
        try:
            handler.send_json(200, services.collect_diagnostics())
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path == "/api/support-bundle":
        try:
            body = services.create_support_bundle(performance={
                "capture_status": services.live_capture_status(),
                "stream_metrics": services.stream_metrics_snapshot(),
                "network_status": services.collect_network_performance(),
                "captured_at": time.time(),
            })
            handler.send_response(200)
            handler.send_header("Content-Type", "application/gzip")
            handler.send_header("Content-Disposition", "attachment; filename=\"petcam-support.tar.gz\"")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path == "/api/live-status":
        handler.send_json(200, services.diagnostics_snapshot())
        return
    if path == "/api/system":
        handler.send_json(200, {"services.installed_version": services.installed_version()})
        return
    if path == "/api/health":
        try:
            health = json.loads(services.HEALTH_FILE.read_text(encoding="utf-8"))
            if not isinstance(health, dict):
                raise ValueError("Invalid health status document")
            handler.send_json(200, health)
        except (OSError, ValueError):
            handler.send_json(200, {"state": "not_checked", "reason": "The periodic health monitor has not reported yet.", "recovery_count": 0})
        return
    if path == "/api/camera-controls":
        try:
            handler.send_json(200, services.read_camera_controls())
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    if path == "/api/cameras":
        try:
            handler.send_json(200, {"cameras": services.camera_inventory(), "active_config": services.active_camera_config(), "capture_status": services.live_capture_status()})
        except Exception as error:
            handler.send_json(500, {"error": str(error)})
        return
    if path == "/stream":
        try:
            services.proxy_stream(handler, int(services.parse_config(services.CONFIG)["PORT"]))
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    handler.send_error(404)



def handle_post(handler, services):
    path = urlparse(handler.path).path
    if path == "/api/setup":
        if services.is_configured():
            handler.send_json(409, {"error": "PetCam administrator setup has already been completed."})
            return
        if not services._origin_ok(handler):
            handler.send_json(403, {"error": "Request origin is not allowed"})
            return
        try:
            data = services._body(handler, 4096)
            if data.get("password") != data.get("password_confirmation"):
                handler.send_json(400, {"error": "The passwords do not match."})
                return
            services.initialize_password(data.get("password", ""))
            token, csrf = services.new_session()
            handler.send_json(201, {"ok": True, "csrf_token": csrf}, {
                "Set-Cookie": f"petcam_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={services.SESSION_TTL}"
            })
        except ValueError as error:
            status = 409 if services.is_configured() else 400
            handler.send_json(status, {"error": str(error)})
        except Exception as error:
            handler.send_json(400, {"error": str(error)})
        return
    if path == "/api/login":
        if not services._origin_ok(handler):
            handler.send_json(403, {"error": "Request origin is not allowed"})
            return
        try:
            data = services._body(handler, 4096)
            peer = handler.client_address[0]
            now = time.time()
            with services._login_lock:
                attempts = [stamp for stamp in services._login_attempts.get(peer, []) if stamp > now - 300]
                if len(attempts) >= 5:
                    handler.send_json(429, {"error": "Too many sign-in attempts. Wait five minutes and retry."})
                    return
                attempts.append(now)
                services._login_attempts[peer] = attempts
            if not services.verify_password(data.get("password", "")):
                handler.send_json(401, {"error": "Invalid password"})
                return
            with services._login_lock:
                services._login_attempts.pop(peer, None)
            token, csrf = services.new_session()
            handler.send_json(200, {"ok": True, "csrf_token": csrf}, {
                "Set-Cookie": f"petcam_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={services.SESSION_TTL}"
            })
        except Exception as error:
            handler.send_json(400, {"error": str(error)})
        return
    if not handler._require_auth():
        return
    if not handler._require_csrf():
        return
    try:
        data = services._body(handler)
        if path == "/api/camera-controls":
            handler.send_json(200, services.set_camera_control(data))
            return
        if path == "/api/timelapse":
            updated = services.update_timelapse(data)
            handler.send_json(200, {"ok": True, "config": updated})
            return
        if path == "/api/motion":
            updated = services.update_motion(data)
            handler.send_json(200, {"ok": True, "config": updated})
            return
        if path == "/api/light-sensor":
            updated = services.update_light_sensor(data)
            handler.send_json(200, {"ok": True, "config": updated})
            return
        if path == "/api/logout":
            services.invalidate_session(services._cookie(handler))
            handler.send_json(200, {"ok": True}, {
                "Set-Cookie": "petcam_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
            })
            return
        if path == "/api/select":
            services.save_selection(data)
            handler.send_json(200, {"ok": True})
            return
        handler.send_error(404)
    except Exception as error:
        handler.send_json(400, {"error": str(error)})

