# PetCam

PetCam serves a camera's native H.264 capture stream over RTSP using Live555. It does
not decode, transcode, or provide a web interface, motion processing, timelapse, or
Home Assistant integration.

## Install

On supported Raspberry Pi OS 32-bit (ARMHF, ARMv6 or newer):

```sh
sudo ./install.sh
```

The installer uses the Live555 packages provided by Raspberry Pi OS Trixie,
compiles the native RTSP/RTP server against the system libraries, then removes the
compiler and development headers. The installed application has no
GStreamer dependency.

Connect over SSH and run:

```sh
petcam
```

The guided terminal workflow asks for USB or CSI, lists detected cameras, shows their
H.264 resolution/frame-rate combinations, and asks for confirmation before starting RTSP.

To skip the guided workflow:

```sh
petcam -c "USB;1920x1080;30"
petcam -c "USB;1280x720;30"
```

The RTSP endpoint is `rtsp://DEVICE-HOSTNAME:8554/petcam`. USB H.264 is captured
directly with V4L2; CSI H.264 is captured with `rpicam-vid`. Both paths pass Annex-B
NAL units to Live555 without decoding or transcoding. Each client starts at a cached
SPS/PPS + IDR boundary.

Use `petcam -h` for command help. Press `q` in the live terminal view to stop streaming.

## Dependencies

`requirements.apt` lists the Debian runtime and build packages. USB camera mode
discovery and capture use `v4l2-ctl` from `v4l-utils`. RTSP control and H.264 RTP
packetization are provided by Live555. No Python packages or GStreamer packages are
required.

## Build a Raspberry Pi OS image

```sh
sudo ./build-image.sh
```

The image builder downloads and verifies the official Raspberry Pi OS Lite 32-bit image,
installs PetCam directly from this checkout in an ARMHF chroot, and writes the image to
`dist/image/`. Set `PETCAM_VERSION` to override the output filename's version label.
