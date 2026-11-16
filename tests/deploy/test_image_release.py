import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from create_image_release import create_signed_image_manifest


class SignedImageReleaseTests(unittest.TestCase):
    def test_manifest_is_bound_to_image_digest_and_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "petcam.img.xz"
            image.write_bytes(b"test compressed image")
            private, public = root / "private.pem", root / "public.pem"
            subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
            subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
            manifest_path, signature_path = create_signed_image_manifest(image, "1.2.3", "https://github.com/example/petcam/releases/download/v1.2.3/petcam-v1.2.3-arm64.img.xz", private, public, root / "assets")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["image_size"], image.stat().st_size)
            verified = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public), "-rawin", "-in", str(manifest_path), "-sigfile", str(signature_path)], capture_output=True)
            self.assertEqual(verified.returncode, 0)

    def test_rejects_mismatched_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "petcam.img.xz"
            image.write_bytes(b"test image")
            private, other, public = root / "private.pem", root / "other.pem", root / "public.pem"
            subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
            subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(other)], check=True, capture_output=True)
            subprocess.run(["openssl", "pkey", "-in", str(other), "-pubout", "-out", str(public)], check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, "does not match"):
                create_signed_image_manifest(image, "1.2.3", "https://example.com/image.img.xz", private, public, root / "assets")
