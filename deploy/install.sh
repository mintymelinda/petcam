#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WHEEL="${1:-}"
APP_ROOT=/opt/petcam
VENV="$APP_ROOT/venv"
ETC_ROOT=/etc/petcam
STATE_ROOT=/var/lib/petcam
SYSTEMD_ROOT=/etc/systemd/system
log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0 /path/to/petcam.whl"
[[ -n "$WHEEL" && -f "$WHEEL" && "$WHEEL" == *.whl ]] || fail "Pass an existing PetCam .whl file."
[[ "$WHEEL" = /* ]] || WHEEL="$(cd -- "$(dirname -- "$WHEEL")" && pwd)/$(basename -- "$WHEEL")"
command -v apt-get >/dev/null && command -v systemctl >/dev/null || fail "Debian/Raspberry Pi OS with systemd is required."

log "Installing OS-level Python and GStreamer dependencies."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates openssl python3 python3-venv python3-pip python3-gi python3-pil \
  gir1.2-gst-rtsp-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav v4l-utils

log "Installing the wheel into the stable virtual environment."
install -d -m 0755 "$APP_ROOT" "$ETC_ROOT" "$STATE_ROOT" /run/petcam
if [[ ! -x "$VENV/bin/python" ]]; then python3 -m venv --system-site-packages "$VENV"; fi
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade "$WHEEL"
"$VENV/bin/python" -c 'import petcam.bootstrap.setup_portal, petcam.api.application'
ln -sfn "$VENV/bin/petcam-camera" /usr/local/bin/petcam-camera

log "Creating defaults only when configuration is absent."
if [[ ! -e "$ETC_ROOT/petcam.conf" ]]; then install -m 0640 "$ROOT/etc/petcam/petcam.conf" "$ETC_ROOT/petcam.conf"; fi
for name in home-assistant.conf light-sensor.conf web-manager.json; do
  if [[ ! -e "$ETC_ROOT/$name" ]]; then install -m 0640 "$ROOT/etc/petcam/$name" "$ETC_ROOT/$name"; fi
done
for feature in motion timelapse; do
  install -d -m 0750 "$STATE_ROOT/$feature"
  if [[ ! -e "$STATE_ROOT/$feature/config.json" ]]; then
    install -m 0640 "$ROOT/var/lib/petcam/$feature/config.json" "$STATE_ROOT/$feature/config.json"
  fi
done
install -d -m 0750 "$STATE_ROOT/motion/frames" "$STATE_ROOT/timelapse/frames"

if [[ ! -s "$ETC_ROOT/web-manager.crt" || ! -s "$ETC_ROOT/web-manager.key" ]]; then
  log "Generating a local self-signed HTTPS certificate (replace with a trusted certificate as needed)."
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=$(hostname -f 2>/dev/null || hostname)" \
    -keyout "$ETC_ROOT/web-manager.key.tmp" -out "$ETC_ROOT/web-manager.crt.tmp"
  install -m 0600 "$ETC_ROOT/web-manager.key.tmp" "$ETC_ROOT/web-manager.key"
  install -m 0644 "$ETC_ROOT/web-manager.crt.tmp" "$ETC_ROOT/web-manager.crt"
  rm -f "$ETC_ROOT/web-manager.key.tmp" "$ETC_ROOT/web-manager.crt.tmp"
fi
chown -R root:root "$ETC_ROOT"
chmod 0600 "$ETC_ROOT/web-manager.key"

log "Installing systemd units."
install -d -m 0755 "$SYSTEMD_ROOT"
for unit in "$ROOT"/systemd/*.service; do install -m 0644 "$unit" "$SYSTEMD_ROOT/$(basename "$unit")"; done
# Remove the orphaned legacy drop-in and disable the obsolete stream unit.
rm -f "$SYSTEMD_ROOT/petcam-stream.service.d/10-gstreamer-rtsp.conf"
rmdir "$SYSTEMD_ROOT/petcam-stream.service.d" 2>/dev/null || true
systemctl disable --now petcam-stream.service >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable petcam-g-streamer-rtsp.service petcam-rtsp-sampler.service petcam-setup.service \
  petcam-feature-services.service petcam-home-assistant.service petcam-light-sensor.service
systemctl disable petcam-web.service petcam-motion.service petcam-timelapse.service >/dev/null 2>&1 || true
systemctl restart petcam-g-streamer-rtsp.service petcam-rtsp-sampler.service petcam-setup.service \
  petcam-feature-services.service petcam-home-assistant.service petcam-light-sensor.service
log "Install complete. Setup portal: https://$(hostname -f 2>/dev/null || hostname):8443/setup"
log "The full Web UI remains disabled until enabled in the setup portal."
