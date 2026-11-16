# Raspberry Pi OS image build

The image pipeline separates application assembly from operating-system customization:

1. Docker Compose builds a small ARM64 assembly container. It creates a portable source bundle; it does not build a second PetCam runtime image or install target OS packages.
2. The `usimd/pi-gen-action` workflow generates Raspberry Pi OS Trixie. The final custom pi-gen stage installs packages declared by the feature-owned `requirements.apt` manifests and places the source bundle at `/opt/petcam`.
3. The stage invokes the same `deploy/install.sh` used for an existing device, with flags that prevent apt operations or service startup inside the image-build chroot. Device-specific TLS credentials are generated on first boot.

## Build the runtime bundle locally on an ARM64 Docker host

```sh
docker compose -f deploy/image/compose.yaml run --build --rm assemble
```

The output is `deploy/image/dist/petcam-runtime.tar.gz`. The GitHub Actions workflow copies it into the custom stage before invoking pi-gen.

## Dependency ownership

- OS packages and Python modules supplied by Debian are declared in `deploy/features/*/requirements.apt`.
- `deploy/python/requirements.txt` is intentionally empty because the current application uses Python's standard library and OS-provided Python modules. The assembly step fails if pip requirements are added without a corresponding target-compatible offline wheelhouse implementation.
- No dependency installation is performed in the Docker assembly container. pi-gen installs target packages into the target root filesystem.

## Runtime behavior

- The Python supervisor remains the only PetCam process lifecycle manager.
- Cron is only the boot trigger. No PetCam systemd units or systemd service management are introduced.
- HTTPS key/certificate material is generated on the device's first boot, not baked into a reusable image.
- The existing source installer remains available for already-running Debian and Raspberry Pi OS installations.

## Image artifacts and releases

Pull request and main-branch builds upload a short-lived, unsigned GitHub Actions artifact for validation. This workflow does not publish GitHub Releases or distribute production images. The current `main` branch has no release-signing workflow or signing configuration; production signing and publication remain separate, explicit release operations.
