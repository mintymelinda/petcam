"""Always-on lightweight setup portal and reverse proxy for the optional manager."""

from __future__ import annotations

import http.client
import json
import logging
import secrets
import ssl
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
SESSION_TTL = 8 * 60 * 60
MAX_BODY = 16 * 1024 * 1024
PROXY_TIMEOUT_SECONDS = 60
_sessions: dict[str, dict] = {}
_sessions_lock = threading.RLock()
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PetCam Setup</title>
<style>
:root{color-scheme:dark;font:16px system-ui,sans-serif;background:#17191d;color:#eee}
body{max-width:34rem;margin:8vh auto;padding:0 1rem}main{background:#22262c;border:1px solid #383e47;border-radius:12px;padding:1.4rem}
h1{font-size:1.5rem}label{display:block;margin:.9rem 0 .3rem}input{box-sizing:border-box;width:100%;font:inherit;padding:.7rem;border:1px solid #59616d;border-radius:6px;background:#303741;color:inherit}
button,a.button{display:inline-block;font:inherit;padding:.7rem 1rem;border:1px solid #68788c;border-radius:6px;background:#3b4654;color:#fff;text-decoration:none;cursor:pointer;margin-top:.7rem}
small,.muted{color:#aeb7c2}#message{min-height:1.5rem;color:#b9d8ff}#manager-control[hidden],#setup-form[hidden],#login-form[hidden],#open-manager[hidden]{display:none}
.switch{display:flex;align-items:center;gap:.7rem;margin:1rem 0}.switch input{width:auto}
</style></head><body><main><h1>PetCam <small>Device setup</small></h1>
<p class="muted">This lightweight page remains available even when the full management dashboard is switched off.</p>
<form id="setup-form" hidden><h2>First-time administrator setup</h2>
<label for="new-password">Create administrator password (12–1024 characters)</label><input id="new-password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required>
<label for="confirm-password">Confirm password</label><input id="confirm-password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required>
<button type="submit">Create administrator password</button></form>
<form id="login-form" hidden><h2>Administrator login</h2>
<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form>
<section id="manager-control" hidden><h2>Full Web UI</h2><p id="web-state" class="muted">Checking status…</p>
<label class="switch"><input id="web-enabled" type="checkbox"> Enable full Web UI</label>
<p class="muted">The full dashboard is a separate service. Turning it off does not disable this setup page, camera streaming, or other enabled features.</p>
<button id="save" type="button">Save Web UI setting</button><button id="logout" type="button">Sign out</button>
<p><a id="open-manager" class="button" href="/" hidden>Open full dashboard</a></p><p id="manager-readiness" class="muted" role="status">Full Web UI is not ready.</p>
<section id="stream-info"><h3>RTSP camera stream</h3><label for="rtsp-url">Stream URL</label><input id="rtsp-url" type="text" readonly><button id="copy-rtsp-url" type="button">Copy stream URL</button><p class="muted">Use this URL in OBS or another RTSP client.</p></section></section>
<p id="message" role="status" aria-live="polite"></p></main>
<script>
const $=id=>document.getElementById(id);let csrf="";
async function api(path,body){const headers={"Content-Type":"application/json"};if(csrf)headers["X-PetCam-CSRF"]=csrf;
 const response=await fetch("/setup/api/"+path,{method:body===undefined?"GET":"POST",headers,body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json().catch(()=>({error:"Unexpected server response"}));if(!response.ok)throw Error(data.error||"Request failed");return data;}
function message(value){$("message").textContent=value;}
function rtspStreamUrl(){let host=window.location.hostname;if(host.startsWith("[")&&host.endsWith("]"))host=host.slice(1,-1);if(host.includes(":"))host="["+host+"]";return "rtsp://"+host+":8554/petcam";}
let readinessTimer=null;
async function refreshManagerReadiness(){const link=$("open-manager"),status=$("manager-readiness");try{const result=await api("manager-status");link.hidden=!result.ready;status.textContent=result.ready?"Full Web UI is ready.":"Full Web UI is starting or unavailable.";}catch(_){link.hidden=true;status.textContent="Full Web UI readiness could not be confirmed.";}}
function startReadinessChecks(){if(readinessTimer!==null)clearInterval(readinessTimer);refreshManagerReadiness();readinessTimer=setInterval(refreshManagerReadiness,2000);}
async function refresh(){try{const status=await api("status");$("setup-form").hidden=status.configured;$("login-form").hidden=!status.configured;
 if(status.configured){try{const session=await api("session");csrf=session.csrf_token;$("manager-control").hidden=false;$("login-form").hidden=true;
 $("web-enabled").checked=status.enabled;$("rtsp-url").value=rtspStreamUrl();$("web-state").textContent=status.enabled?"Full Web UI is enabled.":"Full Web UI is disabled.";if(status.enabled)startReadinessChecks();else{if(readinessTimer!==null)clearInterval(readinessTimer);readinessTimer=null;$("open-manager").hidden=true;$("manager-readiness").textContent="Full Web UI is disabled.";}
 }catch(_){$("manager-control").hidden=true;$("login-form").hidden=false;}}
 }catch(error){message(error.message);}}
$("setup-form").addEventListener("submit",async event=>{event.preventDefault();try{if($("new-password").value!==$("confirm-password").value)throw Error("Passwords do not match.");
 const result=await api("setup",{password:$("new-password").value,password_confirmation:$("confirm-password").value});csrf=result.csrf_token;message("Administrator password created.");await refresh();}catch(error){message(error.message);}});
$("login-form").addEventListener("submit",async event=>{event.preventDefault();try{const result=await api("login",{password:$("password").value});csrf=result.csrf_token;$("password").value="";message("Signed in.");await refresh();}catch(error){message(error.message);}});
$("save").addEventListener("click",async()=>{try{const result=await api("web-ui",{enabled:$("web-enabled").checked});$("web-state").textContent=result.enabled?"Full Web UI is enabled.":"Full Web UI is disabled.";if(result.enabled){$("open-manager").hidden=true;startReadinessChecks();}else{if(readinessTimer!==null)clearInterval(readinessTimer);readinessTimer=null;$("open-manager").hidden=true;$("manager-readiness").textContent="Full Web UI is disabled.";}message("Setting saved. Waiting for the full console to become ready.");}catch(error){message(error.message);}});
$("copy-rtsp-url").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("rtsp-url").value);message("RTSP stream URL copied.");}catch(_){message("Unable to copy automatically. Select and copy the URL above.");}});
$("logout").addEventListener("click",async()=>{try{await api("logout",{});}catch(_){}csrf="";if(readinessTimer!==null)clearInterval(readinessTimer);readinessTimer=null;$("open-manager").hidden=true;$("manager-control").hidden=true;await refresh();});
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


def manager_ready() -> bool:
    """Report ready only after the full manager serves its dashboard page."""
    if not web_ui_enabled():
        return False
    connection = None
    try:
        connection = http.client.HTTPSConnection(
            MANAGER_HOST, MANAGER_PORT,
            context=ssl._create_unverified_context(), timeout=2,
        )
        connection.request("GET", "/api/ready")
        response = connection.getresponse()
        payload = json.loads(response.read(4096))
        return response.status == 200 and payload == {"ready": True}
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        if connection is not None:
            connection.close()


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
    try:
        connection = http.client.HTTPSConnection(
            MANAGER_HOST, MANAGER_PORT, context=ssl._create_unverified_context(), timeout=PROXY_TIMEOUT_SECONDS
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
        handler.wfile.write(payload)
        connection.close()
    except (OSError, http.client.HTTPException) as error:
        logging.warning("Full Web UI proxy unavailable: %s", error)
        _json(handler, 503, {"error": "The full Web UI is enabled but is not currently available."})


class Handler(BaseHTTPRequestHandler):
    def _serve_page(self):
        body = PAGE.encode("utf-8")
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
