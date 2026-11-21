#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${PETCAM_INSTALL_ROOT:-/opt/petcam}"

log() { printf '[petcam-install] %s\n' "$*"; }
fail() { printf '[petcam-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run as root: sudo $0"
command -v apt-get >/dev/null 2>&1 || fail "Raspberry Pi OS / Debian with apt is required."
command -v dpkg >/dev/null 2>&1 || fail "dpkg is required."
[[ -f "$REPO_ROOT/src/petcam/cli.py" && -x "$REPO_ROOT/petcam" ]] || fail "Run this installer from a complete PetCam source checkout."

# PetCam's ARMHF build targets Raspberry Pi OS 32-bit on ARMv6 or newer.
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

export DEBIAN_FRONTEND=noninteractive
log "Installing camera, Python/GObject and GStreamer dependencies."
apt-get update
apt-get install -y --no-install-recommends \
  python3 \
  python3-gi \
  gir1.2-gst-rtsp-server-1.0 \
  gstreamer1.0-plugins-good \
  v4l-utils \
  rpicam-apps-lite

# The Good plug-in package depends on Base, which supplies appsrc/appsink.
# The Python runtime uses only the standard library and OS-provided python3-gi;
# requirements.txt is intentionally empty until a genuine PyPI dependency exists.
install -d -m 0755 "$APP_ROOT" /usr/local/bin
rm -rf "$APP_ROOT/src"
cp -a "$REPO_ROOT/src" "$APP_ROOT/src"
chown -R root:root "$APP_ROOT"
install -m 0755 "$REPO_ROOT/petcam" /usr/local/bin/petcam

log "Installed PetCam at $APP_ROOT."
log "Run 'petcam' for guided setup or 'petcam -h' for command help."
