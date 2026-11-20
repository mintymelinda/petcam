# PetCam

PetCam turns a Raspberry Pi and a compatible USB or CSI camera into a locally managed camera system with an RTSP stream. It includes a lightweight setup portal, an optional full web dashboard, camera discovery and configuration, and optional motion, time-lapse, ambient-light, and Home Assistant integrations.

PetCam is an application installed **on top of the official Raspberry Pi OS Lite (32-bit)**. The project publishes one ARMHF application package with an ARMv6 CPU baseline, supporting the original Raspberry Pi Zero W and newer Pi models running the 32-bit OS. PetCam does not require a custom operating-system image, an ARM64 package, a desktop environment, or Docker on the Pi.

## Get started

### Install on stock Raspberry Pi OS Lite (32-bit)

1. Use Raspberry Pi Imager to flash the official **Raspberry Pi OS Lite (32-bit)** image for your board. This is the standard Raspberry Pi OS image, not a PetCam-customized image.
2. In Imager, configure the hostname, operating-system username/password, and Wi-Fi if needed.
3. Boot the Pi and complete the normal first-boot setup.
4. Download the single ARMHF application package from the [latest PetCam release](https://github.com/mintymelinda/petcam/releases/latest):

   ```sh
   curl -fL -o petcam-armhf.tar.gz https://github.com/mintymelinda/petcam/releases/latest/download/petcam-armhf.tar.gz
   mkdir petcam-package
   tar -xzf petcam-armhf.tar.gz -C petcam-package
   cd petcam-package
   sudo ./install.sh
   ```

5. Open `https://<hostname>.local:8443/`. The device generates a self-signed HTTPS certificate, so the browser may ask you to acknowledge it.
6. On first use, create the PetCam administrator password. It must be at least 12 characters.
7. The setup page displays and can copy the RTSP stream URL. Add that URL as an RTSP/Media Source in OBS or open it in another RTSP client.

**Use the 32-bit OS.** The original Pi Zero W cannot run a 64-bit operating system, and PetCam intentionally builds and publishes only the ARMHF/32-bit application package. The installer checks the target architecture before changing the system.

The full management dashboard is disabled by default. Sign in to the setup page and enable **Full Web UI** when you want to configure cameras and optional features. The lightweight setup page remains available when the full dashboard is disabled.

### Install from source (development)

For development or a local checkout, keep the repository at a stable location such as `/opt/petcam`, then run:

```sh
sudo ./deploy/install.sh
```

The source installer discovers and installs feature-owned OS dependencies, creates configuration and state directories, and installs the device boot launcher. See [Source deployment](deploy/README.md) for details.

## What it includes

- **Camera capture:** discovers compatible USB/V4L2 and CSI cameras, reports advertised capture modes, and lets you select a camera and mode.
- **RTSP streaming:** serves the camera at `rtsp://<hostname>:8554/petcam` for OBS and other RTSP clients. The native H.264 path hands encoded access units to the RTSP server without transcoding.
- **Setup portal:** HTTPS first-run administrator setup, sign-in, RTSP URL display/copy, and a control for the full dashboard.
- **Camera dashboard:** camera and capture-mode selection, actual capture-rate status, diagnostics, and advanced camera controls where the device exposes them.
- **Motion detection:** optional low-rate sampled-frame motion detection and event snapshots.
- **Time-lapse:** optional scheduled still captures with retention, storage limits, and optional SMB/NFS storage.
- **Ambient-light sensor:** optional TSL2591 I²C sensor integration.
- **Home Assistant:** optional MQTT discovery and state publishing.

Optional features are disabled by default. Camera availability and supported modes depend on the camera hardware, kernel drivers, and the Raspberry Pi model.

## Documentation

- [Documentation index](docs/README.md)
- [ARMHF package installation and upgrades](deploy/package/README.md)
- [Source deployment](deploy/README.md)
- [Time-lapse storage and network mounts](docs/operations/timelapse-storage.md)
- [GStreamer RTSP performance validation](docs/operations/gstreamer-rtsp-performance-validation.md)
- [Pre-release and production release checklist](docs/operations/pre-release-checklist.md)

## Network and security notes

PetCam is designed for use on a trusted local network. Do not port-forward the setup/dashboard HTTPS port (8443) or RTSP port (8554) directly to the public internet. The setup portal's administrator login protects the web-management functions; treat the RTSP URL as a private stream endpoint and share it only with clients you trust. The generated HTTPS certificate is self-signed and local to the device.

## Project status

The latest published release and the current development branch may differ. Check the [GitHub Releases](https://github.com/mintymelinda/petcam/releases) page for the application package that is actually published; a successful build on `main` is not itself a published release.
