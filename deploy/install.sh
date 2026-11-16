#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ETC_ROOT=/etc/petcam
STATE_ROOT=/var/lib/petcam
RUN_ROOT=/run/petcam
log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"
command -v apt-get >/dev/null || fail "Debian/Raspberry Pi OS with apt is required."
[[ -f "$REPO_ROOT/src/petcam/infrastructure/system/supervisor.py" ]] || fail "Run this installer from the PetCam source checkout."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates openssl cron python3 python3-pil python3-gi \
  gir1.2-gst-rtsp-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav v4l-utils ustreamer
# Remove legacy PetCam unit files and enablement links without calling a service manager.
rm -f /etc/systemd/system/petcam-*.service /etc/systemd/system/multi-user.target.wants/petcam-*.service
rm -f /usr/lib/systemd/system/petcam-*.service /lib/systemd/system/petcam-*.service
install -d -m 0755 "$ETC_ROOT" "$STATE_ROOT" "$RUN_ROOT"
if [[ ! -e "$ETC_ROOT/petcam.conf" ]]; then install -m 0640 "$REPO_ROOT/deploy/etc/petcam/petcam.conf" "$ETC_ROOT/petcam.conf"; fi
for name in home-assistant.conf light-sensor.conf web-manager.json; do
  if [[ ! -e "$ETC_ROOT/$name" ]]; then install -m 0640 "$REPO_ROOT/deploy/etc/petcam/$name" "$ETC_ROOT/$name"; fi
done
for feature in motion timelapse; do
  install -d -m 0750 "$STATE_ROOT/$feature"
  if [[ ! -e "$STATE_ROOT/$feature/config.json" ]]; then
    install -m 0640 "$REPO_ROOT/deploy/var/lib/petcam/$feature/config.json" "$STATE_ROOT/$feature/config.json"
  fi
done
install -d -m 0750 "$STATE_ROOT/motion/frames" "$STATE_ROOT/timelapse/frames"
if [[ ! -s "$ETC_ROOT/web-manager.crt" || ! -s "$ETC_ROOT/web-manager.key" ]]; then
  log "Generating a local self-signed HTTPS certificate."
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -subj "/CN=$(hostname -f 2>/dev/null || hostname)" \
    -keyout "$ETC_ROOT/web-manager.key.tmp" -out "$ETC_ROOT/web-manager.crt.tmp"
  install -m 0600 "$ETC_ROOT/web-manager.key.tmp" "$ETC_ROOT/web-manager.key"
  install -m 0644 "$ETC_ROOT/web-manager.crt.tmp" "$ETC_ROOT/web-manager.crt"
  rm -f "$ETC_ROOT/web-manager.key.tmp" "$ETC_ROOT/web-manager.crt.tmp"
fi
chmod 0600 "$ETC_ROOT/web-manager.key"
printf '@reboot root cd %q && PYTHONPATH=%q /usr/bin/python3 -m petcam.infrastructure.system.supervisor >>/var/log/petcam-supervisor.log 2>&1\n' \
  "$REPO_ROOT" "$REPO_ROOT/src" > /etc/cron.d/petcam
chmod 0644 /etc/cron.d/petcam
update-rc.d cron defaults || true
service cron start
log "Installed source-based PetCam boot entry."
log "Legacy PetCam unit files were removed; reboot once to release processes from the previous installation."
log "Supervisor command: PYTHONPATH=$REPO_ROOT/src python3 -m petcam.infrastructure.system.supervisor"
log "Setup portal: https://$(hostname -f 2>/dev/null || hostname):8443/setup"
