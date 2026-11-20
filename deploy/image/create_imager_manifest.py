#!/usr/bin/env python3
"""Create a Raspberry Pi Imager manifest for a locally stored PetCam image."""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
from typing import NoReturn
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_SOURCE_URL = "https://downloads.raspberrypi.com/raspios_lite_armhf_latest"
DEFAULT_REPOSITORY_URL = "https://downloads.raspberrypi.com/os_list_imagingutility_v4.json"
VALID_INIT_FORMATS = {"none", "systemd", "cloudinit", "cloudinit-rpi", "rpi-preseed"}
CHUNK_SIZE = 1024 * 1024


def fail(message: str) -> NoReturn:
    raise SystemExit(f"[petcam-imager] ERROR: {message}")


def image_entries(entries: list[dict]) -> list[dict]:
    """Flatten repository categories into downloadable OS entries."""
    flattened: list[dict] = []
    for entry in entries:
        if isinstance(entry.get("subitems"), list):
            flattened.extend(image_entries(entry["subitems"]))
        elif isinstance(entry.get("url"), str):
            flattened.append(entry)
    return flattened


def resolve_source_filename(source_url: str) -> str:
    request = Request(
        source_url,
        method="HEAD",
        headers={"User-Agent": "PetCam-Imager-Manifest/1"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            final_url = response.geturl()
    except (OSError, URLError):
        # Some mirrors reject HEAD even though the image itself is downloadable.
        fallback = Request(
            source_url,
            headers={"Range": "bytes=0-0", "User-Agent": "PetCam-Imager-Manifest/1"},
        )
        try:
            with urlopen(fallback, timeout=30) as response:
                final_url = response.geturl()
        except (OSError, URLError) as exc:
            fail(f"Could not resolve the official Raspberry Pi OS image URL {source_url}: {exc}")
    filename = os.path.basename(urlparse(final_url).path)
    if not filename:
        fail(f"The resolved official image URL has no filename: {final_url}")
    return filename


def load_source_entry(source_url: str, repository_url: str) -> tuple[dict, dict]:
    filename = resolve_source_filename(source_url)
    try:
        with urlopen(repository_url, timeout=30) as response:
            repository = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        fail(f"Could not load Raspberry Pi Imager's official OS manifest: {exc}")

    entries = image_entries(repository.get("os_list", []))
    matches = [entry for entry in entries if os.path.basename(urlparse(entry["url"]).path) == filename]
    if len(matches) != 1:
        fail(
            f"Expected one official manifest entry for {filename}, found {len(matches)}. "
            "The upstream image or manifest may have changed; refusing to guess its customization format."
        )
    source_entry = matches[0]
    init_format = source_entry.get("init_format")
    if init_format not in VALID_INIT_FORMATS:
        fail(f"The official manifest has no supported init_format for {filename}: {init_format!r}")
    return repository, source_entry


def file_hash_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def extracted_hash_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with lzma.open(path, "rb") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
    except (lzma.LZMAError, EOFError, OSError) as exc:
        fail(f"Image must be a readable .xz-compressed disk image: {exc}")
    if size == 0:
        fail("The decompressed disk image is empty.")
    return digest.hexdigest(), size


def create_manifest(
    image: Path, output: Path, image_url: str, source_url: str, repository_url: str
) -> None:
    image = image.expanduser().resolve(strict=True)
    if not image.is_file() or image.suffix != ".xz":
        fail("Pass the compressed PetCam .img.xz file.")

    parsed_image_url = urlparse(image_url)
    if parsed_image_url.scheme != "https" or not parsed_image_url.netloc:
        fail("The published image URL must be an absolute HTTPS URL.")

    repository, upstream_entry = load_source_entry(source_url, repository_url)
    compressed_sha, compressed_size = file_hash_and_size(image)
    extracted_sha, extracted_size = extracted_hash_and_size(image)

    entry = dict(upstream_entry)
    entry.update(
        {
            "name": "PetCam — Raspberry Pi OS Lite (32-bit)",
            "description": "Raspberry Pi OS Lite 32-bit with PetCam preinstalled. Configure hostname, user, password and Wi-Fi in Raspberry Pi Imager before writing.",
            "url": image_url,
            "image_download_size": compressed_size,
            "image_download_sha256": compressed_sha,
            "extract_size": extracted_size,
            "extract_sha256": extracted_sha,
        }
    )

    result: dict = {"os_list": [entry]}
    imager = repository.get("imager", {})
    devices = imager.get("devices", [])
    entry_tags = set(entry.get("devices", []))
    if devices:
        matching_devices = [
            device for device in devices
            if not device.get("tags") or not entry_tags or entry_tags.intersection(device["tags"])
        ]
        if matching_devices:
            result["imager"] = {"devices": matching_devices}

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[petcam-imager] Wrote {output}")
    print(f"[petcam-imager] Preserved upstream customization format: {entry['init_format']}")
    print(f"[petcam-imager] Published image URL: {image_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="local PetCam .img.xz file")
    parser.add_argument(
        "output", nargs="?", type=Path,
        help="JSON manifest output path (default: petcam.rpi-imager-manifest.json beside the image)",
    )
    parser.add_argument(
        "--image-url", required=True,
        help="public HTTPS URL where the release image will be downloaded",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="official upstream image URL used as the build base",
    )
    parser.add_argument(
        "--repository-url",
        default=DEFAULT_REPOSITORY_URL,
        help="Raspberry Pi Imager v4 OS manifest URL",
    )
    args = parser.parse_args()
    output = args.output or args.image.parent / "petcam.rpi-imager-manifest.json"
    create_manifest(args.image, output, args.image_url, args.source_url, args.repository_url)


if __name__ == "__main__":
    main()
