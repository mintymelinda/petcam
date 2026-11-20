import hashlib
import json
import lzma
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from deploy.image.create_imager_manifest import create_manifest, resolve_source_filename


class Response:
    def __init__(
        self,
        payload,
        url="https://downloads.raspberrypi.com/raspios_lite_armhf/images/test/raspios-lite-armhf.img.xz",
    ):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, *_args):
        return self.payload


class ImagerManifestTests(unittest.TestCase):
    def test_source_url_resolution_falls_back_when_head_is_unsupported(self):
        with patch(
            "deploy.image.create_imager_manifest.urlopen",
            side_effect=[URLError("HEAD unsupported"), Response(b"")],
        ) as open_url:
            filename = resolve_source_filename("https://downloads.raspberrypi.com/raspios_lite_armhf_latest")
        self.assertEqual(filename, "raspios-lite-armhf.img.xz")
        self.assertEqual(open_url.call_count, 2)

    def test_release_workflow_publishes_the_manifest_json(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/package-build.yml").read_text(encoding="utf-8")
        self.assertIn("tests.deploy.test_imager_manifest", workflow)
        self.assertIn("petcam.rpi-imager-manifest.json", workflow)
        self.assertIn('--image-url "$IMAGE_URL"', workflow)
        self.assertIn("petcam.rpi-imager-manifest.json --clobber", workflow)
        self.assertNotIn("create_imager_manifest.py --clobber", workflow)

    def test_manifest_points_to_release_image_and_preserves_upstream_customization_metadata(self):
        disk_image = b"test disk image bytes"
        compressed = lzma.compress(disk_image)
        repository = {
            "imager": {"devices": [
                {"name": "Pi Zero", "description": "Zero family", "tags": ["pi0"]},
                {"name": "Pi 4", "description": "Pi 4", "tags": ["pi4"]},
            ]},
            "os_list": [{ 
                "name": "Raspberry Pi OS Lite (32-bit)",
                "url": "https://downloads.raspberrypi.com/raspios_lite_armhf/images/test/raspios-lite-armhf.img.xz",
                "init_format": "cloudinit-rpi",
                "devices": ["pi0"],
                "icon": "https://example.invalid/raspios.png",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "petcam-v1.2.3-raspios-lite-armhf.img.xz"
            output = Path(directory) / "petcam.rpi-imager-manifest"
            image.write_bytes(compressed)
            with patch(
                "deploy.image.create_imager_manifest.urlopen",
                side_effect=[Response(b""), Response(json.dumps(repository).encode())],
            ):
                create_manifest(
                    image,
                    output,
                    "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam.img.xz",
                    "https://downloads.raspberrypi.com/raspios_lite_armhf_latest",
                    "https://example.invalid/os.json",
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            entry = manifest["os_list"][0]
            self.assertEqual(entry["init_format"], "cloudinit-rpi")
            self.assertEqual(
                entry["url"],
                "https://github.com/mintymelinda/petcam/releases/download/v1.2.3/petcam.img.xz",
            )
            self.assertEqual(entry["image_download_size"], len(compressed))
            self.assertEqual(entry["image_download_sha256"], hashlib.sha256(compressed).hexdigest())
            self.assertEqual(entry["extract_size"], len(disk_image))
            self.assertEqual(entry["extract_sha256"], hashlib.sha256(disk_image).hexdigest())
            self.assertEqual(manifest["imager"]["devices"][0]["name"], "Pi Zero")
            self.assertEqual(len(manifest["imager"]["devices"]), 1)


if __name__ == "__main__":
    unittest.main()
