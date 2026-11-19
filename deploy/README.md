# PetCam source deployment

PetCam runs directly from this checkout. There is no wheel build, package build,
or virtual environment.

## Install runtime dependencies

On Raspberry Pi OS / Debian, run the installer from the source checkout:

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

Keep the checkout at a stable path (the examples use /opt/petcam). The
installer creates /etc/petcam and /var/lib/petcam, copies defaults from
deploy/etc and deploy/var, and installs the device boot wrapper. To launch
manually:

```sh
PETCAM_ROOT=/opt/petcam /usr/local/sbin/petcam-start
```

The wrapper creates the HTTPS certificate for the device hostname when it is
first needed, then starts the Python supervisor. The supervisor launches the
always-on setup portal, RTSP server and sampler, and starts optional workers
only when their persisted feature settings enable them. It restarts failed
workers with bounded exponential backoff and writes its live process inventory
to /run/petcam/supervisor-status.json.

## Start at boot

The installer adds one root crontab @reboot entry that invokes the wrapper.
Cron is only the boot trigger; all PetCam process lifecycle, health and
optional-feature decisions belong to the Python supervisor.

The setup portal remains at https://<device-hostname>:8443/. The full manager
is disabled by default and can be enabled from the setup portal.

## Prebuilt Raspberry Pi image

See [the Raspberry Pi image build](image/README.md) for the Docker Compose +
pi-gen pipeline. It builds one Raspberry Pi OS Trixie 32-bit ARMHF image for supported Raspberry Pi models, with PetCam installed
at /opt/petcam, while keeping this source-based installer usable on existing
devices.
