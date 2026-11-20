#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE="${1:?Usage: build.sh petcam-armhf.tar.gz [output-directory]}"
OUTPUT_DIR="${2:-$REPO_ROOT/dist/image}"
RASPIOS_IMAGE_URL="${PETCAM_RASPIOS_IMAGE_URL:-https://downloads.raspberrypi.com/raspios_lite_armhf_latest}"
VERSION="${PETCAM_VERSION:-}"

log() { printf '[petcam-image] %s\n' "$*"; }
fail() { printf '[petcam-image] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run this image customizer as root (for example: sudo $0 ...)."
[[ -s "$PACKAGE" ]] || fail "ARMHF application package not found: $PACKAGE"
for tool in curl xz truncate parted resize2fs losetup mount umount blkid chroot sha256sum qemu-arm-static update-binfmts; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required host tool is missing: $tool"
done
[[ -x /usr/bin/qemu-arm-static ]] || fail "qemu-arm-static is not installed at /usr/bin/qemu-arm-static."
[[ -e /proc/sys/fs/binfmt_misc/qemu-arm ]] || fail "The qemu-arm binfmt handler is not registered; install qemu-user-static and enable qemu-arm."
grep -q '^enabled' /proc/sys/fs/binfmt_misc/qemu-arm || fail "The qemu-arm binfmt handler is disabled."

if [[ -z "$VERSION" ]]; then
  VERSION="$(tar -xOzf "$PACKAGE" ./VERSION 2>/dev/null | tr -d '\r\n' || true)"
fi
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || fail "Invalid image version."

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
BUILD_ROOT="$(mktemp -d)"
ROOTFS="$BUILD_ROOT/rootfs"
BOOT_MOUNT=""
LOOP_DEVICE=""
RESOLV_LINK=""
RESOLV_BACKUP=""
RESOLV_WAS_REGULAR=0
RESOLV_REPLACED=0

cleanup() {
  set +e
  if (( RESOLV_REPLACED )); then
    rm -f "$ROOTFS/etc/resolv.conf"
    if [[ -n "$RESOLV_LINK" ]]; then ln -s "$RESOLV_LINK" "$ROOTFS/etc/resolv.conf"; elif (( RESOLV_WAS_REGULAR )); then cp -a "$RESOLV_BACKUP" "$ROOTFS/etc/resolv.conf"; fi
  fi
  for mount_path in "$ROOTFS/run" "$ROOTFS/sys" "$ROOTFS/proc" "$ROOTFS/dev" "$BOOT_MOUNT" "$ROOTFS"; do
    if [[ -n "$mount_path" ]] && mountpoint -q "$mount_path"; then
      umount -R "$mount_path" 2>/dev/null || umount -lf "$mount_path" 2>/dev/null || true
    fi
  done
  if [[ -n "$LOOP_DEVICE" ]]; then losetup -d "$LOOP_DEVICE" 2>/dev/null || true; fi
  rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

BASE_ARCHIVE="$BUILD_ROOT/raspios-lite-armhf.img.xz"
BASE_IMAGE="$BUILD_ROOT/raspios-lite-armhf.img"
BASE_CHECKSUM="$BUILD_ROOT/raspios-lite-armhf.img.xz.sha256"

log "Downloading the official Raspberry Pi OS Lite 32-bit image."
curl --fail --location --retry 5 --retry-all-errors --silent --show-error "$RASPIOS_IMAGE_URL" --output "$BASE_ARCHIVE"
curl --fail --location --retry 5 --retry-all-errors --silent --show-error "${RASPIOS_IMAGE_URL}.sha256" --output "$BASE_CHECKSUM"

BASE_SHA256="$(awk 'NR == 1 { print $1 }' "$BASE_CHECKSUM")"
[[ "$BASE_SHA256" =~ ^[a-fA-F0-9]{64}$ ]] || fail "Raspberry Pi returned an invalid SHA-256 sidecar."
printf '%s  %s\n' "$BASE_SHA256" "$BASE_ARCHIVE" | sha256sum --check --status || fail "Official Raspberry Pi OS image checksum verification failed."
log "Verified upstream image SHA-256: $BASE_SHA256"

log "Decompressing the verified stock image."
xz --decompress --threads=0 --keep "$BASE_ARCHIVE"
[[ -s "$BASE_IMAGE" ]] || fail "The decompressed Raspberry Pi OS image is empty."

# The stock Lite root partition is sized for the base OS, not PetCam's
# camera/streaming runtime. Extend only the final root partition; keep the
# existing boot partition and its start sector untouched.
log "Extending the stock root filesystem to provide room for PetCam dependencies."
truncate -s +2G "$BASE_IMAGE"
parted --script "$BASE_IMAGE" resizepart 2 100%

LOOP_DEVICE="$(losetup --find --show --partscan "$BASE_IMAGE")"
if [[ ! -b "${LOOP_DEVICE}p1" || ! -b "${LOOP_DEVICE}p2" ]]; then
  udevadm settle || true
  for _ in $(seq 1 30); do
    [[ -b "${LOOP_DEVICE}p1" && -b "${LOOP_DEVICE}p2" ]] && break
    sleep 1
  done
fi
[[ -b "${LOOP_DEVICE}p1" && -b "${LOOP_DEVICE}p2" ]] || fail "Expected boot and root partitions were not found in the official image."
[[ "$(blkid -s TYPE -o value "${LOOP_DEVICE}p1")" == vfat ]] || fail "The first image partition is not the expected FAT boot partition."
[[ "$(blkid -s TYPE -o value "${LOOP_DEVICE}p2")" == ext4 ]] || fail "The second image partition is not the expected ext4 root partition."
resize2fs "${LOOP_DEVICE}p2"

mkdir -p "$ROOTFS"
mount "${LOOP_DEVICE}p2" "$ROOTFS"
BOOT_PATH="$(awk '$1 !~ /^#/ && ($2 == "/boot/firmware" || $2 == "/boot") { print $2; exit }' "$ROOTFS/etc/fstab")"
[[ "$BOOT_PATH" == "/boot/firmware" || "$BOOT_PATH" == "/boot" ]] || fail "Could not determine the boot partition mount point from the stock image fstab."
BOOT_MOUNT="$ROOTFS$BOOT_PATH"
mkdir -p "$BOOT_MOUNT"
mount "${LOOP_DEVICE}p1" "$BOOT_MOUNT"

log "Preparing ARMHF chroot and network access."
install -m 0755 /usr/bin/qemu-arm-static "$ROOTFS/usr/bin/qemu-arm-static"
printf 'processor : 0\nCPU architecture : 6\n' > "$ROOTFS/tmp/petcam-build-cpuinfo"
if [[ -L "$ROOTFS/etc/resolv.conf" ]]; then
  RESOLV_LINK="$(readlink "$ROOTFS/etc/resolv.conf")"
  rm "$ROOTFS/etc/resolv.conf"
elif [[ -e "$ROOTFS/etc/resolv.conf" ]]; then
  RESOLV_BACKUP="$BUILD_ROOT/resolv.conf.original"
  cp -a "$ROOTFS/etc/resolv.conf" "$RESOLV_BACKUP"
  RESOLV_WAS_REGULAR=1
fi
RESOLV_REPLACED=1
cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
RESOLV_REPLACED=1

mount --rbind /dev "$ROOTFS/dev"
mount --make-rslave "$ROOTFS/dev"
mount --rbind /proc "$ROOTFS/proc"
mount --make-rslave "$ROOTFS/proc"
mount --rbind /sys "$ROOTFS/sys"
mount --make-rslave "$ROOTFS/sys"
mkdir -p "$ROOTFS/run"
mount --rbind /run "$ROOTFS/run"
mount --make-rslave "$ROOTFS/run"

log "Installing PetCam into the existing Raspberry Pi OS root filesystem."
export PETCAM_VERSION="$VERSION"
export PETCAM_INSTALL_ROOT=/opt/petcam
export PETCAM_SKIP_SERVICE_START=1
export PETCAM_DEFER_INITIALIZE=1
export PETCAM_CPUINFO_FILE=/tmp/petcam-build-cpuinfo
mkdir -p "$ROOTFS/tmp/petcam-armhf-installer"
tar -xzf "$PACKAGE" -C "$ROOTFS/tmp/petcam-armhf-installer"
chroot "$ROOTFS" /bin/bash -e -c '
  test "$(dpkg --print-architecture)" = armhf
  test "$(getconf LONG_BIT)" = 32
  /tmp/petcam-armhf-installer/install.sh
' || fail "PetCam installation in the stock image failed."

rm -rf "$ROOTFS/tmp/petcam-armhf-installer" "$ROOTFS/tmp/petcam-build-cpuinfo"
rm -f "$ROOTFS/usr/bin/qemu-arm-static"
if (( RESOLV_REPLACED )); then
  rm -f "$ROOTFS/etc/resolv.conf"
  if [[ -n "$RESOLV_LINK" ]]; then ln -s "$RESOLV_LINK" "$ROOTFS/etc/resolv.conf"; elif (( RESOLV_WAS_REGULAR )); then cp -a "$RESOLV_BACKUP" "$ROOTFS/etc/resolv.conf"; fi
  RESOLV_REPLACED=0
fi
touch "$BOOT_MOUNT/ssh"

log "Cleaning package caches and temporary installer files."
chroot "$ROOTFS" /bin/bash -e -c 'apt-get clean; rm -rf /var/lib/apt/lists/*'

log "Unmounting the customized stock image."
for mount_path in "$ROOTFS/run" "$ROOTFS/sys" "$ROOTFS/proc" "$ROOTFS/dev" "$BOOT_MOUNT" "$ROOTFS"; do
  if mountpoint -q "$mount_path"; then umount -R "$mount_path"; fi
done
losetup -d "$LOOP_DEVICE"
LOOP_DEVICE=""

FINAL_IMAGE="$OUTPUT_DIR/petcam-$VERSION-raspios-lite-armhf.img.xz"
log "Compressing the customized image."
xz --threads=0 --compress --force --keep --stdout "$BASE_IMAGE" > "$FINAL_IMAGE"
[[ -s "$FINAL_IMAGE" ]] || fail "The customized image archive is empty."
log "Created $FINAL_IMAGE"
