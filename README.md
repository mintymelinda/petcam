# PetCam

PetCam serves a camera's native H.264 capture stream over RTSP. It does not decode,
transcode, or provide a web interface, motion processing, timelapse, or Home Assistant
integration.

## Install

On supported Raspberry Pi OS 32-bit (ARMHF, ARMv6 or newer):

```sh
sudo ./install.sh
```

The installer installs the required Debian packages, copies the Python application to
`/opt/petcam`, and installs the `petcam` command at `/usr/local/bin/petcam`.

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

Use `petcam -h` for command help. The live terminal view shows the RTSP URL, RTSP status,
streamed frame rate, CPU usage, and memory usage. Press `q` to stop the stream.

The RTSP endpoint is `rtsp://DEVICE-HOSTNAME:8554/petcam`. PetCam runs in the foreground
and owns the camera and RTSP processes for the duration of the terminal session.

## Dependencies

`requirements.apt` is the complete list of Debian packages installed by `install.sh`.
The GStreamer Good plug-ins provide `v4l2src` and `rtph264pay`; their Debian package
dependency brings in the Base plug-ins used for `appsrc` and `appsink`. USB camera
mode discovery uses `v4l2-ctl` from `v4l-utils`.

`requirements.txt` is reserved for pip dependencies and is currently empty because
the application has no third-party PyPI dependencies. GStreamer Python bindings are
provided by the OS package `python3-gi`, not installed with pip.

## Build a Raspberry Pi OS image

The source checkout can be installed into a customized Raspberry Pi OS Lite image:

```sh
sudo ./build-image.sh
```

The image builder downloads and verifies the official Raspberry Pi OS Lite 32-bit image,
installs PetCam directly from this checkout in an ARMHF chroot, and writes the image to
`dist/image/`. Set `PETCAM_VERSION` to override the output filename's version label.

`create-imager-manifest.py` creates a Raspberry Pi Imager manifest for a published
compressed image.
