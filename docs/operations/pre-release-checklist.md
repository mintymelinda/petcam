# PetCam pre-release and production release checklist

This checklist separates repository/CI evidence from tests that require a physical Raspberry Pi and camera. A successful GitHub Actions run does not prove that every advertised board, camera, or RTSP client combination works.

## Repository snapshot

Audit date: 2026-11-19

- Repository: `mintymelinda/petcam`
- Audited branch: `main`
- Audited commit: `ff85ad8b8ae664ff25b1c3feff95863aab0df70b`
- Latest published release at audit time: `v1.1.1`
- Latest published release commit: `7ad2b5cc6e3e3ce6c3c2a98175eeae52bfee3871`
- Current `main` includes the 100 MiB native H.264 RTSP queue change merged in PR #67, which is newer than the published `v1.1.1` image.

The audited `main` commit has successful Application CI and Raspberry Pi Image workflow runs. The application job passed JavaScript Prettier/syntax checks, deployment shell checks, dependency discovery tests, Python compilation, architecture checks, and the unit suite. The image job passed deployment/manifest tests, Docker Compose validation, runtime assembly, pi-gen image creation, compressed-image integrity validation, and artifact upload. The production publish job was skipped because this was a push to `main`, not a version tag.

There were no open pull requests or open repository issues at the time of this audit. This does not replace the physical-device checks below.

## Before creating a production tag

- [ ] Confirm the intended release commit is on `main` and all intended changes are merged.
- [ ] Confirm Application CI is green on that exact commit.
- [ ] Confirm Raspberry Pi Image is green on that exact commit and the image artifact was uploaded.
- [ ] Review the generated image, manifest, and checksum naming for the intended release version.
- [ ] Confirm the release notes describe user-visible changes and known limitations.
- [ ] Confirm documentation links and first-boot instructions match the image being released.
- [ ] Choose a new `vMAJOR.MINOR.PATCH` tag. Do not reuse an existing tag.

A version tag triggers the image workflow. It validates the tag format, builds and validates the image, creates a draft GitHub Release, uploads the compressed image, SHA-256 checksum, and Raspberry Pi Imager manifest, verifies the required assets, and then publishes the release.

Expected release assets:

- `petcam-vVERSION-32bit.img.xz`
- `petcam-vVERSION-32bit.img.xz.sha256`
- `petcam-imager.json`

The current latest published release is `v1.1.1`; the audited `main` commit is newer. Do not describe the 100 MiB queue change as part of the published image until a release built from a commit containing that change has been published.

## Required target-device validation

Record the device model, camera model, camera mode, client count, and test result. Do not generalise a result from one Pi/camera combination to all supported hardware.

### First boot and setup

- [ ] Flash the release image with Raspberry Pi Imager using the documented custom repository manifest.
- [ ] Verify first boot, hostname/network setup, and access to `https://HOSTNAME.local:8443/`.
- [ ] Verify first-run administrator password creation and subsequent sign-in.
- [ ] Verify the RTSP URL displayed by the setup portal opens successfully in OBS or another RTSP client.
- [ ] Verify the full dashboard can be enabled and disabled, and that the lightweight setup page remains available.
- [ ] Verify SSH behavior matches the Imager options selected for the test.

### Camera and RTSP behavior

- [ ] Test at least one supported USB/V4L2 camera and one CSI camera if both are part of the release's advertised support.
- [ ] Test representative advertised camera modes, including a resolution/FPS change while an RTSP viewer is connected.
- [ ] Test zero, one, and two simultaneous RTSP clients; closing one client must not interrupt the other.
- [ ] Test disconnect/reconnect after all clients close, without restarting the worker.
- [ ] Repeat camera-mode changes and reconnects; check for frozen video, stale frames, worker restarts, and recovery.
- [ ] Enable motion and time-lapse separately and together; verify sampled frames still arrive and that disabling both leaves the native H.264 frame branch idle.
- [ ] Capture controlled CPU measurements at zero, one, and two clients using the procedure in the GStreamer validation document.

### Resource and storage behavior

- [x] On `kittycam`, one active RTSP viewer was present during queue observation. The native RTSP queue reached a sampled high-water mark of 0.04 MiB (2 buffers, 68.1 ms) against the 100 MiB ceiling.
- [x] On the same test session, GStreamer RSS remained 35.5 MiB across 16 samples taken one minute apart (15 minutes total); anonymous memory was 16.0 MiB, file-backed memory 19.6 MiB, and swap 0 MiB.
- [ ] Repeat resource measurements during zero-, one-, and two-client tests and record CPU averages over controlled intervals. The observed 32.1% CPU reading was a point-in-time process sample, not a controlled benchmark.
- [ ] Verify time-lapse local storage limits, retention, minimum-free-space handling, and SMB/NFS mount loss/recovery if network storage is advertised for the release.

The queue and memory observations above were collected using temporary instrumentation applied directly to the installed `kittycam` worker. That instrumentation was not committed to the repository and is not part of the release. Queue occupancy was sampled once per second, so brief sub-second peaks may not have been observed.

### Hardware coverage

- [ ] Boot and smoke-test the single 32-bit image on the original ARMv6 Raspberry Pi Zero/Zero W or Pi 1.
- [ ] Boot and smoke-test on a representative 64-bit-capable board such as Pi 4 or Pi 5.
- [ ] Confirm the camera and network adapters used by the release are detected and function on each tested board.

The image build passing proves that the image was assembled and its compressed artifact validated. It does not prove physical boot or peripheral compatibility on every model listed in the Imager manifest.

## Security and support readiness

- [ ] Confirm the full dashboard remains disabled by default on a fresh install.
- [ ] Confirm the first-run password requirement and login/session behavior.
- [ ] Confirm HTTPS is used for the setup and management pages and that the self-signed certificate behavior is documented.
- [ ] Do not expose ports 8443 or 8554 directly to the public internet; communicate the trusted-LAN deployment model.
- [ ] Verify support-bundle contents do not include secrets before asking users to share one.
- [ ] Review known limitations and make sure users can find the deployment, storage, and troubleshooting documentation.

## Release decision

A release is ready only when the automated checks are green on the exact tagged commit, the image artifact is validated, and the target-device tests required for the advertised hardware and features have been completed or explicitly narrowed in the release notes. A green build alone is not a release sign-off.
