#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${PETCAM_INSTALL_ROOT:-/opt/petcam}"
[[ "$PACKAGE_ROOT" != "$INSTALL_ROOT" ]] || fail "Extract the package outside $INSTALL_ROOT before running the installer."
log() { printf '[petcam-package] %s\n' "$*"; }
fail() { printf '[petcam-package] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"
[[ -f "$PACKAGE_ROOT/VERSION" ]] || fail "Package VERSION file is missing."
[[ -f "$PACKAGE_ROOT/deploy/lib/platform.sh" ]] || fail "Package platform validator is missing."

source "$PACKAGE_ROOT/deploy/lib/platform.sh"
validate_petcam_platform

for required in src/petcam deploy/install.sh deploy/start.sh; do
  [[ -e "$PACKAGE_ROOT/$required" ]] || fail "Package is incomplete; missing $required."
done

version="$(tr -d '\r\n' < "$PACKAGE_ROOT/VERSION")"
[[ -n "$version" ]] || fail "Package VERSION file is empty."

install -d -m 0755 "$INSTALL_ROOT"
for item in src deploy VERSION; do
  rm -rf "$INSTALL_ROOT/$item"
  cp -a "$PACKAGE_ROOT/$item" "$INSTALL_ROOT/$item"
done

log "Installed PetCam application version $version at $INSTALL_ROOT."
log "Existing /etc/petcam configuration and /var/lib/petcam state are left in place."
PETCAM_VERSION="$version" exec "$INSTALL_ROOT/deploy/install.sh"
