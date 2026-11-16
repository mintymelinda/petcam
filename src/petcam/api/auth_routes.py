"""Authentication and session HTTP routes."""

import time


def handle_get(handler, services, path):
    if path == "/api/session":
        handler.send_json(200, {"csrf_token": handler._session()["csrf"]})
        return True
    return False


def handle_public_post(handler, services, path):
    if path == "/api/setup":
        if services.is_configured():
            handler.send_json(409, {"error": "PetCam administrator setup has already been completed."})
            return True
        if not services._origin_ok(handler):
            handler.send_json(403, {"error": "Request origin is not allowed"})
            return True
        try:
            data = services._body(handler, 4096)
            if data.get("password") != data.get("password_confirmation"):
                handler.send_json(400, {"error": "The passwords do not match."})
                return True
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
        return True

    if path == "/api/login":
        if not services._origin_ok(handler):
            handler.send_json(403, {"error": "Request origin is not allowed"})
            return True
        try:
            data = services._body(handler, 4096)
            peer = handler.client_address[0]
            now = time.time()
            with services._login_lock:
                attempts = [stamp for stamp in services._login_attempts.get(peer, []) if stamp > now - 300]
                if len(attempts) >= 5:
                    handler.send_json(429, {"error": "Too many sign-in attempts. Wait five minutes and retry."})
                    return True
                attempts.append(now)
                services._login_attempts[peer] = attempts
            if not services.verify_password(data.get("password", "")):
                handler.send_json(401, {"error": "Invalid password"})
                return True
            with services._login_lock:
                services._login_attempts.pop(peer, None)
            token, csrf = services.new_session()
            handler.send_json(200, {"ok": True, "csrf_token": csrf}, {
                "Set-Cookie": f"petcam_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={services.SESSION_TTL}"
            })
        except Exception as error:
            handler.send_json(400, {"error": str(error)})
        return True
    return False


def handle_authenticated_post(handler, services, path):
    if path == "/api/logout":
        services.invalidate_session(services._cookie(handler))
        handler.send_json(200, {"ok": True}, {
            "Set-Cookie": "petcam_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
        })
        return True
    return False
