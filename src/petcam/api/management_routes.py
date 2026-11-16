"""Authenticated management route composition."""

from urllib.parse import urlparse

from . import auth_routes, camera_routes, diagnostics_routes, feature_routes


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path.startswith("/static/"):
        services.serve_static_asset(handler, path.removeprefix("/static/"))
        return
    if path == "/api/setup/status":
        handler.send_json(200, {"configured": services.is_configured()})
        return
    if path == "/":
        body = services.PAGE.replace("__PETCAM_HOST__", services.device_mdns_hostname()).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        return
    if not handler._require_auth():
        return
    for routes in (
        auth_routes,
        diagnostics_routes,
        feature_routes,
        camera_routes,
    ):
        if routes.handle_get(handler, services, path):
            return
    if path == "/stream":
        try:
            services.proxy_stream(handler, int(services.parse_config(services.CONFIG)["PORT"]))
        except Exception as error:
            handler.send_json(503, {"error": str(error)})
        return
    handler.send_error(404)


def handle_post(handler, services):
    path = urlparse(handler.path).path
    if auth_routes.handle_public_post(handler, services, path):
        return
    if not handler._require_auth():
        return
    if not handler._require_csrf():
        return
    try:
        data = services._body(handler)
        if auth_routes.handle_authenticated_post(handler, services, path):
            return
        if camera_routes.handle_post(handler, services, path, data):
            return
        if feature_routes.handle_post(handler, services, path, data):
            return
        handler.send_error(404)
    except Exception as error:
        handler.send_json(400, {"error": str(error)})
