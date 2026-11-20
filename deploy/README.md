# PetCam deployment

PetCam is deployed as an application on the official Raspberry Pi OS Lite
(32-bit) installation. The release package is the primary installation path;
the source installer remains available for development and local checkouts.

## Install the release package

See [ARMHF package installation](package/README.md) for the full process:

1. Flash official Raspberry Pi OS Lite (32-bit) with Raspberry Pi Imager.
2. Complete normal OS first-boot configuration.
3. Download the single `petcam-armhf.tar.gz` package from the latest release.
4. Extract the package and run `sudo ./install.sh`.

The package installer verifies 32-bit ARMHF userspace and an ARMv6-or-newer
CPU, then installs feature-owned APT dependencies and the PetCam runtime.
The original Pi Zero W is the baseline target; newer Raspberry Pi models use
the same package when running the 32-bit OS. No ARM64 package or custom
PetCam OS image is part of the deployment contract.

## Install from source

PetCam runs directly from a source checkout. There is no wheel build, package
build, or virtual environment required for this development path.

On Raspberry Pi OS / Debian ARMHF, run the installer from the source checkout:

```sh
sudo ./deploy/install.sh
```

The installer discovers `deploy/features/*/requirements.apt` manifests,
validates package names, deduplicates packages across features, and installs
the combined set. It does not contain a hand-maintained feature package list.

### Adding a feature dependency

Create a manifest alongside the feature:

```text
deploy/features/<feature-name>/requirements.apt
```

Declare one Debian package name per line. Blank lines and lines beginning
with `#` are ignored. Repeated packages across manifests are installed only
once. The installer discovers new feature manifests automatically; adding or
changing a dependency does not require modifying `deploy/install.sh`.

Feature-specific runtime configuration and enablement remain separate from
dependency installation. The installer installs the dependencies declared by
all features; the supervisor starts optional workers only when their persisted
feature settings enable them.

## Configure and launch

The installer creates `/etc/petcam` and `/var/lib/petcam`, copies defaults
only when a file does not already exist, and installs the device boot wrapper.
To launch manually:

```sh
PETCAM_ROOT=/opt/petcam /usr/local/sbin/petcam-start
```

The wrapper creates the HTTPS certificate for the device hostname when it is
first needed, then starts the Python supervisor. The supervisor launches the
always-on setup portal, RTSP server and sampler, and starts optional workers
only when their persisted feature settings enable them. It restarts failed
workers with bounded exponential backoff and writes its live process inventory
to `/run/petcam/supervisor-status.json`.

The setup portal remains at `https://<device-hostname>:8443/`. The full
manager is disabled by default and can be enabled from the setup portal.

## Package build

From a source checkout, run:

```sh
PETCAM_VERSION=1.2.3 deploy/package/build.sh dist
```

This creates the single `dist/petcam-armhf.tar.gz` release package. The
archive contains PetCam's runtime and installer, not an operating-system
image. Native dependencies are resolved on the target using the OS package
repositories.
