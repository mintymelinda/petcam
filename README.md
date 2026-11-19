# PetCam

PetCam turns a Raspberry Pi and a compatible USB or CSI camera into a locally managed camera system with an RTSP stream. It includes a lightweight setup portal, an optional full web dashboard, camera discovery and configuration, and optional motion, time-lapse, ambient-light, and Home Assistant integrations.

The project publishes one Raspberry Pi OS Trixie **32-bit ARMHF** image intended to cover Raspberry Pi 1 through Raspberry Pi 5, including Zero-family boards, Pi 400, and Compute Modules. The image is built with Docker Compose and pi-gen; Docker is not required on the Raspberry Pi at runtime.

## Get started

### Prebuilt Raspberry Pi image

1. Download and flash the latest PetCam image using Raspberry Pi Imager. The [PetCam Imager repository manifest](https://github.com/mintymelinda/petcam/releases/latest/download/petcam-imager.json) exposes the current image and its integrity metadata.
2. In Imager's customisation options, set a hostname, create the operating-system user credentials, and configure Wi-Fi if needed. SSH is disabled in the image defaults; enable it in Imager only if you need shell access.
3. Boot the Pi and allow the first boot to finish.
4. Open `https://<hostname>.local:8443/` (replace the hostname with the one configured in Imager). The device generates a self-signed HTTPS certificate, so the browser may ask you to acknowledge the local certificate.
5. On first use, create the PetCam administrator password. It must be at least 12 characters.
6. The setup page displays and can copy the RTSP stream URL. Add that URL as an RTSP/Media Source in OBS or open it in another RTSP client.

The full management dashboard is disabled by default. Sign in to the setup page and enable **Full Web UI** when you want to configure cameras and optional features. The lightweight setup page remains available when the full dashboard is disabled.

### Install from source on an existing Debian or Raspberry Pi OS system

The source installer is intended for Debian-family systems with `apt`. Keep the checkout at a stable location such as `/opt/petcam`, then run:

```sh
sudo ./deploy/install.sh
```

The installer discovers and installs feature-owned OS dependencies, creates the configuration and state directories, and installs the boot launcher. See [Source deployment](deploy/README.md) for details and manual launch instructions.

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
- [Source deployment](deploy/README.md)
- [Raspberry Pi image build and Imager setup](deploy/image/README.md)
- [Time-lapse storage and network mounts](docs/operations/timelapse-storage.md)
- [GStreamer RTSP performance validation](docs/operations/gstreamer-rtsp-performance-validation.md)
- [Pre-release and production release checklist](docs/operations/pre-release-checklist.md)

## Network and security notes

PetCam is designed for use on a trusted local network. Do not port-forward the setup/dashboard HTTPS port (8443) or RTSP port (8554) directly to the public internet. The setup portal's administrator login protects the web-management functions; treat the RTSP URL as a private stream endpoint and share it only with clients you trust. The generated HTTPS certificate is self-signed and local to the device.

## Project status

The latest published release and the current development branch may differ. Check the [GitHub Releases](https://github.com/mintymelinda/petcam/releases) page for the image that is actually published; a successful build on `main` is not itself a published release.
