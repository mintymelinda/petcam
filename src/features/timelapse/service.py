#!/usr/bin/env python3
"""Capture periodic JPEG frames from PetCam's existing MJPEG stream."""
import argparse
from io import BytesIO
import json
import os
import shutil
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ...infrastructure.persistence.frames import (
    capture_frame as persist_frame,
    jpeg_frames,
    prune_frames,
    storage_status as persist_storage_status,
)

BASE = Path("/var/lib/petcam/timelapse")
CONFIG = BASE / "config.json"
STATE = BASE / "status.json"
FRAMES = BASE / "frames"
NETWORK_FILESYSTEMS = {"cifs", "nfs", "nfs4"}
from ...domain.timelapse.policy import DEFAULTS, NETWORK_ROOT, in_schedule, validate_config

def capture_frame(frame, directory=None, now=None):
    """Store a JPEG in the timelapse frame directory unless overridden."""
    return persist_frame(frame, directory or FRAMES, now)


def storage_status(directory=None):
    """Summarize the timelapse frame directory unless overridden."""
    return persist_storage_status(directory or FRAMES)


STREAM_URL = "http://127.0.0.1:8081/stream"
_running = True


def load_config(path=CONFIG):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = DEFAULTS
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read timelapse settings: {error}") from error
    return validate_config(data)


def save_config(values, path=CONFIG):
    config = validate_config(values)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return config


def uses_network_storage(directory):
    return Path(directory).resolve().is_relative_to(NETWORK_ROOT.resolve())


def network_storage_ready(mounts_path="/proc/mounts"):
    """Return true only when the dedicated mountpoint is an active SMB/NFS mount."""
    if not os.path.ismount(NETWORK_ROOT):
        return False
    try:
        for line in Path(mounts_path).read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) >= 3:
                mountpoint = fields[1]
                if mountpoint == str(NETWORK_ROOT) and fields[2] in NETWORK_FILESYSTEMS:
                    return True
    except OSError:
        return False
    return False


def write_state(state, path=STATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    preserved = {key: previous.get(key) for key in ("last_capture_at", "last_file")}
    preserved.update(state)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(preserved, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def state_snapshot(config, state_path=STATE, frames_dir=None):
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"state": "waiting", "last_capture_at": None, "last_error": None}
    return {**state, **storage_status(frames_dir or config["storage_path"]), "enabled": config["enabled"], "config": config}


def _free_space_ok(config, directory=None):
    directory = Path(directory or config["storage_path"])
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    return free >= config["min_free_mb"] * 1024 * 1024, free


def process_frame(frame, config):
    if config["max_width"] == 0 and config["jpeg_quality"] == 0:
        return frame
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Pillow is required to resize or adjust timelapse JPEG quality.") from error
    with Image.open(BytesIO(frame)) as image:
        image.load()
        if config["max_width"] and image.width > config["max_width"]:
            height = max(1, round(image.height * config["max_width"] / image.width))
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize((config["max_width"], height), resampling)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=config["jpeg_quality"] or 95, optimize=False)
        return output.getvalue()


def capture_from_stream(config, directory=None, url=STREAM_URL):
    request = urllib.request.Request(url, headers={"User-Agent": "PetCam-Timelapse/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        frame = next(jpeg_frames(response), None)
    if frame is None:
        raise OSError("The live stream closed before a JPEG frame arrived.")
    return capture_frame(process_frame(frame, config), directory or config["storage_path"])


def run():
    global _running
    BASE.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    next_capture = 0.0
    directory = FRAMES
    last_error = None
    while _running:
        try:
            config = load_config()
            if not config["enabled"]:
                write_state({"state": "disabled", "last_error": None})
                next_capture = 0.0
                time.sleep(2)
                continue
            now = datetime.now().astimezone()
            if not in_schedule(now, config["schedule_start"], config["schedule_end"]):
                write_state({"state": "outside_schedule", "last_error": None})
                time.sleep(5)
                continue
            if time.monotonic() < next_capture:
                time.sleep(min(2, max(0.2, next_capture - time.monotonic())))
                continue
            directory = Path(config["storage_path"])
            if uses_network_storage(directory) and not network_storage_ready():
                last_error = "Network storage is not mounted at /mnt/petcam-network; capture is paused to protect the SD card."
                write_state({"state": "network_storage_unavailable", "last_error": last_error})
                time.sleep(5)
                continue
            prune_frames(config, directory)
            enough_space, free = _free_space_ok(config, directory)
            if not enough_space:
                last_error = f"Free space below configured minimum ({free // 1048576} MiB available)."
                write_state({"state": "storage_limit", "last_error": last_error, **storage_status(directory)})
                next_capture = time.monotonic() + config["interval_seconds"]
                time.sleep(2)
                continue
            try:
                path = capture_from_stream(config, directory)
                prune_frames(config, directory)
                last_error = None
                write_state({
                    "state": "running", "last_capture_at": datetime.now(timezone.utc).isoformat(),
                    "last_file": path.name, "last_error": None, **storage_status(directory),
                })
            except (OSError, urllib.error.URLError, StopIteration, ValueError) as error:
                last_error = str(error)
                write_state({"state": "camera_unavailable", "last_error": last_error, **storage_status(directory)})
            next_capture = time.monotonic() + config["interval_seconds"]
        except Exception as error:
            last_error = str(error)
            write_state({"state": "error", "last_error": last_error, **storage_status(directory)})
            time.sleep(5)


def _stop(_signum, _frame):
    global _running
    _running = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        print(json.dumps(load_config(), indent=2))
        return 0
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
