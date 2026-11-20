from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
class PetCamImageBuildTests(unittest.TestCase):
    def test_image_builder_pins_official_pi_gen_and_builds_lite_armhf(self):
        builder = (ROOT / "deploy/image/build.sh").read_text(encoding="utf-8")
        self.assertIn("https://github.com/RPi-Distro/pi-gen.git", builder)
        self.assertRegex(builder, r'PI_GEN_REF="[0-9a-f]{40}"')
        self.assertIn('RELEASE="trixie"', builder)
        self.assertIn('DEPLOY_COMPRESSION="xz"', builder)
        self.assertIn('STAGE_LIST="stage0 stage1 stage2 stage-petcam"', builder)
        self.assertIn('FIRST_USER_NAME="pi"', builder)
        self.assertIn("./build-docker.sh", builder)
        self.assertIn("raspios-lite-armhf.img.xz", builder)
        self.assertIn('touch "$PI_GEN_DIR/stage2/SKIP_IMAGES"', builder)
        self.assertNotIn("arm64", builder.lower())
    def test_image_stage_installs_package_and_defers_device_specific_setup(self):
        stage = ROOT / "deploy/image/stage-petcam/00-install-petcam"
        host = (stage / "00-run.sh").read_text(encoding="utf-8")
        chroot = (stage / "00-run-chroot.sh").read_text(encoding="utf-8")
        installer = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn("petcam-armhf.tar.gz", host)
        self.assertIn('tar -xzf "$PACKAGE"', chroot)
        self.assertIn("PETCAM_INSTALL_ROOT=/opt/petcam", chroot)
        self.assertIn("PETCAM_SKIP_SERVICE_START=1", chroot)
        self.assertIn("PETCAM_DEFER_INITIALIZE=1", chroot)
        self.assertTrue((ROOT / "deploy/image/stage-petcam/prerun.sh").is_file())
        self.assertTrue((ROOT / "deploy/image/stage-petcam/EXPORT_IMAGE").is_file())
        self.assertIn("Deferring cron startup until the image boots", installer)
        self.assertIn("Deferring certificate initialization until the device boots", installer)
    def test_release_image_is_tag_only_and_required_before_publishing(self):
        workflow = (ROOT / ".github/workflows/package-build.yml").read_text(encoding="utf-8")
        self.assertIn("build-image:", workflow)
        self.assertIn("needs: [build-package, build-image]", workflow)
        self.assertIn("github.sha", workflow)
        self.assertIn("*.img.xz.sha256", workflow)
        self.assertIn('(cd dist && sha256sum "$IMAGE_NAME" > "$IMAGE_NAME.sha256")', workflow)
        self.assertIn("for REQUIRED_ASSET in", workflow)
        self.assertIn("tests.deploy.test_image_build", workflow)
if __name__ == "__main__":
    unittest.main()
