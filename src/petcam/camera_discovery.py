"""Hardware-backed USB and CSI camera discovery adapters."""

import re
import subprocess
from pathlib import Path

if __package__:
    from .camera_capabilities import parse_csi_cameras, parse_modes
else:  # Support the installed standalone camera worker entry point.
    from camera_capabilities import parse_csi_cameras, parse_modes


def discover_csi_cameras():
    result = subprocess.run(
        ["rpicam-hello", "--list-cameras"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if result.returncode:
        return []
    return parse_csi_cameras(result.stdout + "\n" + result.stderr)


def read_model():
    path = Path("/proc/device-tree/model")
    try:
        return path.read_text(errors="replace").strip("\x00\n ")
    except OSError:
        return "Unknown Raspberry Pi model"


def usb_parent_for_video_node(video_entry):
    """Return the physical USB device directory for a V4L2 node, or None."""
    try:
        device_path = (video_entry / "device").resolve(strict=True)
    except OSError:
        return None
    for parent in (device_path, *device_path.parents):
        if (parent / "idVendor").is_file() and (parent / "idProduct").is_file():
            return parent
    return None


def discover_devices(sysfs_root=Path("/sys/class/video4linux"), dev_root=Path("/dev")):
    """Discover one usable V4L2 capture interface per physical USB camera."""
    groups = {}
    for entry in sorted(sysfs_root.glob("video*")):
        parent = usb_parent_for_video_node(entry)
        if parent is None:
            continue
        node = dev_root / entry.name
        if node.exists():
            groups.setdefault(str(parent), []).append(node)
    aliases = {}
    for alias in sorted((dev_root / "v4l/by-id").glob("*")):
        try:
            aliases[str(alias.resolve(strict=True))] = alias
        except OSError:
            continue
    devices = []
    for physical_path, nodes in groups.items():
        # A camera may expose multiple video nodes; publish only one interface.
        candidates = sorted(nodes, key=lambda node: (str(node) not in aliases, str(node)))
        for node in candidates:
            device = str(aliases.get(str(node), node))
            result = subprocess.run(["v4l2-ctl", "--device", device, "--list-formats-ext"],
                                    capture_output=True, text=True, check=False)
            if result.returncode:
                continue
            modes = parse_modes(result.stdout)
            if modes:
                devices.append({"device": device, "physical_path": physical_path, "modes": modes})
                break
    return devices

def detect_hardware_h264_encoder(sysfs_root=Path("/sys/class/video4linux"), dev_root=Path("/dev")):
    """Return a confirmed Raspberry Pi hardware H.264 encoder node, never a software fallback."""
    for entry in sorted(sysfs_root.glob("video*")):
        try:
            name = (entry / "name").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if "bcm2835-codec-encode" not in name:
            continue
        device = dev_root / entry.name
        if not device.exists():
            continue
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--device", str(device), "--list-formats"],
                capture_output=True, text=True, check=False, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and re.search(r"['\"]H264['\"]|H\.264", result.stdout, re.IGNORECASE):
            return {"available": True, "device": str(device), "encoder": name, "format": "H264"}
    return {"available": False, "device": None, "encoder": None, "format": None}
