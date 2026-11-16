from petcam.api import diagnostics_routes


class Handler:
    def __init__(self):
        self.errors = []

    def send_error(self, status, message=None):
        self.errors.append((status, message))


def test_motion_event_route_rejects_untrusted_filenames_before_reading_disk():
    handler = Handler()
    services = type("Services", (), {})()
    assert diagnostics_routes.handle_get(handler, services, "/api/motion/events/../../secrets.txt")
    assert handler.errors == [(404, None)]
