import hashlib
import lzma
import tempfile
import unittest
from pathlib import Path

from tools.create_imager_manifest import DEVICE_PROFILES, create_manifest


class ImagerManifestTests(unittest.TestCase):
    def test_manifest_contains_one_32bit_image_for_every_pi_generation(self):
        image = b"petcam-32bit-image-content" * 128
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "petcam-32bit.img.xz"
            compressed = lzma.compress(image)
            image_path.write_bytes(compressed)
            manifest = create_manifest(
                image_path,
                "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam-v1.2.3-32bit.img.xz",
                "2026-11-17",
            )

        devices = manifest["imager"]["devices"]
        self.assertEqual(
            [(device["name"], device["tags"], device["architecture"]) for device in devices],
            [
                ("Raspberry Pi 5", ["pi5-32bit"], "armhf"),
                ("Raspberry Pi 4", ["pi4-32bit"], "armhf"),
                ("Raspberry Pi 3", ["pi3-32bit"], "armhf"),
                ("Raspberry Pi 2", ["pi2-32bit"], "armhf"),
                ("Raspberry Pi 1", ["pi1-32bit"], "armhf"),
                ("Raspberry Pi Zero", ["pizero-32bit"], "armhf"),
            ],
        )
        self.assertEqual(len(manifest["os_list"]), 1)
        entry = manifest["os_list"][0]
        self.assertEqual(entry["name"], "PetCam OS (32-bit)")
        self.assertEqual(entry["architecture"], "armhf")
        self.assertEqual(
            entry["devices"],
            ["pi5-32bit", "pi4-32bit", "pi3-32bit", "pi2-32bit", "pi1-32bit", "pizero-32bit"],
        )
        self.assertTrue(entry["description"].startswith("One 32-bit ARMHF"))
        self.assertEqual(entry["url"].split("-")[-1], "32bit.img.xz")
        self.assertEqual(entry["extract_size"], len(image))
        self.assertEqual(entry["extract_sha256"], hashlib.sha256(image).hexdigest())
        self.assertEqual(entry["image_download_sha256"], hashlib.sha256(compressed).hexdigest())
        self.assertEqual(entry["image_download_size"], len(compressed))
        self.assertEqual(entry["release_date"], "2026-11-17")
        self.assertEqual(entry["init_format"], "cloudinit")
        self.assertEqual(DEVICE_PROFILES, devices)

    def test_manifest_rejects_non_http_image_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "image.img"
            image_path.write_bytes(b"image")
            with self.assertRaises(ValueError):
                create_manifest(image_path, "file:///tmp/image.img", "2026-11-17")

    def test_manifest_rejects_invalid_release_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "image.img"
            image_path.write_bytes(b"image")
            with self.assertRaises(ValueError):
                create_manifest(image_path, "https://example.com/image.img", "not-a-date")


if __name__ == "__main__":
    unittest.main()
