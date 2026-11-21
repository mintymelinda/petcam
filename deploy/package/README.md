# PetCam ARMHF application package

Build the source package with `deploy/package/build.sh`. Install the resulting archive on a supported Raspberry Pi OS 32-bit ARMHF device using the packaged `install.sh` script as root.

The package installs the PetCam command and dependencies needed to discover USB/CSI cameras, produce native H.264 capture, and packetize the stream for RTSP. It does not install a web UI, feature workers, a background supervisor, or a software video decoder.
