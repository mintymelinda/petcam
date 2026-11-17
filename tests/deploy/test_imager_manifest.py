import hashlib
import lzma
import tempfile
import unittest
from pathlib import Path

from tools.create_imager_manifest import create_manifest


class ImagerManifestTests(unittest.TestCase):
    def test_manifest_describes_cloud_init_customisation_and_image_integrity(self):
        image = b"petcam-image-content" * 128
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "petcam.img.xz"
            compressed = lzma.compress(image)
            image_path.write_bytes(compressed)
            manifest = create_manifest(
                image_path,
                "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam-v1.2.3-arm64.img.xz",
                "2026-11-17",
            )

        self.assertEqual(manifest["imager"]["devices"][0]["tags"], ["pi4"])
        self.assertEqual(manifest["imager"]["devices"][1]["tags"], ["pi5"])
        entry = manifest["os_list"][0]
        self.assertEqual(entry["init_format"], "cloudinit")
        self.assertTrue(
            {
                "name",
                "description",
                "icon",
                "url",
                "extract_size",
                "extract_sha256",
                "image_download_size",
                "image_download_sha256",
                "release_date",
                "devices",
            }.issubset(entry)
        )
        self.assertEqual(entry["devices"], ["pi4", "pi5"])
        self.assertEqual(entry["extract_size"], len(image))
        self.assertEqual(entry["extract_sha256"], hashlib.sha256(image).hexdigest())
        self.assertEqual(
            entry["image_download_sha256"], hashlib.sha256(compressed).hexdigest()
        )
        self.assertEqual(entry["image_download_size"], len(compressed))
        self.assertEqual(entry["release_date"], "2026-11-17")

    def test_manifest_rejects_non_http_image_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "petcam.img"
            image_path.write_bytes(b"image")
            with self.assertRaises(ValueError):
                create_manifest(image_path, "file:///tmp/petcam.img", "2026-11-17")

    def test_manifest_rejects_invalid_release_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "petcam.img"
            image_path.write_bytes(b"image")
            with self.assertRaises(ValueError):
                create_manifest(image_path, "https://example.com/petcam.img", "not-a-date")


if __name__ == "__main__":
    unittest.main()
