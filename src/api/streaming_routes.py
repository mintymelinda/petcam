"""HTTP route dispatch for the unauthenticated OBS browser-source interface."""

from urllib.parse import urlparse


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path == "/browser-source.js":
        services.serve_static_asset(handler, "browser-source.js")
        return
    try:
        if services.parse_config(services.CONFIG).get("FORMAT") == "H264":
            handler.send_error(503, "HTTP Browser Source is disabled while H.264 capture is selected. Use the RTSP endpoint.")
            return
    except Exception:
        pass
    if path == "/":
        body = (services.STATIC_DIR / "browser-source.html").read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        return
    if path != "/stream":
        handler.send_error(404)
        return
    try:
        services.proxy_stream(handler, int(services.parse_config(services.CONFIG)["PORT"]))
    except Exception:
        handler.send_error(503)

