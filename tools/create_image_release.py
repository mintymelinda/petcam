#!/usr/bin/env python3
"""Create and Ed25519-sign a manifest for a production PetCam OS image."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

VERSION_PATTERN = re.compile(r"^[0-9]+\\.[0-9]+\\.[0-9]+$")
MAX_IMAGE_SIZE = 16 * 1024 * 1024 * 1024

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def create_signed_image_manifest(image: Path, version: str, image_url: str,
                                  private_key: Path, public_key: Path,
                                  output_dir: Path) -> tuple[Path, Path]:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must use MAJOR.MINOR.PATCH format")
    if not image.is_file() or image.is_symlink():
        raise ValueError(f"Image must be a regular file: {image}")
    if image.suffixes[-2:] != [".img", ".xz"]:
        raise ValueError("Production image must be an .img.xz file")
    if not image_url.startswith("https://"):
        raise ValueError("Image URL must use HTTPS")
    if not private_key.is_file() or not public_key.is_file():
        raise ValueError("Both signing private key and pinned public key are required")
    size = image.stat().st_size
    if size < 1 or size > MAX_IMAGE_SIZE:
        raise ValueError(f"Image size is outside the allowed range: {size}")
    output_dir.mkdir(parents=True, exist_ok=True)
    derived = output_dir / ".derived-public.pem"
    try:
        subprocess.run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(derived)], check=True, capture_output=True)
        if derived.read_bytes() != public_key.read_bytes():
            raise ValueError("Signing private key does not match the public key pinned in the repository")
        manifest_path = output_dir / "petcam-image-manifest.json"
        signature_path = output_dir / "petcam-image-manifest.json.sig"
        manifest = {
            "schema_version": 1, "application": "petcam", "version": version,
            "architecture": "arm64", "image_url": image_url,
            "image_size": size, "image_sha256": sha256(image),
        }
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\\n", encoding="utf-8")
        os.chmod(manifest_path, 0o644)
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private_key), "-rawin", "-in", str(manifest_path), "-out", str(signature_path)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key), "-rawin", "-in", str(manifest_path), "-sigfile", str(signature_path)], check=True, capture_output=True)
        os.chmod(signature_path, 0o644)
        return manifest_path, signature_path
    finally:
        derived.unlink(missing_ok=True)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image-url", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest, signature = create_signed_image_manifest(args.image, args.version, args.image_url, args.private_key, args.public_key, args.output_dir)
    print(f"Created {manifest}")
    print(f"Created {signature}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
