#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE="${1:?Usage: build.sh petcam-armhf.tar.gz [output-directory]}"
OUTPUT_DIR="${2:-$REPO_ROOT/dist/image}"
VERSION="${PETCAM_VERSION:-}"
log() { printf '[petcam-image] %s\n' "$*"; }
fail() { printf '[petcam-image] ERROR: %s\n' "$*" >&2; exit 1; }
[[ -s "$PACKAGE" ]] || fail "ARMHF application package not found: $PACKAGE"
command -v git >/dev/null 2>&1 || fail "git is required."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
if [[ -z "$VERSION" ]]; then
  VERSION="$(tar -xOzf "$PACKAGE" ./VERSION 2>/dev/null | tr -d '\r\n' || true)"
fi
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || fail "Invalid image version."
PI_GEN_REF="6e3ff62bfd9c690a6a3d1d7de259d5e0af40cb78"
BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "$BUILD_ROOT"' EXIT
PI_GEN_DIR="$BUILD_ROOT/pi-gen"
mkdir -p "$OUTPUT_DIR"
git -C "$BUILD_ROOT" init -q "$PI_GEN_DIR"
git -C "$PI_GEN_DIR" remote add origin https://github.com/RPi-Distro/pi-gen.git
git -C "$PI_GEN_DIR" fetch --quiet --depth 1 origin "$PI_GEN_REF"
git -C "$PI_GEN_DIR" checkout --quiet --detach FETCH_HEAD
install -d "$PI_GEN_DIR/stage-petcam/00-install-petcam/files"
cp -a "$REPO_ROOT/deploy/image/stage-petcam/." "$PI_GEN_DIR/stage-petcam/"
install -m 0644 "$PACKAGE" "$PI_GEN_DIR/stage-petcam/00-install-petcam/files/petcam-armhf.tar.gz"
cat > "$PI_GEN_DIR/config" <<EOF
IMG_NAME="petcam-${VERSION}"
RELEASE="trixie"
DEPLOY_COMPRESSION="xz"
DEPLOY_DIR="${OUTPUT_DIR}"
WORK_DIR="${PI_GEN_DIR}/work"
ENABLE_SSH=1
FIRST_USER_NAME="petcam"
STAGE_LIST="stage0 stage1 stage2 stage-petcam"
EOF
log "Building stock Raspberry Pi OS Lite 32-bit plus PetCam."
(cd "$PI_GEN_DIR" && ./build-docker.sh)
mapfile -t images < <(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.img.xz' -print | sort)
[[ "${#images[@]}" -eq 1 ]] || fail "Expected exactly one .img.xz image."
FINAL_IMAGE="$OUTPUT_DIR/petcam-${VERSION}-raspios-lite-armhf.img.xz"
if [[ "${images[0]}" != "$FINAL_IMAGE" ]]; then mv -- "${images[0]}" "$FINAL_IMAGE"; fi
test -s "$FINAL_IMAGE"
log "Built $FINAL_IMAGE."
