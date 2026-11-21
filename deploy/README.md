# PetCam deployment

PetCam is installed on the official Raspberry Pi OS Lite (32-bit) foundation.
Version-tag releases provide both a ready-to-flash image with PetCam already
installed and the standalone ARMHF application package for upgrades.

## Customize the release image with Raspberry Pi Imager

Each versioned release includes `petcam.rpi-imager-manifest.json`. This is a
Raspberry Pi Imager repository manifest that points directly to that release's
published image and carries forward the official Raspberry Pi OS customization
metadata (including the correct `init_format` for that OS release).

1. Download `petcam.rpi-imager-manifest.json` from the
   [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest).
2. In Raspberry Pi Imager, open **App Options → Content Repository → Edit →
   Use custom file**, select the downloaded JSON file, then choose **Apply &
   Restart**. Alternatively, use **Use custom URL** with the manifest's
   GitHub release download URL.
3. Select the **PetCam — Raspberry Pi OS Lite (32-bit)** entry, choose the
   target Raspberry Pi, and use Imager's customization step to configure
   hostname, username/password, Wi-Fi, and other supported options.
4. Write the SD card and boot the Pi. SSH is enabled. Open
   `https://<device-hostname>.local:8443/` to continue PetCam setup. If you
   configure a fully qualified hostname in Imager, PetCam also includes that
   FQDN in its device certificate and reports it as the preferred setup address.

The manifest references the versioned image asset hosted by the same GitHub
release; it is not tied to a local filesystem path. Its image size and SHA-256
checksums are generated from the exact image being published. The
`.img.xz` image and its `.sha256` sidecar remain available as separate
release assets.

## Ready-to-flash image without Imager customization

If you do not need Imager's pre-flash customization, you can flash the image
directly with Raspberry Pi Imager's **Use custom** option or another image
writer. Complete Raspberry Pi OS's normal first-boot setup, then open
`https://<device-hostname>.local:8443/`.

The release image is made by downloading the official prebuilt Raspberry Pi OS
Lite 32-bit image, verifying its published SHA-256 checksum, and installing
PetCam into its existing root filesystem. The stock firmware, kernel, boot
partition, and partition layout are retained; this project does not run
`pi-gen` or build a replacement operating system. Device-specific HTTPS
certificates are generated on the first boot, not baked into the shared image.

The original Raspberry Pi Zero W is the baseline target. PetCam uses the
32-bit ARMHF/ARMv6 baseline, so newer Raspberry Pi models that support the
32-bit OS can use the same image.

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
manually with GitHub Actions `workflow_dispatch` to validate an image without
publishing a release.
