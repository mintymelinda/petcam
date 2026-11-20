# PetCam deployment

PetCam is installed on the official Raspberry Pi OS Lite (32-bit) foundation.
Version-tag releases provide both a ready-to-flash image with PetCam already
installed and the standalone ARMHF application package for upgrades.

## Ready-to-flash release image

1. Download the `petcam-*-raspios-lite-armhf.img.xz` asset and its
   `.sha256` checksum from the [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest).
2. Verify it with `sha256sum -c <image>.sha256`.
3. Flash the image to an SD card using Raspberry Pi Imager or another image writer.
4. On first boot, complete Raspberry Pi OS's normal user setup. SSH is enabled.
5. Open `https://<device-hostname>:8443/` to continue PetCam setup.

The release image is made by downloading the official prebuilt Raspberry Pi OS
Lite 32-bit image, verifying its published SHA-256 checksum, and installing
PetCam into its existing root filesystem. The stock firmware, kernel, boot
partition, and partition layout are retained; this project does not run
`pi-gen` or build a replacement operating system. Device-specific HTTPS
certificates are generated on the first boot, not baked into the shared image.

The original Raspberry Pi Zero W is the baseline target. Raspberry Pi lists
its current 32-bit OS as compatible with all Raspberry Pi models; PetCam uses
the 32-bit ARMHF/ARMv6 baseline, so newer models can use the same image.

## Standalone application package

The standalone `petcam-armhf.tar.gz` asset is intended for installing PetCam
on an existing Raspberry Pi OS Lite (32-bit) system and for application
upgrades. Extract it and run `sudo ./install.sh`. Configuration under
`/etc/petcam` and state under `/var/lib/petcam` are preserved across upgrades.

## Build artifacts

The fast application package is built with `bash deploy/package/build.sh dist`.
It is the PR CI and application-upgrade artifact; it excludes image-builder
internals. Image construction is intentionally excluded from pull-request CI.

On an Ubuntu/Debian Linux host with loop-device, mount, QEMU ARM user-mode,
and binfmt support installed, run:

```sh
sudo bash deploy/image/build.sh dist/petcam-armhf.tar.gz dist
```

The script downloads the official Raspberry Pi OS Lite 32-bit image and its
upstream checksum, verifies the download, mounts its boot and root partitions,
and runs the existing PetCam package installer in an ARMHF chroot. Release CI
performs this longer customization for version tags; it can also be run
manually with GitHub Actions `workflow_dispatch` to validate an image
without publishing a release.
