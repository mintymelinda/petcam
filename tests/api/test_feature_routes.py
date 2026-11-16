from petcam.api import feature_routes


class Handler:
    def __init__(self):
        self.responses = []

    def send_json(self, *args):
        self.responses.append(args)


def test_timelapse_route_returns_configuration_and_runtime_snapshot():
    handler = Handler()
    services = type("Services", (), {
        "load_timelapse_config": lambda self: {"enabled": True},
        "timelapse_snapshot": lambda self, config: {"frame_count": 12},
    })()
    assert feature_routes.handle_get(handler, services, "/api/timelapse")
    assert handler.responses == [(200, {
        "config": {"enabled": True},
        "status": {"frame_count": 12},
    })]


def test_feature_update_route_returns_the_saved_configuration():
    handler = Handler()
    services = type("Services", (), {
        "update_motion": lambda self, data: {"enabled": data["enabled"]},
    })()
    assert feature_routes.handle_post(handler, services, "/api/motion", {"enabled": True})
    assert handler.responses == [(200, {"ok": True, "config": {"enabled": True}})]
