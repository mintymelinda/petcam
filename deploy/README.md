# PetCam H.264 runtime

PetCam serves the camera's native H.264 capture stream over RTSP. It has no web interface, MJPEG path, motion processing, timelapse, Home Assistant integration, or software video-decoding path.

Install the application package or run `sudo deploy/install.sh` from a source checkout. The installer adds only camera discovery, the headless CSI camera application, Python/GObject, and the GStreamer RTSP/H.264 dependencies.

Connect over SSH and run:

```sh
petcam
```

The guided terminal workflow asks for USB or CSI, lists detected cameras, displays their H.264 resolution/frame-rate combinations, and asks for confirmation before starting RTSP.

To skip the guided workflow and select the first camera advertising a specific mode:

```sh
petcam -c "USB;1920x1080;30"
petcam -c "USB;1280x720;30"
```

Use `petcam -h` for command help. The live terminal view shows the RTSP URL, RTSP status, streamed frame rate, CPU usage, and memory usage. Press `q` to stop the stream.

The RTSP endpoint is `rtsp://DEVICE-HOSTNAME:8554/petcam`. The command runs in the foreground and owns the camera and RTSP processes for the duration of the terminal session.

USB H.264 is passed from V4L2 as access-unit-aligned byte-stream data. CSI H.264 is emitted by `rpicam-vid`; PetCam frames its Annex-B NAL units into access units without decoding or transcoding them. Both paths feed the RTSP payloader directly.
