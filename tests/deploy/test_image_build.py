from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PetCamImageBuildTests(unittest.TestCase):
    def test_image_customizer_uses_verified_official_prebuilt_image(self):
        builder = (ROOT / "deploy/image/build.sh").read_text(encoding="utf-8")
        self.assertIn("https://downloads.raspberrypi.com/raspios_lite_armhf_latest", builder)
        self.assertIn('"${RASPIOS_IMAGE_URL}.sha256"', builder)
        self.assertIn("sha256sum --check --status", builder)
        self.assertIn('truncate -s +2G "$BASE_IMAGE"', builder)
        self.assertIn('parted --script "$BASE_IMAGE" resizepart 2 100%', builder)
        self.assertIn('e2fsck -f -p "${LOOP_DEVICE}p2"', builder)\n        self.assertIn('(( FSCK_STATUS <= 1 ))', builder)\n        self.assertIn('resize2fs "${LOOP_DEVICE}p2"', builder)
        self.assertIn('losetup --find --show --partscan "$BASE_IMAGE"', builder)
        self.assertIn('mount "${LOOP_DEVICE}p2" "$ROOTFS"', builder)
        self.assertIn('mount "${LOOP_DEVICE}p1" "$BOOT_MOUNT"', builder)
        self.assertIn("qemu-arm-static", builder)
        self.assertIn('chroot "$ROOTFS" /bin/bash', builder)
        self.assertIn("PETCAM_CPUINFO_FILE=/tmp/petcam-build-cpuinfo", builder)
        self.assertIn('touch "$BOOT_MOUNT/ssh"', builder)
        self.assertIn('FINAL_IMAGE="$OUTPUT_DIR/petcam-$VERSION-raspios-lite-armhf.img.xz"', builder)
        self.assertNotIn("pi-gen", builder)
        self.assertNotIn("docker", builder.lower())
        self.assertNotIn("build-docker.sh", builder)

    def test_image_customizer_installs_the_standalone_package_without_baking_device_identity(self):
        builder = (ROOT / "deploy/image/build.sh").read_text(encoding="utf-8")
        installer = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        package_builder = (ROOT / "deploy/package/build.sh").read_text(encoding="utf-8")
        self.assertIn('tar -xzf "$PACKAGE" -C "$ROOTFS/tmp/petcam-armhf-installer"', builder)
        self.assertIn("PETCAM_INSTALL_ROOT=/opt/petcam", builder)
        self.assertIn("PETCAM_SKIP_SERVICE_START=1", builder)
        self.assertIn("PETCAM_DEFER_INITIALIZE=1", builder)
        self.assertIn("Deferring certificate initialization until the device boots", installer)
        self.assertIn("Deferring cron startup until the image boots", installer)
        self.assertIn('rm -rf "$STAGING/deploy/image"', package_builder)

    def test_release_image_is_tag_only_and_published_with_checksum(self):
        workflow = (ROOT / ".github/workflows/package-build.yml").read_text(encoding="utf-8")
        self.assertIn("build-image:", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("needs: [build-package, build-image]", workflow)
        self.assertIn("qemu-user-static", workflow)
        self.assertIn("update-binfmts --enable qemu-arm", workflow)
        self.assertIn("sudo bash deploy/image/build.sh", workflow)
        self.assertIn("*.img.xz.sha256", workflow)
        self.assertIn('(cd dist && sha256sum "$IMAGE_NAME" > "$IMAGE_NAME.sha256")', workflow)
        self.assertIn("for REQUIRED_ASSET in", workflow)
        self.assertIn("tests.deploy.test_image_build", workflow)


if __name__ == "__main__":
    unittest.main()
