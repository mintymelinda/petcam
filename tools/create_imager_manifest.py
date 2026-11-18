#!/usr/bin/env python3
"""Generate a Raspberry Pi Imager repository manifest for PetCam images."""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
from datetime import date
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

ICON_URL = (
    "https://raw.githubusercontent.com/mintymelinda/petcam/main/"
    "deploy/image/petcam-icon.svg"
)
WEBSITE_URL = "https://github.com/mintymelinda/petcam"
DEVICE_PROFILES = [
    {
        "name": "Raspberry Pi Zero W",
        "description": "Original Raspberry Pi Zero W (ARMv6)",
        "tags": ["pizero-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi 4",
        "description": "Raspberry Pi 4 Model B",
        "tags": ["pi4"],
        "architecture": "armv8",
    },
    {
        "name": "Raspberry Pi 5",
        "description": "Raspberry Pi 5",
        "tags": ["pi5"],
        "architecture": "armv8",
    },
]


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def image_metadata(image_path: Path) -> dict[str, str | int]:
    """Return hashes and sizes for the compressed download and extracted image."""
    with image_path.open("rb") as stream:
        download_sha256, download_size = _hash_stream(stream)

    opener = lzma.open if image_path.suffix == ".xz" else open
    with opener(image_path, "rb") as stream:
        extract_sha256, extract_size = _hash_stream(stream)

    return {
        "extract_sha256": extract_sha256,
        "extract_size": extract_size,
        "image_download_sha256": download_sha256,
        "image_download_size": download_size,
    }


def _validate_image_url(image_url: str) -> None:
    parsed_url = urlparse(image_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("image URL must be an absolute HTTP or HTTPS URL")


def _os_entry(
    *,
    name: str,
    description: str,
    image_path: Path,
    image_url: str,
    architecture: str,
    devices: list[str],
    release_date: str,
) -> dict[str, object]:
    _validate_image_url(image_url)
    return {
        "name": name,
        "description": description,
        "icon": ICON_URL,
        "url": image_url,
        "website": WEBSITE_URL,
        "architecture": architecture,
        "init_format": "cloudinit",
        "devices": devices,
        "release_date": release_date,
        **image_metadata(image_path),
    }


def create_manifest(
    armhf_image_path: Path,
    armhf_image_url: str,
    arm64_image_path: Path,
    arm64_image_url: str,
    release_date: str,
) -> dict[str, object]:
    """Build the Imager manifest with ARMHF and ARM64 install choices."""
    date.fromisoformat(release_date)
    return {
        "imager": {"devices": DEVICE_PROFILES},
        "os_list": [
            _os_entry(
                name="PetCam OS (32-bit)",
                description=(
                    "PetCam appliance for the original Raspberry Pi Zero W "
                    "(ARMv6). Configure hostname, user credentials, Wi-Fi, "
                    "locale and SSH in Raspberry Pi Imager before flashing."
                ),
                image_path=armhf_image_path,
                image_url=armhf_image_url,
                architecture="armhf",
                devices=["pizero-32bit"],
                release_date=release_date,
            ),
            _os_entry(
                name="PetCam OS (64-bit)",
                description=(
                    "PetCam appliance for Raspberry Pi 4 and Raspberry Pi 5. "
                    "Configure hostname, user credentials, Wi-Fi, locale and "
                    "SSH in Raspberry Pi Imager before flashing."
                ),
                image_path=arm64_image_path,
                image_url=arm64_image_url,
                architecture="armv8",
                devices=["pi4", "pi5"],
                release_date=release_date,
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--armhf-image", required=True, type=Path)
    parser.add_argument("--armhf-image-url", required=True)
    parser.add_argument("--arm64-image", required=True, type=Path)
    parser.add_argument("--arm64-image-url", required=True)
    parser.add_argument("--release-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for image_path in (args.armhf_image, args.arm64_image):
        if not image_path.is_file():
            parser.error(f"image does not exist: {image_path}")
    manifest = create_manifest(
        args.armhf_image,
        args.armhf_image_url,
        args.arm64_image,
        args.arm64_image_url,
        args.release_date,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
