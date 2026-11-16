import threading

from petcam.api import auth_routes


class Handler:
    client_address = ("127.0.0.1", 5000)

    def __init__(self):
        self.responses = []

    def send_json(self, *args):
        self.responses.append(args)


def test_session_route_returns_the_current_csrf_token():
    handler = Handler()
    handler._session = lambda: {"csrf": "csrf-token"}
    assert auth_routes.handle_get(handler, object(), "/api/session")
    assert handler.responses == [(200, {"csrf_token": "csrf-token"})]


def test_login_route_sets_a_secure_session_cookie():
    handler = Handler()
    services = type("Services", (), {})()
    services._origin_ok = lambda request: True
    services._body = lambda request, maximum: {"password": "valid"}
    services._login_lock = threading.Lock()
    services._login_attempts = {}
    services.verify_password = lambda password: password == "valid"
    services.new_session = lambda: ("session-token", "csrf-token")
    services.SESSION_TTL = 3600
    assert auth_routes.handle_public_post(handler, services, "/api/login")
    status, payload, headers = handler.responses[0]
    assert status == 200
    assert payload["csrf_token"] == "csrf-token"
    assert "HttpOnly" in headers["Set-Cookie"]
    assert "SameSite=Strict" in headers["Set-Cookie"]
