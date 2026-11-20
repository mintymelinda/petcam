# PetCam documentation

Use this page to find the documentation for installing, configuring, operating, and releasing PetCam.

## Installation and deployment

- [ARMHF package installation](../deploy/package/README.md) — install PetCam on the official Raspberry Pi OS Lite (32-bit) image, upgrade the application, and understand the ARMv6 baseline.
- [Source deployment](../deploy/README.md) — install runtime dependencies, initialise configuration, and launch PetCam from a source checkout.

## Operation

- [Time-lapse storage](operations/timelapse-storage.md) — local storage defaults, SMB/NFS mount requirements, and safe behavior when a network mount is unavailable.
- [Camera mode selection](operations/camera-mode-selection.md) — automatic H.264 720p30 preference, capability-based fallbacks, explicit settings, and negotiation troubleshooting.
- [GStreamer RTSP performance validation](operations/gstreamer-rtsp-performance-validation.md) — target-device CPU, queue, memory, and functional regression checks.

## Release engineering

- [Pre-release checklist](operations/pre-release-checklist.md) — automated gates, stock-OS installation validation, hardware coverage, and production tagging requirements.
