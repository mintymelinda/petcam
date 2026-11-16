from petcam.api import streaming_routes


class Handler:
    path = "/"

    def __init__(self):
        self.errors = []

    def send_error(self, *args):
        self.errors.append(args)


def test_browser_preview_is_disabled_when_h264_is_selected():
    handler = Handler()
    services = type("Services", (), {
        "parse_config": lambda self, path: {"FORMAT": "H264"},
        "CONFIG": "/etc/petcam/petcam.conf",
    })()
    streaming_routes.handle_get(handler, services)
    assert handler.errors
    assert handler.errors[0][0] == 503
