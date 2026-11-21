#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[petcam-live555-repository] %s\n' "$*"; }
fail() { printf '[petcam-live555-repository] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 ]] || fail "Run as root."
command -v apt-get >/dev/null 2>&1 || fail "apt-get is required."
command -v dpkg >/dev/null 2>&1 || fail "dpkg is required."

package_arch="$(dpkg --print-architecture)"
[[ "$package_arch" == "armhf" ]] || fail "Live555 target packages are configured for ARMHF, detected '$package_arch'."

. /etc/os-release
[[ "${VERSION_CODENAME:-}" == "trixie" ]] || fail "Expected Debian/Raspberry Pi OS Trixie."
case "${ID:-}" in
  debian|raspbian) ;;
  *) fail "Unsupported operating system ID '${ID:-unknown}'." ;;
esac

keyring_package="deb-multimedia-keyring_2024.9.1_all.deb"
keyring_url="https://www.deb-multimedia.org/pool/main/d/deb-multimedia-keyring/$keyring_package"
keyring_sha256="8dc6cbb266c701cfe58bd1d2eb9fe2245a1d6341c7110cfbfe3a5a975dcf97ca"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT

log "Installing HTTPS and package-signature prerequisites."
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gpgv

log "Downloading the Debian Multimedia signing-key package."
curl --fail --location --retry 3 --retry-all-errors --silent --show-error \
  "$keyring_url" --output "$temporary_directory/$keyring_package"
printf '%s  %s\n' "$keyring_sha256" "$temporary_directory/$keyring_package" |
  sha256sum --check --status || fail "Debian Multimedia keyring package checksum verification failed."

log "Installing the verified repository signing key."
apt-get install -y "$temporary_directory/$keyring_package"
[[ -r /usr/share/keyrings/deb-multimedia-keyring.pgp ]] ||
  fail "The Debian Multimedia package did not install its expected signing key."

log "Configuring the Trixie ARMHF package source."
install -d -m 0755 /etc/apt/sources.list.d /etc/apt/preferences.d
cat > /etc/apt/sources.list.d/petcam-deb-multimedia.sources <<'EOF'
Types: deb
URIs: https://www.deb-multimedia.org
Suites: trixie
Components: main non-free
Architectures: armhf
Signed-By: /usr/share/keyrings/deb-multimedia-keyring.pgp
Enabled: yes
EOF

# Keep this third-party archive below Debian's normal package priority.
# PetCam will explicitly request only the Live555 packages it needs.
cat > /etc/apt/preferences.d/petcam-deb-multimedia <<'EOF'
Package: *
Pin: origin www.deb-multimedia.org
Pin-Priority: 100
EOF

log "Refreshing package indexes and verifying the Live555 development package is available."
apt-get update
apt-cache policy liblivemedia-dev liblivemedia116
apt-cache show liblivemedia-dev >/dev/null ||
  fail "liblivemedia-dev is not available for Trixie ARMHF."

log "Debian Multimedia is configured with signature verification and low default package priority."
