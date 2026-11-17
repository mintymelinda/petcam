from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "deploy/image"
STAGE = IMAGE / "stages/stage-petcam"


class RaspberryPiImageBuildTests(unittest.TestCase):
    def test_compose_uses_native_arm64_docker_assembly_without_version_file(self):
        compose = (IMAGE / "compose.yaml").read_text(encoding="utf-8")
        dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
        assembler = (IMAGE / "assemble.sh").read_text(encoding="utf-8")
        self.assertIn("platform: linux/arm64", compose)
        self.assertIn("deploy/image/Dockerfile", compose)
        self.assertIn("FROM debian:trixie-slim", dockerfile)
        self.assertIn("assemble-petcam", dockerfile)
        self.assertNotIn("COPY VERSION", dockerfile)
        self.assertNotIn("-C /workspace VERSION", assembler)

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

    def test_python_pip_manifest_is_explicitly_empty(self):
        manifest = (ROOT / "deploy/python/requirements.txt").read_text(encoding="utf-8")
        self.assertFalse(any(line.strip() and not line.lstrip().startswith("#") for line in manifest.splitlines()))

    def test_image_workflow_packages_latest_pi_gen_action_and_tracks_arm64_branch(self):
        workflow = (ROOT / ".github/workflows/image-build.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04-arm", workflow)
        self.assertIn("repository: usimd/pi-gen-action", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("path: .github/actions/pi-gen-action", workflow)
        self.assertIn("node-version: 24", workflow)
        self.assertIn("npm ci", workflow)
        self.assertIn("npm run package", workflow)
        self.assertIn("uses: ./.github/actions/pi-gen-action", workflow)
        self.assertIn("pi-gen-version: arm64", workflow)
        self.assertNotIn("d075c37c5eed90bf0325858ec2272e84200a5efe", workflow)
        self.assertIn("enable-pigen-cache: true", workflow)
        self.assertIn("cache-read-only: ${{ github.ref != 'refs/heads/main' }}", workflow)
        self.assertIn("extra-host-dependencies: git", workflow)
        self.assertIn("verbose-output: true", workflow)
        self.assertIn("enable-cloud-init: 1", workflow)
        self.assertIn("enable-ssh: 0", workflow)
        self.assertIn("password: ''", workflow)
        self.assertIn("disable-first-boot-user-rename: 0", workflow)
        self.assertIn("release: trixie", workflow)
        self.assertIn("stage0 stage1 stage2 ./deploy/image/stages/stage-petcam", workflow)
        self.assertIn("01-petcam/02-run-chroot.sh", workflow)

    def test_first_boot_wrapper_owns_device_specific_tls_initialization(self):
        start = (ROOT / "deploy/start.sh").read_text(encoding="utf-8")
        installer = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn("Generating the device HTTPS certificate", start)
        self.assertIn("deploy/start.sh", installer)
        self.assertIn("PETCAM_DEFER_TLS", installer)
