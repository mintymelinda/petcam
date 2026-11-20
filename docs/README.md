# PetCam documentation

Use this page to find the documentation for installing, configuring, operating, and releasing PetCam.

## Installation and deployment

- [Source deployment](../deploy/README.md) — install runtime dependencies, initialise configuration, and launch PetCam on an existing Debian or Raspberry Pi OS system.
- [Raspberry Pi image build](../deploy/image/README.md) — supported image target, Raspberry Pi Imager custom repository, build pipeline, and release assets.

## Operation

- [Time-lapse storage](operations/timelapse-storage.md) — local storage defaults, SMB/NFS mount requirements, and safe behavior when a network mount is unavailable.
- [Camera mode selection](operations/camera-mode-selection.md) — automatic H.264 720p30 preference, capability-based fallbacks, explicit settings, and negotiation troubleshooting.
- [GStreamer RTSP performance validation](operations/gstreamer-rtsp-performance-validation.md) — target-device CPU, queue, memory, and functional regression checks.

## Release engineering

- [Pre-release checklist](operations/pre-release-checklist.md) — automated gates, on-device validation, image verification, and production tagging requirements.
