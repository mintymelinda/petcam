#!/usr/bin/env bash
set -Eeuo pipefail
PACKAGE=/tmp/petcam-armhf.tar.gz
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR" "$PACKAGE"' EXIT
tar -xzf "$PACKAGE" -C "$WORK_DIR"
[[ -x "$WORK_DIR/install.sh" ]] || { echo "Missing PetCam package installer." >&2; exit 1; }
PETCAM_INSTALL_ROOT=/opt/petcam PETCAM_SKIP_SERVICE_START=1 PETCAM_DEFER_INITIALIZE=1 "$WORK_DIR/install.sh"
test -x /usr/local/sbin/petcam-start
test -d /etc/petcam
test -d /var/lib/petcam
