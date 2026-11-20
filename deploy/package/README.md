# PetCam ARMHF application package

PetCam targets the official Raspberry Pi OS Lite (32-bit) foundation. Version
releases publish both a ready-to-flash OS image with PetCam installed and this
standalone application package for upgrades or existing installations.

## Supported target

- Original Raspberry Pi Zero W (ARMv6).
- Newer Raspberry Pi models running Raspberry Pi OS Lite 32-bit.
- A 32-bit ARMHF userspace and an ARMv6-or-newer CPU are required.

Do not select Raspberry Pi OS Lite (64-bit). PetCam intentionally publishes
only the 32-bit ARMHF application package.

## Install on an existing OS

1. Flash the official Raspberry Pi OS Lite (32-bit) image for your board.
2. Complete normal OS first-boot configuration.
3. Download `petcam-armhf.tar.gz` from the
   [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest).
4. Extract it and run:

```sh
tar -xzf petcam-armhf.tar.gz
sudo ./install.sh
```

The installer verifies the 32-bit ARMHF userspace and ARMv6-or-newer CPU,
installs OS dependencies from feature-owned APT manifests, and installs the
PetCam runtime.

## Ready-to-flash image

For a new installation, prefer the `petcam-*-raspios-lite-armhf.img.xz`
release asset. It is stock Raspberry Pi OS Lite 32-bit with the same standalone
PetCam package installed during image construction. Verify its accompanying
`.sha256` file before flashing. See [deployment instructions](../README.md).

## Upgrade and persistent data

Install a newer release package using the same steps. The package replaces
application code under `/opt/petcam`, then reruns the idempotent installer.
Existing configuration under `/etc/petcam` and application state under
`/var/lib/petcam` are preserved; defaults are copied only when a file does
not already exist.
