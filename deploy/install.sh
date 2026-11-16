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
if [[ "${PETCAM_SKIP_DEPENDENCIES:-0}" != 1 ]]; then
  export DEBIAN_FRONTEND=noninteractive
  source "$REPO_ROOT/deploy/lib/dependencies.sh"
  install_feature_dependencies "$REPO_ROOT/deploy/features"
else
  log "Skipping apt installation; dependencies were installed by the image builder."
fi
install -d -m 0755 "$ETC_ROOT" "$STATE_ROOT" "$RUN_ROOT"
if [[ ! -e "$ETC_ROOT/petcam.conf" ]]; then install -m 0640 "$REPO_ROOT/deploy/etc/petcam/petcam.conf" "$ETC_ROOT/petcam.conf"; fi
for name in home-assistant.conf light-sensor.conf web-manager.json; do
  if [[ ! -e "$ETC_ROOT/$name" ]]; then install -m 0640 "$REPO_ROOT/deploy/etc/petcam/$name" "$ETC_ROOT/$name"; fi
done
for feature in motion timelapse; do
  install -d -m 0750 "$STATE_ROOT/$feature"
  if [[ ! -e "$STATE_ROOT/$feature/config.json" ]]; then install -m 0640 "$REPO_ROOT/deploy/var/lib/petcam/$feature/config.json" "$STATE_ROOT/$feature/config.json"; fi
done
install -d -m 0750 "$STATE_ROOT/motion/frames" "$STATE_ROOT/timelapse/frames"
install -d -m 0755 /usr/local/sbin
install -m 0755 "$REPO_ROOT/deploy/start.sh" /usr/local/sbin/petcam-start
if [[ "${PETCAM_DEFER_TLS:-0}" != 1 ]]; then
  PETCAM_INITIALIZE_ONLY=1 PETCAM_ROOT="$REPO_ROOT" /usr/local/sbin/petcam-start "$REPO_ROOT"
else
  log "Deferring device-specific HTTPS certificate generation until first boot."
fi
printf '@reboot root /usr/local/sbin/petcam-start %q >>/var/log/petcam-supervisor.log 2>&1\n' "$REPO_ROOT" > /etc/cron.d/petcam
chmod 0644 /etc/cron.d/petcam
update-rc.d cron defaults || true
if [[ "${PETCAM_SKIP_SERVICE_START:-0}" != 1 ]]; then service cron start; fi
log "Installed source-based PetCam boot entry."
log "Supervisor command: PETCAM_ROOT=$REPO_ROOT /usr/local/sbin/petcam-start"
log "Setup portal: https://$(hostname -f 2>/dev/null || hostname):8443/setup"
