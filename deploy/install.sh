#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"
source "$REPO_ROOT/deploy/lib/platform.sh"
validate_petcam_platform
command -v apt-get >/dev/null 2>&1 || fail "Raspberry Pi OS / Debian with apt is required."
[[ -f "$REPO_ROOT/src/petcam/cli.py" ]] || fail "PetCam H.264 command was not found in the source checkout."

export DEBIAN_FRONTEND=noninteractive
source "$REPO_ROOT/deploy/lib/dependencies.sh"
install_feature_dependencies "$REPO_ROOT/deploy/features"

install -d -m 0755 /usr/local/bin
install -m 0755 "$REPO_ROOT/deploy/petcam" /usr/local/bin/petcam
log "Installed the PetCam SSH configuration and H.264 RTSP command."
log "Run 'petcam' for guided setup or 'petcam -c \"USB;1920x1080;30\"' to start directly."
