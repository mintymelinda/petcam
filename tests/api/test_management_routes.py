from petcam.api import management_routes


class Handler:
    path = "/api/cameras"

    def __init__(self):
        self.errors = []

    def _require_auth(self):
        return False

    def send_error(self, status):
        self.errors.append(status)


def test_management_api_checks_authentication_before_dispatch():
    handler = Handler()
    management_routes.handle_get(handler, object())
    assert handler.errors == []
