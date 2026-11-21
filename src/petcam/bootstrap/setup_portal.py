"""Always-on lightweight setup portal and reverse proxy for the optional manager."""

from __future__ import annotations

import http.client
import html
import json
import logging
import os
import secrets
import ssl
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..security import sessions as web_auth

TLS_CERT = Path("/etc/petcam/web-manager.crt")
TLS_KEY = Path("/etc/petcam/web-manager.key")
WEB_CONFIG = Path("/etc/petcam/web-manager.json")
MANAGER_HOST = "127.0.0.1"
MANAGER_PORT = 8444
HEALTH_STATUS = Path("/var/lib/petcam/health.json")
SUPERVISOR_STATUS = Path("/run/petcam/supervisor-status.json")
SESSION_TTL = 8 * 60 * 60
MAX_BODY = 16 * 1024 * 1024
PROXY_TIMEOUT_SECONDS = 60
PROXY_GET_ATTEMPTS = 3
PROXY_RETRY_DELAY_SECONDS = 0.15
MANAGER_STATIC_ASSETS = (
    "/static/dashboard-api.js",
    "/static/dashboard-core.js",
    "/static/dashboard-camera.js",
    "/static/dashboard-features.js",
    "/static/dashboard.js",
)
_sessions: dict[str, dict] = {}
_sessions_lock = threading.RLock()
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__PETCAM_HOST__ Setup</title>
<style>
:root{color-scheme:dark;font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#11151b;color:#edf2f7;accent-color:#82b5ff}
*{box-sizing:border-box}
body{max-width:46rem;margin:clamp(1.5rem,7vh,4.5rem) auto;padding:0 1.1rem}
main{background:#1b222c;border:1px solid #303b49;border-radius:18px;padding:clamp(1.15rem,4vw,2rem);box-shadow:0 24px 70px #0005}
header{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1.6rem}
h1{font-size:clamp(1.45rem,4vw,1.9rem);letter-spacing:-.035em;line-height:1.2;margin:0}
h2{font-size:1.12rem;margin:0 0 1rem;letter-spacing:-.015em}
p{margin:.55rem 0}
.muted{color:#aab6c5}
section.panel{padding:1.15rem 1.2rem;border:1px solid #354253;border-radius:12px;background:#202934;margin-top:1rem}
.status-line{font-size:.94rem;color:#c3d0df;margin:.1rem 0 1rem}
.url-row{display:flex;gap:.65rem;align-items:stretch}
input{min-width:0;width:100%;font:inherit;padding:.72rem .8rem;border:1px solid #48576a;border-radius:8px;background:#131a23;color:#edf2f7}
input[readonly]{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9rem}
button,a.button{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;font:600 .94rem system-ui,sans-serif;padding:.72rem 1rem;border:1px solid #53677f;border-radius:8px;background:#2d3c4e;color:#f7fbff;text-decoration:none;cursor:pointer;white-space:nowrap;transition:background .15s,border-color .15s,transform .15s}
button:hover,a.button:hover{background:#3a4d63;border-color:#7894b5}
button:active,a.button:active{transform:translateY(1px)}
button:focus-visible,a.button:focus-visible,input:focus-visible{outline:3px solid #82b5ff;outline-offset:2px}
button.primary{background:#3569a8;border-color:#5488c7}
button.primary:hover{background:#407bbd}
button.quiet{padding:.55rem .8rem;font-size:.88rem;background:transparent;border-color:#48576a}
button:disabled{opacity:.55;cursor:wait}
#sign-out[hidden],#setup-form[hidden],#login-form[hidden],#manager-control[hidden],#open-manager[hidden]{display:none}
#message{min-height:1.5rem;color:#b9d8ff;margin:.9rem .1rem 0;font-size:.92rem}
#message:empty{display:none}
#readiness{font-size:.9rem;color:#aab6c5;margin:.8rem 0 0}
#open-manager{margin-top:.85rem}
#setup-form,#login-form{margin:1rem 0}
#setup-form label,#login-form label{display:block;margin:.8rem 0 .35rem;color:#cbd5e1}
#setup-form input,#login-form input{margin-bottom:.2rem}
#setup-form button,#login-form button{margin-top:.7rem}
@media(max-width:520px){body{margin:1rem auto;padding:0 .7rem}main{border-radius:13px;padding:1rem}.url-row{align-items:stretch}.url-row button{padding:.65rem .75rem}header{align-items:flex-start}}
</style></head><body><main>
<header><h1>__PETCAM_HOST__ Device Setup</h1><button id="sign-out" class="quiet" type="button" hidden>Sign Out</button></header>
<form id="setup-form" hidden><h2>Administrator setup</h2>
<p class="muted">Create a password to protect this device's management interface.</p>
<label for="new-password">Administrator password (12–1024 characters)</label><input id="new-password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required>
<label for="confirm-password">Confirm password</label><input id="confirm-password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required>
<button class="primary" type="submit">Create password</button></form>
<form id="login-form" hidden><h2>Administrator sign in</h2>
<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
<button class="primary" type="submit">Sign In</button></form>
<section id="manager-control" hidden>
<section class="panel" aria-labelledby="stream-heading"><h2 id="stream-heading">RTSP camera stream</h2>
<p id="rtsp-service-status" class="status-line" role="status" aria-live="polite">Checking RTSP service…</p>
<div class="url-row"><input id="rtsp-url" type="text" readonly aria-label="RTSP stream URL"><button id="copy-rtsp-url" type="button">Copy</button></div>
<p id="camera-mode-status" class="muted" role="status">Waiting for active camera…</p>
</section>
<section class="panel" aria-labelledby="full-ui-heading"><h2 id="full-ui-heading">Full Web UI</h2>
<p id="web-state" class="status-line" role="status">Checking status…</p>
<button id="toggle-web-ui" class="primary" type="button" disabled>Checking…</button>
<p id="readiness" role="status" aria-live="polite">Checking service health…</p>
<a id="open-manager" class="button" href="/">Open Full UI</a>
</section></section>
<p id="message" role="status" aria-live="polite"></p></main>
<script>
const $=id=>document.getElementById(id);let csrf="";
async function api(path,body){const headers={"Content-Type":"application/json"};if(csrf)headers["X-PetCam-CSRF"]=csrf;
 const response=await fetch("/setup/api/"+path,{method:body===undefined?"GET":"POST",headers,body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json().catch(()=>({error:"Unexpected server response"}));if(!response.ok)throw Error(data.error||"Request failed");return data;}
function message(value){$("message").textContent=value;}
function rtspStreamUrl(){let host=window.location.hostname;if(host.startsWith("[")&&host.endsWith("]"))host=host.slice(1,-1);if(host.includes(":"))host="["+host+"]";return "rtsp://"+host+":8554/petcam";}
let readinessTimer=null,streamStatusTimer=null,webEnabled=false,webUiReady=false,requestPending=false;
function stopReadinessChecks(){if(readinessTimer!==null)clearInterval(readinessTimer);readinessTimer=null;}
function stopStreamStatusChecks(){if(streamStatusTimer!==null)clearInterval(streamStatusTimer);streamStatusTimer=null;}
function renderWebUi(){const button=$("toggle-web-ui");button.textContent=webEnabled?"Disable Full UI":"Enable Full UI";button.disabled=requestPending;
 $("web-state").textContent=webEnabled?"Full Web UI is enabled.":"Full Web UI is disabled.";
 $("open-manager").hidden=!(webEnabled&&webUiReady);
 if(!webEnabled){$("readiness").textContent="Enable the Full UI to start its services.";return;}
 $("readiness").textContent=webUiReady?"All core services are healthy. The Full UI is ready.":"Starting services and checking health…";}
async function refreshManagerReadiness(){if(!webEnabled)return;try{const result=await api("manager-status");webUiReady=result.ready===true;}catch(_){webUiReady=false;}renderWebUi();}
function startReadinessChecks(){stopReadinessChecks();refreshManagerReadiness();readinessTimer=setInterval(refreshManagerReadiness,2000);}
async function refreshStreamStatus(){try{const status=await api("stream-status");const active=status.active_camera||{};
 if(active.resolution&&active.format&&active.fps!==null&&active.fps!==undefined){const source=(active.backend||"camera").toUpperCase();$("camera-mode-status").textContent=active.format+" - "+active.resolution+" - "+active.fps+" FPS ("+source+")";}
 else{$("camera-mode-status").textContent=status.capture_state==="running"?"Active camera mode details unavailable":"Camera is not currently active";}
 const rtsp=status.rtsp||{};let label=rtsp.state||"starting";
 if(rtsp.state==="publishing")label="RTSP server publishing video";else if(rtsp.state==="ready")label="RTSP server ready; waiting for video/client";else if(rtsp.state==="stalled")label="RTSP service status is stale";else if(rtsp.state==="stopped")label="RTSP service stopped";else if(rtsp.state==="starting")label="RTSP server starting";
 $("rtsp-service-status").textContent=label+(rtsp.error?" · "+rtsp.error:"");
 }catch(error){$("rtsp-service-status").textContent="Unable to read RTSP status: "+error.message;}}
function startStreamStatusChecks(){stopStreamStatusChecks();refreshStreamStatus();streamStatusTimer=setInterval(refreshStreamStatus,5000);}
async function refresh(){try{const status=await api("status");$("setup-form").hidden=status.configured;$("login-form").hidden=!status.configured;
 if(!status.configured){$("manager-control").hidden=true;$("sign-out").hidden=true;return;}
 try{const session=await api("session");csrf=session.csrf_token;$("manager-control").hidden=false;$("login-form").hidden=true;$("sign-out").hidden=false;
 $("rtsp-url").value=rtspStreamUrl();webEnabled=status.enabled===true;webUiReady=false;renderWebUi();startStreamStatusChecks();
 if(webEnabled)startReadinessChecks();else stopReadinessChecks();
 }catch(_){$("manager-control").hidden=true;$("sign-out").hidden=true;$("login-form").hidden=false;}
 }catch(error){message(error.message);}}
$("setup-form").addEventListener("submit",async event=>{event.preventDefault();try{if($("new-password").value!==$("confirm-password").value)throw Error("Passwords do not match.");
 const result=await api("setup",{password:$("new-password").value,password_confirmation:$("confirm-password").value});csrf=result.csrf_token;message("Administrator password created.");await refresh();}catch(error){message(error.message);}});
$("login-form").addEventListener("submit",async event=>{event.preventDefault();try{const result=await api("login",{password:$("password").value});csrf=result.csrf_token;$("password").value="";message("Signed in.");await refresh();}catch(error){message(error.message);}});
$("toggle-web-ui").addEventListener("click",async()=>{if(requestPending)return;requestPending=true;$("toggle-web-ui").disabled=true;const nextEnabled=!webEnabled;
 try{const result=await api("web-ui",{enabled:nextEnabled});webEnabled=result.enabled===true;webUiReady=false;message(webEnabled?"Full UI enabled. Waiting for all services to become healthy.":"Full UI disabled.");if(webEnabled)startReadinessChecks();else stopReadinessChecks();renderWebUi();}
 catch(error){message(error.message);renderWebUi();}
 finally{requestPending=false;renderWebUi();}});
$("copy-rtsp-url").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("rtsp-url").value);message("RTSP URL copied.");}catch(_){$("rtsp-url").focus();$("rtsp-url").select();message("Select and copy the RTSP URL.");}});
$("sign-out").addEventListener("click",async()=>{try{await api("logout",{});}catch(_){}csrf="";stopReadinessChecks();stopStreamStatusChecks();webUiReady=false;$("open-manager").hidden=true;$("manager-control").hidden=true;$("sign-out").hidden=true;await refresh();});
refresh();
</script></body></html>"""


def web_ui_enabled() -> bool:
    try:
        payload = json.loads(WEB_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("enabled") is True


def set_web_ui_enabled(enabled: bool) -> None:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    WEB_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = WEB_CONFIG.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"enabled": enabled}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(WEB_CONFIG)
    WEB_CONFIG.chmod(0o640)


def _cookie(handler) -> str:
    for part in handler.headers.get("Cookie", "").split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == "petcam_setup_session":
            return value
    return ""


def _new_session():
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    manager_token, _manager_csrf = web_auth.new_session()
    with _sessions_lock:
        now = time.time()
        for key, value in list(_sessions.items()):
            if value["expires_at"] <= now:
                web_auth.invalidate_session(value.get("manager_token", ""))
                del _sessions[key]
        _sessions[token] = {
            "csrf": csrf,
            "manager_token": manager_token,
            "expires_at": now + SESSION_TTL,
        }
    return token, csrf, manager_token


def _get_session(token):
    if not token:
        return None
    with _sessions_lock:
        session = _sessions.get(token)
        if session and session["expires_at"] > time.time():
            return session
        _sessions.pop(token, None)
    return None


def _origin_allowed(handler) -> bool:
    origin = urlparse(handler.headers.get("Origin", ""))
    return origin.scheme == "https" and origin.netloc.lower() == handler.headers.get("Host", "").lower()


def _read_body(handler, maximum=4096):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as error:
        raise ValueError("Invalid request size") from error
    if not 1 <= length <= maximum:
        raise ValueError("Invalid request size")
    try:
        payload = json.loads(handler.rfile.read(length))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid JSON request") from error
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def _json(handler, status, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for name, value in (headers or {}).items():
        values = value if isinstance(value, (list, tuple)) else (value,)
        for header_value in values:
            handler.send_header(name, header_value)
    handler.end_headers()
    handler.wfile.write(body)


def stream_status_snapshot() -> dict:
    """Return camera configuration and RTSP status without probing hardware."""
    config = {}
    try:
        for line in Path("/etc/petcam/petcam.conf").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    except OSError:
        pass

    marker = {}
    try:
        marker = json.loads(Path("/var/lib/petcam/camera-status.json").read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            marker = {}
    except (OSError, ValueError):
        pass

    rtsp = {}
    try:
        rtsp = json.loads(Path("/run/petcam/g-streamer-status.json").read_text(encoding="utf-8"))
        if not isinstance(rtsp, dict):
            rtsp = {}
    except (OSError, ValueError):
        pass

    supervisor = {}
    try:
        supervisor = json.loads(Path("/run/petcam/supervisor-status.json").read_text(encoding="utf-8"))
        if not isinstance(supervisor, dict):
            supervisor = {}
    except (OSError, ValueError):
        pass

    workers = supervisor.get("workers", {})
    worker = workers.get("gstreamer-rtsp", {}) if isinstance(workers, dict) else {}
    marker_pid = marker.get("pid")
    if marker:
        try:
            if not isinstance(marker_pid, int) or marker_pid <= 1:
                marker = {}
            else:
                os.kill(marker_pid, 0)
        except OSError:
            marker = {}
    now = time.time()
    updated_at = rtsp.get("updated_at")
    fresh = isinstance(updated_at, (int, float)) and 0 <= now - updated_at <= 10
    service_running = worker.get("running") is True
    state = rtsp.get("state", "starting") if service_running else "stopped"
    if service_running and not fresh:
        state = "stalled"

    return {
        "configured": {
            "format": config.get("FORMAT", "auto"),
            "resolution": config.get("RESOLUTION", "auto"),
            "fps": config.get("FPS", "auto"),
        },
        "active_camera": {
            "backend": marker.get("backend"),
            "format": marker.get("format"),
            "resolution": marker.get("resolution"),
            "fps": marker.get("fps"),
        } if marker else None,
        "capture_state": "running" if marker else "discovering",
        "rtsp": {
            "state": state,
            "fps": rtsp.get("fps") if fresh else None,
            "source": rtsp.get("source") if fresh else None,
            "error": rtsp.get("last_error") if fresh else None,
        },
        "updated_at": now,
    }


def _manager_get(path: str, *, timeout: float = 2) -> tuple[int, str, bytes]:
    """Fetch one unauthenticated manager resource for a bounded readiness probe."""
    connection = http.client.HTTPSConnection(
        MANAGER_HOST, MANAGER_PORT,
        context=ssl._create_unverified_context(), timeout=timeout,
    )
    try:
        connection.request("GET", path, headers={"Connection": "close"})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(2 * 1024 * 1024)
    finally:
        connection.close()


def core_services_healthy() -> bool:
    """Require a healthy system report and every mandatory manager dependency."""
    try:
        health = json.loads(HEALTH_STATUS.read_text(encoding="utf-8"))
        supervisor = json.loads(SUPERVISOR_STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(health, dict) or health.get("state") != "healthy":
        return False
    workers = supervisor.get("workers", {}) if isinstance(supervisor, dict) else {}
    if not isinstance(workers, dict):
        return False
    return all(
        isinstance(workers.get(name), dict) and workers[name].get("running") is True
        for name in ("camera-capture", "gstreamer-rtsp", "web-ui")
    )


def manager_ready() -> bool:
    """Require healthy core services plus a complete, servable dashboard."""
    if not web_ui_enabled() or not core_services_healthy():
        return False
    try:
        status, content_type, document = _manager_get("/")
        if status != 200 or "text/html" not in content_type.lower() or not document:
            return False
        if any(asset.encode("ascii") not in document for asset in MANAGER_STATIC_ASSETS):
            return False
        for asset in MANAGER_STATIC_ASSETS:
            asset_status, asset_type, asset_body = _manager_get(asset)
            if (
                asset_status != 200
                or "javascript" not in asset_type.lower()
                or not asset_body
            ):
                return False
        return True
    except (OSError, http.client.HTTPException, ValueError):
        logging.debug("Full Web UI readiness probe failed", exc_info=True)
        return False


def _proxy(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length < 0 or length > MAX_BODY:
        _json(handler, 413, {"error": "Request body is too large"})
        return
    body = handler.rfile.read(length) if length else None
    headers = {
        key: value for key, value in handler.headers.items()
        if key.lower() not in {"host", "connection", "keep-alive", "proxy-connection", "transfer-encoding"}
    }
    headers["Host"] = handler.headers.get("Host", "localhost")
    headers["Connection"] = "close"
    retry_safe = handler.command in {"GET", "HEAD"}
    attempts = PROXY_GET_ATTEMPTS if retry_safe else 1
    last_error = None
    for attempt in range(1, attempts + 1):
        connection = None
        try:
            connection = http.client.HTTPSConnection(
                MANAGER_HOST, MANAGER_PORT,
                context=ssl._create_unverified_context(),
                timeout=PROXY_TIMEOUT_SECONDS,
            )
            connection.request(handler.command, handler.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            handler.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "keep-alive", "transfer-encoding", "server", "date"}:
                    handler.send_header(key, value)
            handler.send_header("Connection", "close")
            handler.end_headers()
            if payload:
                handler.wfile.write(payload)
            return
        except (OSError, http.client.HTTPException) as error:
            last_error = error
            if attempt < attempts:
                logging.info(
                    "Full Web UI %s proxy attempt %d/%d failed (%s); retrying",
                    handler.command, attempt, attempts, type(error).__name__,
                )
                time.sleep(PROXY_RETRY_DELAY_SECONDS * attempt)
        finally:
            if connection is not None:
                connection.close()
    logging.warning(
        "Full Web UI proxy unavailable after %d attempt(s): %s: %s",
        attempts, type(last_error).__name__, last_error,
    )
    _json(handler, 503, {"error": "The full Web UI is enabled but is not currently available."})


class Handler(BaseHTTPRequestHandler):
    def _serve_page(self):
        hostname = socket.gethostname().strip().rstrip(".").split(".", 1)[0] or "PetCam"
        body = PAGE.replace("__PETCAM_HOST__", html.escape(hostname)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/setup", "/setup/"}:
            self._serve_page()
            return
        if path == "/setup/api/status":
            _json(self, 200, {"configured": web_auth.is_configured(), "enabled": web_ui_enabled()})
            return
        if path == "/setup/api/manager-status":
            _json(self, 200, {"enabled": web_ui_enabled(), "ready": manager_ready()})
            return
        if path == "/setup/api/stream-status":
            if not _get_session(_cookie(self)):
                _json(self, 401, {"error": "Authentication required"})
                return
            _json(self, 200, stream_status_snapshot())
            return
        if path == "/setup/api/session":
            session = _get_session(_cookie(self))
            if not session:
                _json(self, 401, {"error": "Authentication required"})
            else:
                _json(self, 200, {"csrf_token": session["csrf"]})
            return
        if web_auth.is_configured() and web_ui_enabled():
            if path == "/" and not manager_ready():
                self.send_response(302)
                self.send_header("Location", "/setup/")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            _proxy(self)
        else:
            self._serve_page()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/setup/api/setup", "/setup/api/login", "/setup/api/web-ui", "/setup/api/logout"}:
            if web_auth.is_configured() and web_ui_enabled():
                _proxy(self)
            else:
                _json(self, 404, {"error": "Not found"})
            return
        if not _origin_allowed(self):
            _json(self, 403, {"error": "Request origin is not allowed"})
            return
        try:
            data = _read_body(self)
            if path == "/setup/api/setup":
                if web_auth.is_configured():
                    _json(self, 409, {"error": "Administrator setup has already been completed."})
                    return
                if data.get("password") != data.get("password_confirmation"):
                    _json(self, 400, {"error": "Passwords do not match."})
                    return
                web_auth.initialize_password(data.get("password", ""))
                token, csrf, manager_token = _new_session()
                _json(self, 201, {"ok": True, "csrf_token": csrf}, {
                    "Set-Cookie": [
                        f"petcam_setup_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}",
                        f"petcam_session={manager_token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}",
                    ]
                })
                return
            if path == "/setup/api/login":
                peer, now = self.client_address[0], time.time()
                with _login_lock:
                    attempts = [stamp for stamp in _login_attempts.get(peer, []) if stamp > now - 300]
                    if len(attempts) >= 5:
                        _json(self, 429, {"error": "Too many sign-in attempts. Wait five minutes and retry."})
                        return
                    attempts.append(now)
                    _login_attempts[peer] = attempts
                if not web_auth.verify_password(data.get("password", "")):
                    _json(self, 401, {"error": "Invalid password"})
                    return
                with _login_lock:
                    _login_attempts.pop(peer, None)
                token, csrf, manager_token = _new_session()
                _json(self, 200, {"ok": True, "csrf_token": csrf}, {
                    "Set-Cookie": [
                        f"petcam_setup_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}",
                        f"petcam_session={manager_token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}",
                    ]
                })
                return
            session = _get_session(_cookie(self))
            supplied = self.headers.get("X-PetCam-CSRF", "")
            if not session or not secrets.compare_digest(session["csrf"], supplied):
                _json(self, 403, {"error": "Authentication or CSRF validation failed"})
                return
            if path == "/setup/api/web-ui":
                enabled = data.get("enabled")
                set_web_ui_enabled(enabled)
                _json(self, 200, {"ok": True, "enabled": enabled})
                return
            token = _cookie(self)
            with _sessions_lock:
                session = _sessions.pop(token, None)
            if session:
                web_auth.invalidate_session(session.get("manager_token", ""))
            _json(self, 200, {"ok": True}, {
                "Set-Cookie": [
                    "petcam_setup_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0",
                    "petcam_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0",
                ]
            })
        except ValueError as error:
            _json(self, 400, {"error": str(error)})
        except Exception as error:
            logging.exception("Setup portal request failed")
            _json(self, 500, {"error": "The setup request could not be completed."})

    def log_message(self, fmt, *args):
        pass


def main():
    if not TLS_CERT.is_file() or not TLS_KEY.is_file():
        raise SystemExit("PetCam HTTPS certificate is missing.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(TLS_CERT, TLS_KEY)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
