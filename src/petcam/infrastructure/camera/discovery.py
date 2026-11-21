"""Discover USB and CSI cameras and the native H.264 encoder capability."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ...domain.camera.capabilities import parse_csi_cameras, parse_v4l2_modes


def discover_csi_cameras() -> list[dict]:
    """Return the CSI cameras and sensor modes reported by the Raspberry Pi stack."""
    try:
        result = subprocess.run(
            ["rpicam-hello", "--list-cameras"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    return parse_csi_cameras(result.stdout + "\n" + result.stderr)


def _usb_parent(video_entry: Path) -> Path | None:
    try:
        device_path = (video_entry / "device").resolve(strict=True)
    except OSError:
        return None
    for parent in (device_path, *device_path.parents):
        if (parent / "idVendor").is_file() and (parent / "idProduct").is_file():
            return parent
    return None


def discover_usb_cameras(
    sysfs_root: Path = Path("/sys/class/video4linux"),
    dev_root: Path = Path("/dev"),
) -> list[dict]:
    """Return one V4L2 capture node per physical USB camera, including its modes."""
    groups: dict[str, list[Path]] = {}
    for entry in sorted(sysfs_root.glob("video*")):
        parent = _usb_parent(entry)
        node = dev_root / entry.name
        if parent is not None and node.exists():
            groups.setdefault(str(parent), []).append(node)

    aliases: dict[str, Path] = {}
    for alias in sorted((dev_root / "v4l/by-id").glob("*")):
        try:
            aliases[str(alias.resolve(strict=True))] = alias
        except OSError:
            continue

    cameras = []
    for physical_path, nodes in sorted(groups.items()):
        candidates = sorted(nodes, key=lambda node: (str(node) not in aliases, str(node)))
        for node in candidates:
            device = str(aliases.get(str(node), node))
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "--device", device, "--list-formats-ext"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=8,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode:
                continue
            modes = parse_v4l2_modes(result.stdout)
            if not modes:
                continue
            name_path = sysfs_root / node.name / "name"
            try:
                label = name_path.read_text(encoding="utf-8").strip()
            except OSError:
                label = "USB camera"
            cameras.append({
                "kind": "USB",
                "device": device,
                "physical_path": physical_path,
                "label": label or "USB camera",
                "modes": modes,
            })
            break
    return cameras


def detect_hardware_h264_encoder(
    sysfs_root: Path = Path("/sys/class/video4linux"),
    dev_root: Path = Path("/dev"),
) -> dict:
    """Require a V4L2 hardware H.264 encoder; never accept a software encoder."""
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
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and re.search(r"['\"]H264['\"]|H\.264", result.stdout, re.IGNORECASE):
            return {"available": True, "device": str(device), "encoder": name, "format": "H264"}
    return {"available": False, "device": None, "encoder": None, "format": None}
