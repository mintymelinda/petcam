# PetCam source deployment

PetCam runs directly from this checkout. There is no wheel build, package build,
virtual environment, or PetCam systemd unit.

## Install runtime dependencies

On Raspberry Pi OS / Debian:

```sh
sudo apt-get update
sudo apt-get install -y python3 python3-pil python3-gi \
  gir1.2-gst-rtsp-1.0 gir1.2-gst-rtsp-server-1.0 \
  gstreamer1.0-tools gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav v4l-utils \
  ca-certificates openssl cron
```

## Configure and launch

Keep the checkout at a stable path (the examples use /opt/petcam). Create
/etc/petcam and /var/lib/petcam, copy the defaults from deploy/etc and deploy/var,
then create the HTTPS certificate/key expected by the setup portal. Start:

```sh
sudo env PYTHONPATH=/opt/petcam/src python3 -m petcam.infrastructure.system.supervisor
```

The supervisor launches the always-on setup portal, RTSP server and sampler,
and starts optional workers only when their persisted feature settings enable
them. It restarts failed workers with bounded exponential backoff and writes
its live process inventory to /run/petcam/supervisor-status.json.

## Start at boot

The installer adds one root crontab @reboot entry that invokes the supervisor
from the checkout. Cron is only the boot trigger; all PetCam process lifecycle,
health and optional-feature decisions belong to the Python supervisor.

The setup portal remains at https://<device-hostname>:8443/. The full manager
is disabled by default and can be enabled from the setup portal.
