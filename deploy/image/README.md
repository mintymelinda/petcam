# Raspberry Pi OS image build

Docker Compose assembles a portable PetCam source bundle. The `usimd/pi-gen-action` workflow generates Raspberry Pi OS Trixie ARM64 and uses a thin custom stage to install feature-owned OS packages and place PetCam at `/opt/petcam`. The existing source installer remains usable on already-running Debian and Raspberry Pi OS systems.

## Raspberry Pi Imager preconfiguration

The image enables pi-gen's cloud-init and Netplan integration. This provides the NoCloud boot-partition seed that Raspberry Pi Imager uses to apply pre-flash OS customisation on first boot.

Every tagged image release includes `petcam-imager.json`, a Raspberry Pi Imager repository manifest declaring `init_format: "cloudinit"`. It includes verified compressed and extracted image sizes and SHA-256 hashes. The stable manifest URL is:

```text
https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

In Raspberry Pi Imager 2.x, open App Options / Content Repository, choose a custom repository JSON URL, and paste the URL above. Imager will show PetCam OS as an installable image and offer its cloud-init customisation flow for hostname, user credentials, Wi-Fi, locale and SSH. The manifest currently advertises Raspberry Pi 4 and Raspberry Pi 5.

You can also launch Imager with the repository directly:

```sh
rpi-imager --repo https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json
```

This is the generic `cloudinit` format, not `cloudinit-rpi`: it does not advertise Raspberry Pi-specific hardware toggles that have not been configured and tested in the PetCam image.

## Build cache and stage ordering

The image workflow uses pi-gen-action's work-directory cache. Builds on `main` are the only writers; pull requests and other refs restore the default-branch cache in read-only mode. The cache key is commit-specific, with restore prefixes allowing a new commit to reuse the previous compatible work directory.

The PetCam stage intentionally remains **after** `stage0 stage1 stage2`. Those upstream OS stages are the expensive, relatively stable part of the build. PetCam's bundle and package manifest change more frequently, so keeping the custom stage last isolates those changes and preserves the reusable upstream work. Moving PetCam earlier would put later OS stages downstream of it and reduce the usefulness of the cache.

The cache is an optimization, not a correctness boundary: pi-gen stages still run, and the action excludes cached root filesystems when saving work artifacts to avoid stale rootfs state. We validate the generated compressed image on every build.

## Upstream build updates

The workflow follows `usimd/pi-gen-action@main` instead of pinning a commit or release. This removes the local checkout and Node packaging steps and picks up the action's latest implementation on each build. The action in turn checks out the `arm64` branch of `RPi-Distro/pi-gen` through `pi-gen-version: arm64`, so pi-gen changes on that branch are also picked up by new builds.

This deliberately favors upstream freshness over immutable action references. A change to the action's default branch can affect the next PetCam build, so every build must pass image validation before its artifact can be released. The action's branch is not a substitute for keeping the Trixie APT package sources current: installed kernel and OS package versions are resolved from the repositories used by pi-gen during the build.

Git is explicitly installed as a host dependency for pi-gen's build tooling; the pi-gen Docker builder also installs Git in its own image.

## Production image releases

Production releases are published only from `vMAJOR.MINOR.PATCH` tags. The Git tag is validated and used to name the release and image asset. The image build is validated before it is uploaded to a draft GitHub Release. The release contains the compressed ARM64 image, a SHA-256 checksum, and the Raspberry Pi Imager manifest. No OTA signing keys, signed update manifests, or public signing keys are required.
