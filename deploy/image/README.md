# Raspberry Pi OS image build

Docker Compose assembles a portable PetCam source bundle. The image workflow builds **one Raspberry Pi OS Trixie 32-bit ARMHF image** using the upstream `RPi-Distro/pi-gen` project, then uses a thin custom stage to install feature-owned OS packages and place PetCam at `/opt/petcam`.

- **One 32-bit ARMHF image:** built from pi-gen's `master` branch and intended for every Raspberry Pi generation supported by Raspberry Pi OS 32-bit, from the original Raspberry Pi 1 and Zero (ARMv6) through Raspberry Pi 5, including Zero 2 W, Pi 400, and Compute Modules.

This is one image, not separate architecture-specific downloads. Raspberry Pi OS 32-bit uses the ARMHF/Raspbian userspace needed by original ARMv6 boards while remaining supported on newer Pi models. The image does not require Docker on the device. The existing source installer remains usable on already-running Debian and Raspberry Pi OS systems.

## Raspberry Pi Imager preconfiguration

The image build enables pi-gen's cloud-init and Netplan integration. This provides the NoCloud boot-partition seed that Raspberry Pi Imager uses to apply pre-flash OS customisation on first boot.

Every tagged image release includes `petcam-imager.json`, a Raspberry Pi Imager repository manifest declaring `init_format: "cloudinit"`. It includes verified compressed and extracted image sizes and SHA-256 hashes for the download. The stable manifest URL is:

```text
https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

In Raspberry Pi Imager 2.x, open App Options / Content Repository, choose a custom repository JSON URL, and paste the URL above. Imager shows one 32-bit PetCam OS choice for supported Pi models and offers its cloud-init customisation flow for hostname, user credentials, Wi-Fi, locale and SSH.

You can also launch Imager with the repository directly:

```sh
rpi-imager --repo https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

The manifest maps the image to Raspberry Pi Imager's 32-bit device tags: `pi5-32bit`, `pi4-32bit`, `pi3-32bit`, `pi2-32bit`, `pi1-32bit`, and `pizero-32bit`. This includes Pi 5 / 500 / CM5, Pi 4 / 400 / CM4, Pi 3 / Zero 2 W / CM3, Pi 2, Pi 1 / CM1, and Zero / Zero W / Zero WH. This is the generic `cloudinit` format, not `cloudinit-rpi`: it does not advertise Raspberry Pi-specific hardware toggles that have not been configured and tested in the PetCam image.

## Build target and stage ordering

The workflow builds the single ARMHF target on an x86-64 GitHub-hosted runner. pi-gen's build container is i386, so using an x86-64 runner avoids the execution-format failure encountered on ARM64 runners; pi-gen's `master` branch selects the 32-bit ARMHF target. The GitHub Actions host runner architecture does not determine the target image architecture.

The PetCam stage intentionally remains **after** `stage0 stage1 stage2`. Those upstream OS stages are the expensive, relatively stable part of the build. PetCam's bundle and package manifest change more frequently, so keeping the custom stage last isolates those changes and preserves the reusable upstream work.

The image uses the Raspbian archive at `http://archive.raspbian.org/raspbian/` for base-system packages. The pre-stage configures APT retries and timeouts before the first package-index update. The Raspberry Pi OS repository at `archive.raspberrypi.com` is left unchanged.

The image build downloads APT packages directly from the configured repositories. It deliberately does not route package downloads through a self-hosted or ephemeral APT proxy: a proxy outage must not prevent a clean image build. The final `.xz` image uses compression level 1 rather than the action's slower default level 6; image integrity is checked with `xz -t`. Artifact upload uses compression level 0 because recompressing an already-compressed `.xz` file adds CPU time with negligible size reduction.

## Upstream build updates

The workflow checks out the latest `main` branch of `usimd/pi-gen-action` for every build, then installs its locked Node dependencies and packages its TypeScript source into the `dist/index.js` entrypoint required by GitHub Actions. This is necessary because the upstream source branch does not commit the generated `dist` bundle. It means we follow current action source without pinning a commit or release, while still producing the executable artifact the Actions runner expects.

The action checks out the `master` branch of `RPi-Distro/pi-gen`, which builds the 32-bit ARMHF image. This intentionally uses the 32-bit base for broad backward compatibility rather than producing a second 64-bit image.

This deliberately favors upstream freshness over immutable action references. A change to the action's default branch can affect the next PetCam build, so the image build must pass validation before its artifact can be released. The action's branch is not a substitute for keeping the Trixie APT package sources current: installed kernel and OS package versions are resolved from the repositories used by pi-gen during the build.

Git is explicitly installed as a host dependency for pi-gen's build tooling; the pi-gen Docker builder also installs Git in its own image.

## Production image releases

Production releases are published only from `vMAJOR.MINOR.PATCH` tags. The Git tag is validated and used to name the release and the single image asset:

- `petcam-VERSION-32bit.img.xz` and its SHA-256 checksum.
- `petcam-imager.json`, containing the matching install choice and image integrity metadata.

The image build must complete and pass validation before the draft GitHub Release is published. No OTA signing keys, signed update manifests, or public signing keys are required.
