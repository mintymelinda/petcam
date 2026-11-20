#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ETC_ROOT=/etc/petcam
STATE_ROOT=/var/lib/petcam
RUN_ROOT=/run/petcam
log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"

source "$REPO_ROOT/deploy/lib/platform.sh"
validate_petcam_platform
command -v apt-get >/dev/null || fail "Raspberry Pi OS / Debian with apt is required."
[[ -f "$REPO_ROOT/src/petcam/infrastructure/system/supervisor.py" ]] || fail "Run this installer from the PetCam source checkout."

version="${PETCAM_VERSION:-}"
if [[ -z "$version" ]] && command -v git >/dev/null && [[ -e "$REPO_ROOT/.git" ]]; then
  version="$(git -C "$REPO_ROOT" rev-parse --verify HEAD 2>/dev/null || true)"
fi
if [[ -n "$version" ]]; then
  printf '%s\n' "$version" > "$REPO_ROOT/VERSION"
  chmod 0644 "$REPO_ROOT/VERSION"
fi

export DEBIAN_FRONTEND=noninteractive
source "$REPO_ROOT/deploy/lib/dependencies.sh"
install_feature_dependencies "$REPO_ROOT/deploy/features"

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
PETCAM_INITIALIZE_ONLY=1 PETCAM_ROOT="$REPO_ROOT" /usr/local/sbin/petcam-start "$REPO_ROOT"
printf '@reboot root /usr/local/sbin/petcam-start %q >>/var/log/petcam-supervisor.log 2>&1\n' "$REPO_ROOT" > /etc/cron.d/petcam
chmod 0644 /etc/cron.d/petcam
update-rc.d cron defaults || true
service cron start
log "Installed PetCam boot entry."
log "Supervisor command: PETCAM_ROOT=$REPO_ROOT /usr/local/sbin/petcam-start"
log "Setup portal: https://$(hostname -f 2>/dev/null || hostname):8443/setup"
