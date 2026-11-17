import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SignedImageReleaseWorkflowTests(unittest.TestCase):
    def test_production_signing_is_tag_only_and_fails_closed(self):
        workflow = (ROOT / ".github/workflows/image-build.yml").read_text(encoding="utf-8")
        self.assertIn('tags: ["v*"]', workflow)
        self.assertIn("publish-release:", workflow)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn(r'^v([0-9]+)\.([0-9]+)\.([0-9]+)$', workflow)
        self.assertIn('VERSION="${TAG#v}"', workflow)
        self.assertNotIn("VERSION file", workflow)
        self.assertNotIn("< VERSION", workflow)
        self.assertIn("PETCAM_UPDATE_SIGNING_PRIVATE_KEY: ${{ secrets.PETCAM_UPDATE_SIGNING_PRIVATE_KEY }}", workflow)
        self.assertIn("refusing to publish an unsigned image", workflow)
        self.assertIn('gh release edit "$TAG" --draft=false', workflow)

    def test_petcam_os_ed25519_public_key_is_pinned(self):
        key = (ROOT / "deploy/image/image-signing.pub").read_text(encoding="utf-8")
        self.assertIn("MCowBQYDK2VwAyEAlo1kjtAPdRsQPjbBiqFpp7czKWQwNRr3RRvMiT2N6WU=", key)
