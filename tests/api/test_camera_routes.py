from petcam.api import camera_routes


class Handler:
    def __init__(self):
        self.responses = []

    def send_json(self, *args):
        self.responses.append(args)


def test_camera_inventory_route_returns_active_configuration():
    handler = Handler()
    services = type("Services", (), {
        "camera_inventory": lambda self: [{"id": "usb-camera"}],
        "active_camera_config": lambda self: {"FORMAT": "MJPEG"},
        "live_capture_status": lambda self: {"active": True},
    })()
    assert camera_routes.handle_get(handler, services, "/api/cameras")
    assert handler.responses[0][1]["cameras"] == [{"id": "usb-camera"}]
    assert handler.responses[0][1]["capture_status"] == {"active": True}
