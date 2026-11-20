#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-$REPO_ROOT/dist}"
VERSION="${PETCAM_VERSION:-}"

VERSION="${VERSION:-development}"
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || {
  printf '[petcam-package] ERROR: Invalid package version: %s\n' "$VERSION" >&2
  exit 1
}

mkdir -p "$OUTPUT_DIR"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

cp -a "$REPO_ROOT/src" "$STAGING/src"
cp -a "$REPO_ROOT/deploy" "$STAGING/deploy"
# Image-builder internals are deliberately not part of the application package.
rm -rf "$STAGING/deploy/image"
printf '%s\n' "$VERSION" > "$STAGING/VERSION"
install -m 0755 "$REPO_ROOT/deploy/package/install.sh" "$STAGING/install.sh"

PACKAGE="$OUTPUT_DIR/petcam-armhf.tar.gz"
tar -czf "$PACKAGE" -C "$STAGING" .
tar -tzf "$PACKAGE" >/dev/null
printf '[petcam-package] Built %s (%s bytes) for the single armhf / ARMv6-baseline target.\n' \
  "$PACKAGE" "$(stat -c '%s' "$PACKAGE")"
