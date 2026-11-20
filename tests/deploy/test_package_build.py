from pathlib import Path
import os
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PetCamPackageBuildTests(unittest.TestCase):
    def test_build_produces_one_armhf_application_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            environment = os.environ.copy()
            environment["PETCAM_VERSION"] = "test-1.2.3"
            subprocess.run(
                ["bash", str(ROOT / "deploy/package/build.sh"), str(output)],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

            packages = list(output.glob("*"))
            self.assertEqual([path.name for path in packages], ["petcam-armhf.tar.gz"])
            with tarfile.open(packages[0], "r:gz") as archive:
                names = set(archive.getnames())
                self.assertIn("./install.sh", names)
                self.assertIn("./VERSION", names)
                self.assertIn("./src/petcam", names)
                self.assertIn("./deploy/install.sh", names)
                self.assertIn("./deploy/lib/platform.sh", names)
                self.assertNotIn("./deploy/image", names)
                self.assertFalse(any(name.startswith("./deploy/image/") for name in names))
                version = archive.extractfile("./VERSION")
                self.assertIsNotNone(version)
                self.assertEqual(version.read().decode().strip(), "test-1.2.3")

    def test_package_installer_validates_platform_before_copying_application(self):
        installer = (ROOT / "deploy/package/install.sh").read_text(encoding="utf-8")
        self.assertIn("validate_petcam_platform", installer)
        self.assertLess(
            installer.index("validate_petcam_platform"),
            installer.index('install -d -m 0755 "$INSTALL_ROOT"'),
        )
        self.assertIn('INSTALL_ROOT="${PETCAM_INSTALL_ROOT:-/opt/petcam}"', installer)
        self.assertIn('rm -rf "$INSTALL_ROOT/$item"', installer)
        self.assertIn('PETCAM_VERSION="$version" exec', installer)
        self.assertIn('exec /bin/bash "$INSTALL_ROOT/deploy/install.sh"', installer)
        self.assertIn('[[ "$PACKAGE_ROOT" != "$INSTALL_ROOT" ]]', installer)
        self.assertIn('for item in src deploy VERSION; do', installer)
        deployment = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ ! -e "$ETC_ROOT/petcam.conf" ]]; then', deployment)
        self.assertIn('if [[ ! -e "$STATE_ROOT/$feature/config.json" ]]; then', deployment)

    def test_package_builder_excludes_pi_gen_image_internals(self):
        builder = (ROOT / "deploy/package/build.sh").read_text(encoding="utf-8")
        self.assertIn('rm -rf "$STAGING/deploy/image"', builder)
        self.assertIn('PACKAGE="$OUTPUT_DIR/petcam-armhf.tar.gz"', builder)
        self.assertNotIn("arm64", builder.lower())


if __name__ == "__main__":
    unittest.main()
