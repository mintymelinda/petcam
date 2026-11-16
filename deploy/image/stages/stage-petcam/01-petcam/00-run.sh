#!/bin/bash -e
set -euo pipefail
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="$PACKAGE_DIR/files/petcam-runtime.tar.gz"
: "${ROOTFS_DIR:?pi-gen did not provide ROOTFS_DIR}"
if [[ ! -s "$ARCHIVE" ]]; then echo "PetCam runtime archive is missing: $ARCHIVE" >&2; exit 1; fi
install -d -m 0755 "$ROOTFS_DIR/opt/petcam"
tar -xzf "$ARCHIVE" -C "$ROOTFS_DIR/opt/petcam"
