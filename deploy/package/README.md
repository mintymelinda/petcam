# PetCam ARMHF application package

PetCam is installed onto the **official Raspberry Pi OS Lite (32-bit)** image.
The application release is a single 32-bit ARMHF package with an ARMv6 CPU
baseline. There are no ARM64 package variants and no custom PetCam OS image
that needs to be flashed.

## Supported target

- Original Raspberry Pi Zero W (ARMv6).
- Newer Raspberry Pi models running Raspberry Pi OS Lite 32-bit.
- A 32-bit ARMHF userspace and an ARMv6-or-newer CPU are required.

Do not select Raspberry Pi OS Lite (64-bit). The original Pi Zero W cannot run
a 64-bit operating system, and PetCam intentionally publishes only the 32-bit
ARMHF application package.

## Install

1. Use Raspberry Pi Imager to flash the official **Raspberry Pi OS Lite
   (32-bit)** image for your board.
2. Configure the OS username, hostname, and network in Imager, then boot the Pi
   and complete first-boot setup.
3. Download the single petcam-armhf.tar.gz asset from the
   [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest).
4. Extract it and run the included installer:

   \`\`\`sh
   tar -xzf petcam-armhf.tar.gz
   sudo ./install.sh
   \`\`\`

The installer verifies the 32-bit ARMHF userspace and ARMv6-or-newer CPU,
installs OS dependencies from the feature-owned APT manifests, installs the
boot launcher, and starts the PetCam supervisor through the existing boot
trigger.

Open https://<hostname>.local:8443/ after installation. The HTTPS
certificate is self-signed, so the browser may ask you to acknowledge it.

## Upgrade and persistent data

Install a newer release package using the same steps. The package replaces
application code under /opt/petcam, then reruns the idempotent installer.
Existing configuration under /etc/petcam and application state under
/var/lib/petcam are preserved; defaults are copied only when a file does
not already exist.

## Build

From a source checkout:

\`\`\`sh
PETCAM_VERSION=1.2.3 deploy/package/build.sh dist
\`\`\`

This produces exactly one release package: dist/petcam-armhf.tar.gz.
The package contains the source runtime and installer, not an operating-system
image. Native OS dependencies are installed on the target from Raspberry Pi
OS's APT repositories.
