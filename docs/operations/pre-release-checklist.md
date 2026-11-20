# PetCam pre-release and production release checklist

This checklist separates repository/CI evidence from tests that require a physical
Raspberry Pi and camera. A successful GitHub Actions run does not prove that
every advertised board, camera, or RTSP client combination works.

## Deployment contract

- PetCam is installed onto the official Raspberry Pi OS Lite (32-bit) image.
- The original Raspberry Pi Zero W is the baseline target (ARMv6).
- Newer Raspberry Pi models use the same PetCam package when running the
  32-bit OS.
- Exactly one PetCam application package is built and published:
  `petcam-armhf.tar.gz`.
- The package installer requires a 32-bit ARMHF userspace and an ARMv6-or-newer
  CPU, and rejects ARM64 / 64-bit userspace.
- There is no custom PetCam OS image build or ARM64 application package.

## Before creating a production tag

- [ ] Confirm the intended release commit is on `main` and all intended changes are merged.
- [ ] Confirm Application CI is green on that exact commit.
- [ ] Confirm the PetCam ARMHF Package workflow is green on that exact commit and
      `petcam-armhf.tar.gz` was uploaded as an artifact.
- [ ] Review the package contents and verify that it contains the runtime,
      installer, and platform guard but no OS image or ARM64 variant.
- [ ] Confirm the release notes describe user-visible changes and known limitations.
- [ ] Confirm documentation links and installation instructions use the stock
      Raspberry Pi OS Lite (32-bit) image.
- [ ] Choose a new `vMAJOR.MINOR.PATCH` tag. Do not reuse an existing tag.

A version tag triggers the package workflow. It validates the tag format,
builds the single ARMHF application archive, creates a draft GitHub Release,
uploads the package and SHA-256 checksum, verifies both assets, and publishes
the release. The workflow does not build or publish an operating-system image.

Expected release assets:

- `petcam-armhf.tar.gz`
- `petcam-armhf.tar.gz.sha256`

## Required target-device validation

Record the device model, OS image/version, camera model, camera mode, client
count, and test result. Do not generalise a result from one Pi/camera
combination to all supported hardware.

### Stock OS installation and first boot

- [ ] Flash the official Raspberry Pi OS Lite (32-bit) image with Raspberry Pi
      Imager. Do not use a PetCam-customized OS image.
- [ ] Complete normal OS first-boot setup and confirm the selected userspace is
      32-bit ARMHF.
- [ ] Install the release package and confirm the installer accepts the
      original ARMv6 Pi Zero W and rejects unsupported architectures.
- [ ] Verify configuration under `/etc/petcam` and state under
      `/var/lib/petcam` are created with expected permissions.
- [ ] Verify first boot, hostname/network setup, and access to
      `https://HOSTNAME.local:8443/`.
- [ ] Verify first-run administrator password creation and subsequent sign-in.
- [ ] Verify the RTSP URL displayed by the setup portal opens successfully in
      OBS or another RTSP client.
- [ ] Verify the full dashboard can be enabled and disabled, and that the
      lightweight setup page remains available.
- [ ] Install a newer package over an existing installation and verify that
      existing configuration and application state are preserved.

### Camera and RTSP behavior

- [ ] Test at least one supported USB/V4L2 camera and one CSI camera if both
      are part of the release's advertised support.
- [ ] Test representative advertised camera modes, including a
      resolution/FPS change while an RTSP viewer is connected.
- [ ] Test zero, one, and two simultaneous RTSP clients; closing one client
      must not interrupt the other.
- [ ] Test disconnect/reconnect after all clients close, without restarting
      the worker.
- [ ] Repeat camera-mode changes and reconnects; check for frozen video,
      stale frames, worker restarts, and recovery.
- [ ] Enable motion and time-lapse separately and together; verify sampled
      frames still arrive and that disabling both leaves the native H.264
      frame branch idle.
- [ ] Capture controlled CPU measurements at zero, one, and two clients using
      the procedure in the GStreamer validation document.

### Resource and storage behavior

- [x] On `kittycam`, one active RTSP viewer was present during queue
      observation. The native RTSP queue reached a sampled high-water mark of
      0.04 MiB (2 buffers, 68.1 ms) against the 100 MiB ceiling.
- [x] On the same test session, GStreamer RSS remained 35.5 MiB across 16
      samples taken one minute apart (15 minutes total); anonymous memory was
      16.0 MiB, file-backed memory 19.6 MiB, and swap 0 MiB.
- [ ] Repeat resource measurements during zero-, one-, and two-client tests
      and record CPU averages over controlled intervals. The observed 32.1%
      CPU reading was a point-in-time process sample, not a controlled benchmark.
- [ ] Verify time-lapse local storage limits, retention, minimum-free-space
      handling, and SMB/NFS mount loss/recovery if network storage is
      advertised for the release.

The queue and memory observations above were collected using temporary
instrumentation applied directly to the installed `kittycam` worker. That
instrumentation was not committed to the repository and is not part of the
release. Queue occupancy was sampled once per second, so brief sub-second
peaks may not have been observed.

### Hardware coverage

- [ ] Install and smoke-test on the original ARMv6 Raspberry Pi Zero W.
- [ ] Install and smoke-test on a representative newer board such as Pi 4 or
      Pi 5, still running Raspberry Pi OS Lite 32-bit.
- [ ] Confirm the camera and network adapters used by the release are detected
      and function on each tested board.

A successful package build proves that the application archive was assembled
and validated. It does not prove physical boot or peripheral compatibility on
every Raspberry Pi model.

## Security and support readiness

- [ ] Confirm the full dashboard remains disabled by default on a fresh install.
- [ ] Confirm the first-run password requirement and login/session behavior.
- [ ] Confirm HTTPS is used for the setup and management pages and that the
      self-signed certificate behavior is documented.
- [ ] Do not expose ports 8443 or 8554 directly to the public internet;
      communicate the trusted-LAN deployment model.
- [ ] Verify support-bundle contents do not include secrets before asking
      users to share one.
- [ ] Review known limitations and make sure users can find the deployment,
      storage, and troubleshooting documentation.

## Release decision

A release is ready only when the automated checks are green on the exact tagged
commit, the ARMHF application package is validated, and the target-device tests
required for the advertised hardware and features have been completed or
explicitly narrowed in the release notes. A green build alone is not a release
sign-off.
