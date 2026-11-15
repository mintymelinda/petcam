"""HTTP proxy for the active MJPEG capture stream."""

import http.client
import time
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request


def proxy(handler, port, *, parse_config, register_client, unregister_client, record_chunk, urlopen=urllib.request.urlopen, sleep=time.sleep):
    """Proxy MJPEG bytes unchanged while recording bounded frame telemetry."""
    query = parse_qs(urlparse(handler.path).query)
    source = "obs_media_source" if query.get("client") == ["obs-media-source"] else "browser_source"
    if parse_config().get("FORMAT") == "H264":
        handler.send_error(503, "HTTP MJPEG streaming is disabled while H.264 capture is selected. Use the OBS RTSP Media Source.")
        return
    client_id = register_client(source)
    parser_state = {
        "previous_byte": None,
        "in_jpeg": False,
        "last_frame_monotonic": None,
    }
    headers_sent = False
    retry_delay = 0.1
    try:
        while True:
            streamed_data = False
            try:
                with urlopen(f"http://127.0.0.1:{port}/stream", timeout=5) as upstream:
                    if not headers_sent:
                        handler.send_response(upstream.status)
                        handler.send_header(
                            "Content-Type",
                            upstream.headers.get("Content-Type", "multipart/x-mixed-replace"),
                        )
                        handler.send_header("Cache-Control", "no-store")
                        handler.end_headers()
                        headers_sent = True
                    read_chunk = getattr(upstream, "read1", upstream.read)
                    while chunk := read_chunk(65536):
                        handler.wfile.write(chunk)
                        record_chunk(client_id, chunk, parser_state)
                        streamed_data = True
                retry_delay = 0.1 if streamed_data else min(2.0, retry_delay * 1.7)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except (OSError, urllib.error.URLError, TimeoutError, http.client.HTTPException):
                if not headers_sent:
                    handler.send_error(503, "Camera MJPEG stream is unavailable")
                    return
                retry_delay = min(2.0, retry_delay * 1.7)
            sleep(retry_delay)
    finally:
        unregister_client(client_id)
