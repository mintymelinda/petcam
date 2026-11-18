# Raspberry Pi OS image build

Docker Compose assembles a portable PetCam source bundle. The image workflow builds **two Raspberry Pi OS Trixie images** using the upstream `RPi-Distro/pi-gen` project, then uses a thin custom stage to install feature-owned OS packages and place PetCam at `/opt/petcam`:

- **32-bit ARMHF:** built from pi-gen's `master` branch and compatible with the original Raspberry Pi Zero W (ARMv6).
- **64-bit ARM64:** built from pi-gen's `arm64` branch and retains support for Raspberry Pi 4 and Raspberry Pi 5.

These are separate images, not one image that attempts to support every CPU architecture. Neither image requires Docker on the device. The existing source installer remains usable on already-running Debian and Raspberry Pi OS systems.

## Raspberry Pi Imager preconfiguration

The image builds enable pi-gen's cloud-init and Netplan integration. This provides the NoCloud boot-partition seed that Raspberry Pi Imager uses to apply pre-flash OS customisation on first boot.

Every tagged image release includes `petcam-imager.json`, a Raspberry Pi Imager repository manifest declaring `init_format: "cloudinit"`. It includes verified compressed and extracted image sizes and SHA-256 hashes for both architecture-specific downloads. The stable manifest URL is:

```text
https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

In Raspberry Pi Imager 2.x, open App Options / Content Repository, choose a custom repository JSON URL, and paste the URL above. Imager will show separate 32-bit and 64-bit PetCam OS choices, matched to their supported devices, and offer its cloud-init customisation flow for hostname, user credentials, Wi-Fi, locale and SSH.

You can also launch Imager with the repository directly:

```sh
rpi-imager --repo https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

The manifest advertises the original Zero W with the `pizero-32bit` device tag and `armhf` architecture. Raspberry Pi 4 and Pi 5 remain available through the 64-bit image with their `pi4` and `pi5` device tags and `armv8` architecture. This is the generic `cloudinit` format, not `cloudinit-rpi`: it does not advertise Raspberry Pi-specific hardware toggles that have not been configured and tested in the PetCam images.

## Build targets and stage ordering

The workflow builds ARMHF and ARM64 independently on x86-64 GitHub-hosted runners. pi-gen's build container is i386, so using an x86-64 runner avoids the execution-format failure encountered on ARM64 runners; the pi-gen branch selects the target image architecture. `master` produces 32-bit ARMHF and `arm64` produces 64-bit ARM64.

The PetCam stage intentionally remains **after** `stage0 stage1 stage2`. Those upstream OS stages are the expensive, relatively stable part of the build. PetCam's bundle and package manifest change more frequently, so keeping the custom stage last isolates those changes and preserves the reusable upstream work.

The two builds do not share a pi-gen work-directory cache because the cached root filesystem and stage outputs are architecture-specific. The cache is disabled rather than risk restoring one architecture's work into the other. Each generated compressed image is integrity-checked with `xz -t` before it can be used by a release.

The image builds download APT packages directly from the configured Debian and Raspberry Pi OS repositories. They deliberately do not route package downloads through a self-hosted or ephemeral APT proxy: a proxy outage must not prevent a clean image build. The final `.xz` images use compression level 1 rather than the action's slower default level 6; image integrity is still checked. Artifact upload uses compression level 0 because recompressing already-compressed `.xz` files adds CPU time with negligible size reduction.

## Upstream build updates

The workflow checks out the latest `main` branch of `usimd/pi-gen-action` for every build, then installs its locked Node dependencies and packages its TypeScript source into the `dist/index.js` entrypoint required by GitHub Actions. This is necessary because the upstream source branch does not commit the generated `dist` bundle. It means we follow current action source without pinning a commit or release, while still producing the executable artifact the Actions runner expects.

The action checks out the `master` or `arm64` branch of `RPi-Distro/pi-gen` according to the target. Raspberry Pi's pi-gen project reserves `master` for 32-bit images and `arm64` for 64-bit images. The GitHub Actions host runner architecture does not determine the target image architecture.

This deliberately favors upstream freshness over immutable action references. A change to the action's default branch can affect the next PetCam build, so both image builds must pass validation before their artifacts can be released. The action's branch is not a substitute for keeping the Trixie APT package sources current: installed kernel and OS package versions are resolved from the repositories used by pi-gen during the build.

Git is explicitly installed as a host dependency for pi-gen's build tooling; the pi-gen Docker builder also installs Git in its own image.

## Production image releases

Production releases are published only from `vMAJOR.MINOR.PATCH` tags. The Git tag is validated and used to name the release and both image assets:

- `petcam-VERSION-armhf.img.xz` and its SHA-256 checksum.
- `petcam-VERSION-arm64.img.xz` and its SHA-256 checksum.
- `petcam-imager.json`, containing the matching install choices and per-image integrity metadata.

Both image builds must complete and pass validation before the draft GitHub Release is published. No OTA signing keys, signed update manifests, or public signing keys are required.
