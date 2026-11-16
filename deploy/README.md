# PetCam device deployment

Build the wheel from the repository root, copy it and this `deploy/` directory
to the Raspberry Pi, then run:

```sh
sudo bash ./deploy/install.sh ./dist/petcam-<version>-py3-none-any.whl
```

The installer targets Debian/Raspberry Pi OS with apt and systemd. It installs
the wheel into `/opt/petcam/venv`, copies systemd units, creates missing
configuration defaults, and enables the boot services. Existing settings and
credentials are preserved.

The setup portal always owns HTTPS port 8443. A self-signed local certificate
is generated only when a certificate or key is missing; replace these with a
trusted pair at `/etc/petcam/web-manager.crt` and
`/etc/petcam/web-manager.key` when appropriate.

Always enabled: GStreamer RTSP, RTSP sampler, setup portal, feature supervisor,
Home Assistant worker, and light-sensor worker. The Home Assistant and light
sensor workers remain disabled by their own settings unless explicitly enabled.
The full Web UI, motion, and timelapse are supervisor-managed and must not be
enabled directly. The obsolete `petcam-stream.service` drop-in is removed
during upgrade.
