"""Bounded per-client MJPEG throughput and frame-timing telemetry."""

import threading
import time


_lock = threading.Lock()
_clients = {}
_client_sequence = 0


def register_client(source):
    """Track one downstream MJPEG client without retaining its network address."""
    global _client_sequence
    with _lock:
        _client_sequence += 1
        client_id = str(_client_sequence)
        now = time.monotonic()
        _clients[client_id] = {
            "source": source,
            "started_monotonic": now,
            "window_started_monotonic": now,
            "window_frames": 0,
            "window_bytes": 0,
            "frames": 0,
            "bytes": 0,
            "inter_frame_count": 0,
            "inter_frame_total_seconds": 0.0,
            "max_frame_gap_seconds": 0.0,
            "last_frame_at": None,
            "last_frame_monotonic": None,
        }
    return client_id


def unregister_client(client_id):
    with _lock:
        _clients.pop(client_id, None)


def record_chunk(client_id, chunk, parser_state):
    """Count JPEG marker pairs using bytes.find; never decode or copy image data."""
    data = (b"\xff" if parser_state["previous_byte"] == 0xFF else b"") + chunk
    cursor = 0
    frames = 0
    last_frame_at = None
    while True:
        start = data.find(b"\xff\xd8", cursor)
        end = data.find(b"\xff\xd9", cursor)
        if start < 0 and end < 0:
            break
        if start >= 0 and (end < 0 or start < end):
            parser_state["in_jpeg"] = True
            cursor = start + 2
        else:
            if parser_state["in_jpeg"]:
                frames += 1
                parser_state["last_frame_monotonic"] = time.monotonic()
                last_frame_at = time.time()
            parser_state["in_jpeg"] = False
            cursor = end + 2
    if chunk:
        parser_state["previous_byte"] = chunk[-1]
    with _lock:
        metrics = _clients.get(client_id)
        if metrics is not None:
            metrics["bytes"] += len(chunk)
            metrics["window_bytes"] += len(chunk)
            metrics["frames"] += frames
            metrics["window_frames"] += frames
            if last_frame_at is not None:
                previous = metrics["last_frame_monotonic"]
                current = parser_state["last_frame_monotonic"]
                if previous is not None:
                    gap = max(0.0, current - previous)
                    metrics["inter_frame_count"] += 1
                    metrics["inter_frame_total_seconds"] += gap
                    metrics["max_frame_gap_seconds"] = max(metrics["max_frame_gap_seconds"], gap)
                metrics["last_frame_at"] = last_frame_at
                metrics["last_frame_monotonic"] = current


def snapshot():
    """Return bounded per-client throughput and frame-timing telemetry."""
    now = time.monotonic()
    with _lock:
        clients = []
        for client_id, metrics in _clients.items():
            elapsed = max(0.001, now - metrics["started_monotonic"])
            window_elapsed = max(0.001, now - metrics["window_started_monotonic"])
            last_frame = metrics["last_frame_monotonic"]
            clients.append({
                "client_id": client_id,
                "source": metrics["source"],
                "frames": metrics["frames"],
                "bytes": metrics["bytes"],
                "average_fps": round(metrics["frames"] / elapsed, 2),
                "window_fps": round(metrics["window_frames"] / window_elapsed, 2),
                "window_mbps": round(metrics["window_bytes"] * 8 / window_elapsed / 1_000_000, 3),
                "average_frame_interval_ms": (
                    round(metrics["inter_frame_total_seconds"] * 1000 / metrics["inter_frame_count"], 2)
                    if metrics["inter_frame_count"] else None
                ),
                "max_frame_gap_ms": round(metrics["max_frame_gap_seconds"] * 1000, 2),
                "last_frame_age_seconds": (
                    round(max(0.0, now - last_frame), 2) if last_frame is not None else None
                ),
            })
            metrics["window_started_monotonic"] = now
            metrics["window_frames"] = 0
            metrics["window_bytes"] = 0
    return {"active_clients": len(clients), "clients": clients}
