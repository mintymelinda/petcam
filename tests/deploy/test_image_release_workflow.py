from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ImageReleaseWorkflowTests(unittest.TestCase):
    def test_production_image_release_is_tag_only_and_does_not_require_signing(self):
        workflow = (ROOT / ".github/workflows/image-build.yml").read_text(encoding="utf-8")
        self.assertIn('tags: ["v*"]', workflow)
        self.assertIn("publish-release:", workflow)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn(r'^v([0-9]+)\\.([0-9]+)\\.([0-9]+)$', workflow)
        self.assertIn('VERSION="${TAG#v}"', workflow)
        self.assertIn("sha256sum", workflow)
        self.assertIn('gh release edit "$TAG" --draft=false', workflow)
        self.assertNotIn("PETCAM_UPDATE_SIGNING_PRIVATE_KEY", workflow)
        self.assertNotIn("image-signing.pub", workflow)
        self.assertNotIn("create_image_release.py", workflow)
        self.assertNotIn("manifest.json.sig", workflow)

    def test_release_documentation_describes_unsigned_image_and_checksum(self):
        docs = (ROOT / "deploy/image/README.md").read_text(encoding="utf-8")
        self.assertIn("SHA-256 checksum", docs)
        self.assertNotIn("signing key", docs.lower())
        self.assertNotIn("signed manifest", docs.lower())
