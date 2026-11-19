"""Authenticated management-route dispatcher."""

from urllib.parse import urlparse

from . import auth_routes, camera_routes, diagnostics_routes, feature_routes, system_routes


def handle_get(handler, services):
    path = urlparse(handler.path).path
    if path.startswith("/static/"):
        services.serve_static_asset(handler, path.removeprefix("/static/"))
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
    if auth_routes.handle_get(handler, services):
        return
    if not handler._require_auth():
        return
    for routes in (camera_routes, feature_routes, diagnostics_routes):
        if routes.handle_get(handler, services):
            return
    handler.send_error(404)


def handle_post(handler, services):
    if auth_routes.handle_public_post(handler, services):
        return
    if not handler._require_auth():
        return
    if not handler._require_csrf():
        return
    try:
        data = services._body(handler)
        if auth_routes.handle_authenticated_post(handler, services):
            return
        for routes in (camera_routes, feature_routes, system_routes):
            if routes.handle_post(handler, services, data):
                return
        handler.send_error(404)
    except Exception as error:
        handler.send_json(400, {"error": str(error)})
