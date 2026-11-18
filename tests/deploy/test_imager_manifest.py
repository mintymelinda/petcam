import hashlib
import lzma
import tempfile
import unittest
from pathlib import Path

from tools.create_imager_manifest import create_manifest


class ImagerManifestTests(unittest.TestCase):
    def test_manifest_includes_armhf_zero_w_and_arm64_pi4_pi5_images(self):
        armhf_image = b"petcam-armhf-image-content" * 128
        arm64_image = b"petcam-arm64-image-content" * 128
        with tempfile.TemporaryDirectory() as directory:
            armhf_path = Path(directory) / "petcam-armhf.img.xz"
            arm64_path = Path(directory) / "petcam-arm64.img.xz"
            armhf_compressed = lzma.compress(armhf_image)
            arm64_compressed = lzma.compress(arm64_image)
            armhf_path.write_bytes(armhf_compressed)
            arm64_path.write_bytes(arm64_compressed)
            manifest = create_manifest(
                armhf_path,
                "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam-v1.2.3-armhf.img.xz",
                arm64_path,
                "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam-v1.2.3-arm64.img.xz",
                "2026-11-17",
            )

        devices = manifest["imager"]["devices"]
        self.assertEqual(
            [(device["name"], device["tags"], device["architecture"]) for device in devices],
            [
                ("Raspberry Pi Zero W", ["pizero-32bit"], "armhf"),
                ("Raspberry Pi 4", ["pi4"], "armv8"),
                ("Raspberry Pi 5", ["pi5"], "armv8"),
            ],
        )

        armhf_entry, arm64_entry = manifest["os_list"]
        self.assertEqual(armhf_entry["name"], "PetCam OS (32-bit)")
        self.assertEqual(armhf_entry["architecture"], "armhf")
        self.assertEqual(armhf_entry["devices"], ["pizero-32bit"])
        self.assertEqual(armhf_entry["url"].split("-")[-1], "armhf.img.xz")
        self.assertEqual(armhf_entry["extract_size"], len(armhf_image))
        self.assertEqual(
            armhf_entry["extract_sha256"], hashlib.sha256(armhf_image).hexdigest()
        )
        self.assertEqual(
            armhf_entry["image_download_sha256"],
            hashlib.sha256(armhf_compressed).hexdigest(),
        )
        self.assertEqual(armhf_entry["image_download_size"], len(armhf_compressed))

        self.assertEqual(arm64_entry["name"], "PetCam OS (64-bit)")
        self.assertEqual(arm64_entry["architecture"], "armv8")
        self.assertEqual(arm64_entry["devices"], ["pi4", "pi5"])
        self.assertEqual(arm64_entry["url"].split("-")[-1], "arm64.img.xz")
        self.assertEqual(arm64_entry["extract_size"], len(arm64_image))
        self.assertEqual(
            arm64_entry["extract_sha256"], hashlib.sha256(arm64_image).hexdigest()
        )
        self.assertEqual(
            arm64_entry["image_download_sha256"],
            hashlib.sha256(arm64_compressed).hexdigest(),
        )
        self.assertEqual(arm64_entry["image_download_size"], len(arm64_compressed))
        self.assertEqual(armhf_entry["release_date"], "2026-11-17")
        self.assertEqual(arm64_entry["release_date"], "2026-11-17")
        self.assertEqual(armhf_entry["init_format"], "cloudinit")
        self.assertEqual(arm64_entry["init_format"], "cloudinit")

    def test_manifest_rejects_non_http_image_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            armhf_path = Path(directory) / "armhf.img"
            arm64_path = Path(directory) / "arm64.img"
            armhf_path.write_bytes(b"armhf")
            arm64_path.write_bytes(b"arm64")
            with self.assertRaises(ValueError):
                create_manifest(
                    armhf_path,
                    "file:///tmp/armhf.img",
                    arm64_path,
                    "https://example.com/arm64.img",
                    "2026-11-17",
                )

    def test_manifest_rejects_invalid_release_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            armhf_path = Path(directory) / "armhf.img"
            arm64_path = Path(directory) / "arm64.img"
            armhf_path.write_bytes(b"armhf")
            arm64_path.write_bytes(b"arm64")
            with self.assertRaises(ValueError):
                create_manifest(
                    armhf_path,
                    "https://example.com/armhf.img",
                    arm64_path,
                    "https://example.com/arm64.img",
                    "not-a-date",
                )


if __name__ == "__main__":
    unittest.main()
