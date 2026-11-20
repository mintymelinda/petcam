# PetCam deployment

PetCam is installed on the official Raspberry Pi OS Lite (32-bit) foundation.
Version-tag releases provide both a ready-to-flash image with PetCam already
installed and the standalone ARMHF application package for upgrades.

## Customize a local image with Raspberry Pi Imager

The PetCam image is a locally downloaded image, so Raspberry Pi Imager 2.x
needs a companion local manifest before it will offer OS customization. The
manifest must be generated on the computer that holds the image: it embeds the
image's absolute local file path.

1. Download the `petcam-*-raspios-lite-armhf.img.xz` asset, its `.sha256`
   checksum, and `create_imager_manifest.py` from the
   [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest).
2. Verify the image before using it:

   ```sh
   sha256sum -c petcam-*-raspios-lite-armhf.img.xz.sha256
   ```

3. Generate the local manifest (the script needs internet access to retrieve
   the official Raspberry Pi OS customization metadata):

   ```sh
   python3 create_imager_manifest.py petcam-vX.Y.Z-raspios-lite-armhf.img.xz
   ```

   This creates a matching `.rpi-imager-manifest` file beside the image. The
   generator resolves the upstream base-image URL, finds its exact entry in
   Raspberry Pi's Imager v4 repository, and carries its `init_format` and
   supported-device metadata forward. It calculates fresh compressed and
   decompressed image sizes and SHA-256 checksums for the PetCam image. It
   fails rather than guessing if the upstream entry cannot be identified.
4. Open the `.rpi-imager-manifest` file in Raspberry Pi Imager (double-click
   it), or select it under **App Options → Content Repository → Edit → Use
   custom file**, then apply and restart.
5. Choose the PetCam image, select the target Raspberry Pi, and use Imager's
   customization step to configure hostname, username/password, Wi-Fi, and
   other options supported by the upstream OS image.
6. Write the SD card and boot the Pi. SSH is enabled. Open
   `https://<device-hostname>.local:8443/` to continue PetCam setup.

The manifest deliberately reuses the customization format declared by the
matching official Raspberry Pi OS image. It does not assume that every
Raspberry Pi OS release uses the same mechanism (for example, older releases
use `systemd`, while current Trixie releases use `cloudinit-rpi`). The manifest
is local to the computer where it was generated; regenerate it if you move the
image to a different computer or directory.

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
