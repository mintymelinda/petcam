from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "deploy/image"
STAGE = IMAGE / "stages/stage-petcam"


class RaspberryPiImageBuildTests(unittest.TestCase):
    def test_runtime_assembly_is_portable_and_does_not_pin_target_architecture(self):
        compose = (IMAGE / "compose.yaml").read_text(encoding="utf-8")
        dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
        assembler = (IMAGE / "assemble.sh").read_text(encoding="utf-8")
        self.assertNotIn("platform:", compose)
        self.assertIn("deploy/image/Dockerfile", compose)
        self.assertIn("FROM debian:trixie-slim", dockerfile)
        self.assertIn("assemble-petcam", dockerfile)
        self.assertIn("ARG PETCAM_VERSION=unknown", dockerfile)
        self.assertIn("/workspace/VERSION", dockerfile)
        self.assertIn("-C /workspace VERSION", assembler)
        self.assertIn("PETCAM_VERSION:", compose)

    def test_pi_gen_stage_installs_packages_before_runtime_configuration(self):
        package_dir = STAGE / "01-petcam"
        run = (package_dir / "00-run.sh").read_text(encoding="utf-8")
        chroot = (package_dir / "02-run-chroot.sh").read_text(encoding="utf-8")
        self.assertIn("ROOTFS_DIR/opt/petcam", run)
        self.assertIn("bash deploy/install.sh", chroot)
        self.assertIn("PETCAM_SKIP_DEPENDENCIES=1", chroot)
        self.assertIn("PETCAM_SKIP_SERVICE_START=1", chroot)
        self.assertIn("PETCAM_DEFER_TLS=1", chroot)
        self.assertTrue((package_dir / "01-packages").is_file())
        self.assertLess("01-packages", "02-run-chroot.sh")


    def test_pi_gen_apt_mirror_stage_pins_raspbian_and_adds_retries(self):
        import os
        import subprocess
        import tempfile

        stage_script = IMAGE / "stages/stage-petcam-apt-mirror/prerun.sh"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            apt_dir = base / "stage0/00-configure-apt"
            files_dir = apt_dir / "files"
            files_dir.mkdir(parents=True)
            bootstrap = base / "stage0/prerun.sh"
            bootstrap.write_text(
                'bootstrap trixie "${ROOTFS_DIR}" '
                "http://raspbian.raspberrypi.com/raspbian/\n",
                encoding="utf-8",
            )
            sources = files_dir / "raspbian.sources"
            sources.write_text(
                "URIs: http://raspbian.raspberrypi.com/raspbian/\n",
                encoding="utf-8",
            )
            apt_run = apt_dir / "00-run.sh"
            apt_run.write_text(
                "#!/bin/bash -e\non_chroot <<- \\EOF\napt-get update\nEOF\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["BASE_DIR"] = str(base)
            subprocess.run(["bash", str(stage_script)], env=env, check=True)
            bootstrap_text = bootstrap.read_text(encoding="utf-8")
            sources_text = sources.read_text(encoding="utf-8")
            apt_text = apt_run.read_text(encoding="utf-8")
            self.assertNotIn("raspbian.raspberrypi.com", bootstrap_text)
            self.assertNotIn("raspbian.raspberrypi.com", sources_text)
            self.assertIn("http://archive.raspbian.org/raspbian/", bootstrap_text)
            self.assertIn("http://archive.raspbian.org/raspbian/", sources_text)
            self.assertIn('Acquire::Retries "5";', apt_text)
            self.assertIn('Acquire::http::Timeout "30";', apt_text)
            self.assertEqual(apt_text.count("80-petcam-network-retries"), 1)

            subprocess.run(["bash", str(stage_script)], env=env, check=True)
            self.assertEqual(
                apt_run.read_text(encoding="utf-8").count("80-petcam-network-retries"),
                1,
            )

    def test_pi_gen_apt_mirror_stage_leaves_arm64_debian_sources_unchanged(self):
        import os
        import subprocess
        import tempfile

        stage_script = IMAGE / "stages/stage-petcam-apt-mirror/prerun.sh"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            apt_dir = base / "stage0/00-configure-apt"
            files_dir = apt_dir / "files"
            files_dir.mkdir(parents=True)
            bootstrap = base / "stage0/prerun.sh"
            bootstrap.write_text(
                'bootstrap trixie "${ROOTFS_DIR}" http://deb.debian.org/debian/\n',
                encoding="utf-8",
            )
            sources = files_dir / "debian.sources"
            sources.write_text(
                "URIs: http://deb.debian.org/debian/\n",
                encoding="utf-8",
            )
            apt_run = apt_dir / "00-run.sh"
            apt_run.write_text(
                "#!/bin/bash -e\non_chroot <<- \\EOF\napt-get update\nEOF\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["BASE_DIR"] = str(base)
            subprocess.run(["bash", str(stage_script)], env=env, check=True)
            self.assertIn("http://deb.debian.org/debian/", bootstrap.read_text(encoding="utf-8"))
            self.assertIn("http://deb.debian.org/debian/", sources.read_text(encoding="utf-8"))
            self.assertIn("80-petcam-network-retries", apt_run.read_text(encoding="utf-8"))

    def test_python_pip_manifest_is_explicitly_empty(self):
        manifest = (ROOT / "deploy/python/requirements.txt").read_text(encoding="utf-8")
        self.assertFalse(any(line.strip() and not line.lstrip().startswith("#") for line in manifest.splitlines()))

    def test_image_workflow_builds_one_32bit_armhf_target_for_all_pis(self):
        workflow = (ROOT / ".github/workflows/image-build.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("pi-gen master builds the single 32-bit ARMHF image", workflow)
        self.assertIn("pi-gen-version: master", workflow)
        self.assertIn("petcam-image-32bit-${{ github.sha }}", workflow)
        self.assertIn("uses: ./.github/actions/pi-gen-action", workflow)
        self.assertNotIn("matrix:", workflow)
        self.assertNotIn("arm64", workflow)
        self.assertNotIn("pi-gen-version: arm64", workflow)
        self.assertNotIn("petcam-image-arm64", workflow)
        self.assertIn("compression-level: 1", workflow)
        self.assertIn("compression-level: 0", workflow)
        self.assertIn("release: trixie", workflow)
        self.assertIn("./deploy/image/stages/stage-petcam-apt-mirror stage0 stage1 stage2", workflow)
        self.assertIn("petcam-${TAG}-32bit.img.xz", workflow)
        self.assertIn('--image "$IMAGE_NAME"', workflow)
    def test_first_boot_wrapper_owns_device_specific_tls_initialization(self):
        start = (ROOT / "deploy/start.sh").read_text(encoding="utf-8")
        installer = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn("Generating the device HTTPS certificate", start)
        self.assertIn("deploy/start.sh", installer)
        self.assertIn("PETCAM_DEFER_TLS", installer)
