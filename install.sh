#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${PETCAM_INSTALL_ROOT:-/opt/petcam}"
log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"
command -v apt-get >/dev/null 2>&1 || fail "Raspberry Pi OS / Debian with apt is required."
command -v dpkg >/dev/null 2>&1 || fail "dpkg is required."
[[ -f "$REPO_ROOT/src/petcam/cli.py" && -f "$REPO_ROOT/requirements.apt" && -x "$REPO_ROOT/petcam" ]] || fail "Run this installer from a complete PetCam source checkout."
[[ -f "$REPO_ROOT/scripts/configure-live555-repository.sh" && -f "$REPO_ROOT/src/petcam/infrastructure/streaming/live555_server.cpp" ]] || fail "Live555 installer source files are missing."
package_arch="$(dpkg --print-architecture)"
[[ "$package_arch" == "armhf" ]] || fail "PetCam requires ARMHF; detected '$package_arch'."
long_bits="$(getconf LONG_BIT)"
[[ "$long_bits" == "32" ]] || fail "PetCam requires a 32-bit userspace; detected '$long_bits'-bit."
cpuinfo="${PETCAM_CPUINFO_FILE:-/proc/cpuinfo}"
cpu_arch=""
if [[ -r "$cpuinfo" ]]; then
  cpu_arch="$(awk -F: '/^[[:space:]]*CPU architecture[[:space:]]*:/ { gsub(/[[:space:]]/, "", $2); print $2; exit }' "$cpuinfo")"
fi
if [[ "$cpu_arch" =~ ^[0-9]+$ ]]; then
  (( cpu_arch >= 6 )) || fail "PetCam requires ARMv6 or newer; detected ARM architecture $cpu_arch."
else
  case "$(uname -m)" in
    armv6l|armv7l|armv8l|aarch64) ;;
    *) fail "Unable to confirm an ARMv6-or-newer CPU; detected '$(uname -m)'." ;;
  esac
fi
log "Configuring the signed Live555 Trixie ARMHF package repository."
bash "$REPO_ROOT/scripts/configure-live555-repository.sh"
APT_PACKAGES=()
while IFS= read -r package || [[ -n "$package" ]]; do
  package="${package%%#*}"
  package="$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' <<< "$package")"
  [[ -z "$package" ]] && continue
  [[ "$package" =~ ^[a-z0-9][a-z0-9+.-]*$ ]] || fail "Invalid apt package name in requirements.apt: $package"
  APT_PACKAGES+=("$package")
done < "$REPO_ROOT/requirements.apt"
(("${#APT_PACKAGES[@]}" > 0)) || fail "No apt packages were declared in requirements.apt."
log "Installing native H.264 capture and Live555 build dependencies."
apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
log "Installing the Python application source."
install -d -m 0755 "$APP_ROOT" /usr/local/bin "$APP_ROOT/lib"
rm -rf "$APP_ROOT/src"
cp -a "$REPO_ROOT/src" "$APP_ROOT/src"
chown -R root:root "$APP_ROOT"
log "Compiling the Live555 RTSP/RTP server for ARMHF."
g++ -std=c++17 -O2 -fPIC -shared \
  "$APP_ROOT/src/petcam/infrastructure/streaming/live555_server.cpp" \
  -o "$APP_ROOT/lib/libpetcam_live555.so" \
  -lliveMedia -lgroupsock -lBasicUsageEnvironment -lUsageEnvironment -pthread
chmod 0755 "$APP_ROOT/lib/libpetcam_live555.so"
log "Removing compiler and development headers while retaining Live555 runtime libraries."
apt-get purge -y g++ liblivemedia-dev
apt-get autoremove -y
install -m 0755 "$REPO_ROOT/petcam" /usr/local/bin/petcam
log "Installed PetCam at $APP_ROOT."
log "Run 'petcam' for guided setup or 'petcam -h' for command help."
