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

# These are Raspberry Pi Imager's 32-bit model tags. Zero 2 W shares
# the pi3-32bit compatibility tag.
DEVICE_PROFILES = [
    {
        "name": "Raspberry Pi 5",
        "description": "Raspberry Pi 5, 500 / 500+, and Compute Module 5",
        "tags": ["pi5-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi 4",
        "description": "Raspberry Pi 4 Model B, 400, and Compute Module 4 / 4S",
        "tags": ["pi4-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi 3",
        "description": "Raspberry Pi 3 Model A+ / B / B+, Zero 2 W, and Compute Module 3 / 3+",
        "tags": ["pi3-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi 2",
        "description": "Raspberry Pi 2 Model B",
        "tags": ["pi2-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi 1",
        "description": "Raspberry Pi 1 Model A / A+ / B / B+ and Compute Module 1",
        "tags": ["pi1-32bit"],
        "architecture": "armhf",
    },
    {
        "name": "Raspberry Pi Zero",
        "description": "Raspberry Pi Zero, Zero W, and Zero WH",
        "tags": ["pizero-32bit"],
        "architecture": "armhf",
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


def create_manifest(
    image_path: Path,
    image_url: str,
    release_date: str,
) -> dict[str, object]:
    """Build one 32-bit Imager install choice for every supported Pi generation."""
    date.fromisoformat(release_date)
    _validate_image_url(image_url)
    all_device_tags = [tag for device in DEVICE_PROFILES for tag in device["tags"]]
    return {
        "imager": {"devices": DEVICE_PROFILES},
        "os_list": [
            {
                "name": "PetCam OS (32-bit)",
                "description": (
                    "One 32-bit ARMHF PetCam appliance image for Raspberry Pi "
                    "1 through Raspberry Pi 5, including Zero, Zero W, Zero 2 W, "
                    "400-series boards, and Compute Modules. Configure hostname, "
                    "user credentials, Wi-Fi, locale and SSH in Raspberry Pi "
                    "Imager before flashing."
                ),
                "icon": ICON_URL,
                "url": image_url,
                "website": WEBSITE_URL,
                "architecture": "armhf",
                "init_format": "cloudinit",
                "devices": all_device_tags,
                "release_date": release_date,
                **image_metadata(image_path),
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--image-url", required=True)
    parser.add_argument("--release-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")
    manifest = create_manifest(args.image, args.image_url, args.release_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
