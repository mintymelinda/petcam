"""Shared JPEG frame parsing and atomic frame-storage adapters."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

def jpeg_frames(response, chunk_size=4096):
    buffer = bytearray()
    while True:
        reader = getattr(response, "read1", None)
        if reader is None:
            reader = response.read
        chunk = reader(chunk_size)
        if not chunk:
            return
        buffer.extend(chunk)
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                if len(buffer) > 1:
                    del buffer[:-1]
                break
            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                if start:
                    del buffer[:start]
                break
            yield bytes(buffer[start:end + 2])
            del buffer[:end + 2]

def storage_status(directory):
    directory = Path(directory)
    files = sorted((p for p in directory.glob("*.jpg") if p.is_file()), key=lambda p: p.name) if directory.exists() else []
    return {"frames": len(files), "storage_bytes": sum(p.stat().st_size for p in files)}

def prune_frames(config, directory=None, now=None):
    directory = Path(directory or config["storage_path"])
    directory.mkdir(parents=True, exist_ok=True)
    now = now or time.time()
    for temporary in directory.glob("*.jpg.tmp"):
        temporary.unlink(missing_ok=True)
    cutoff = now - config["retention_days"] * 86400
    files = sorted((p for p in directory.glob("*.jpg") if p.is_file()), key=lambda p: (p.stat().st_mtime, p.name))
    for path in files:
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    files = sorted((p for p in directory.glob("*.jpg") if p.is_file()), key=lambda p: (p.stat().st_mtime, p.name))
    total = sum(p.stat().st_size for p in files)
    maximum = config["max_storage_mb"] * 1024 * 1024
    while files and total > maximum:
        oldest = files.pop(0)
        size = oldest.stat().st_size
        oldest.unlink(missing_ok=True)
        total -= size
    return storage_status(directory)

def capture_frame(frame, directory, now=None):
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise ValueError("The camera stream did not provide a complete JPEG frame.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = stamp.strftime("%Y%m%dT%H%M%S.%fZ")
    target = directory / f"{base}.jpg"
    suffix = 1
    while target.exists():
        target = directory / f"{base}-{suffix:03d}.jpg"
        suffix += 1
    temporary = target.with_suffix(".jpg.tmp")
    with temporary.open("xb") as stream:
        stream.write(frame)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return target

