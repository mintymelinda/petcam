#!/usr/bin/env bash
set -Eeuo pipefail
install -m 0644 \
  "${STAGE_DIR}/00-install-petcam/files/petcam-armhf.tar.gz" \
  "${ROOTFS_DIR}/tmp/petcam-armhf.tar.gz"
