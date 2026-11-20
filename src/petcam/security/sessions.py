"""Password hashing and process-shared sessions for the PetCam web manager."""
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path

AUTH_FILE = Path("/etc/petcam/web-auth.json")
SESSION_FILE = Path("/run/petcam/web-sessions.json")
SESSION_TTL = 8 * 60 * 60
PBKDF2_ITERATIONS = 310_000
_sessions = {}
_lock = threading.RLock()


@contextmanager
def _session_store():
    """Serialize session reads and writes across the setup and manager processes."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = SESSION_FILE.with_suffix(SESSION_FILE.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, ValueError):
                data = {}
            yield data
            temporary = SESSION_FILE.with_suffix(SESSION_FILE.suffix + ".tmp")
            temporary.write_text(json.dumps(data) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, SESSION_FILE)
            with _lock:
                _sessions.clear()
                _sessions.update(data)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _prune(data, now):
    for token, session in list(data.items()):
        if not isinstance(session, dict) or session.get("expires_at", 0) <= now:
            del data[token]


def _clear_sessions():
    with _session_store() as data:
        data.clear()


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError("Password must be at least 12 characters and no more than 1024 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {"algorithm": "pbkdf2_sha256", "iterations": PBKDF2_ITERATIONS,
            "salt": salt.hex(), "password_hash": digest.hex()}


def load_auth():
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        if data.get("algorithm") == "pbkdf2_sha256":
            return data
    except (OSError, ValueError, TypeError):
        pass
    return None


def verify_password(password):
    auth = load_auth()
    if not auth or not isinstance(password, str):
        return False
    try:
        salt = bytes.fromhex(auth["salt"])
        expected = bytes.fromhex(auth["password_hash"])
        iterations = int(auth["iterations"])
        if len(salt) != 16 or len(expected) != 32 or not 100_000 <= iterations <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False


def is_configured():
    """Return whether first-run administrator setup has already completed."""
    return AUTH_FILE.exists()


def initialize_password(password):
    """Create the first administrator password without replacing an existing one."""
    if AUTH_FILE.exists():
        raise ValueError("PetCam administrator setup has already been completed.")
    data = hash_password(password)
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data) + "\n"
    with _lock:
        try:
            output = AUTH_FILE.open("x", encoding="utf-8")
        except FileExistsError as error:
            raise ValueError("PetCam administrator setup has already been completed.") from error
        try:
            with output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            _clear_sessions()
        except Exception:
            try:
                AUTH_FILE.unlink()
            except OSError:
                pass
            raise


def save_password(password):
    data = hash_password(password)
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = AUTH_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data) + "\n", encoding="utf-8")
    os.replace(temporary, AUTH_FILE)
    with _lock:
        _clear_sessions()


def new_session(now=None):
    now = time.time() if now is None else now
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with _lock, _session_store() as sessions:
        _prune(sessions, now)
        sessions[token] = {"csrf": csrf, "expires_at": now + SESSION_TTL}
    return token, csrf


def prune_sessions(now=None):
    now = time.time() if now is None else now
    with _lock, _session_store() as sessions:
        _prune(sessions, now)


def get_session(token, now=None):
    if not token:
        return None
    now = time.time() if now is None else now
    with _lock, _session_store() as sessions:
        _prune(sessions, now)
        session = sessions.get(token)
        return dict(session) if session else None


def invalidate_session(token):
    if not token:
        return
    with _lock, _session_store() as sessions:
        sessions.pop(token, None)
