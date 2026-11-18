#!/bin/bash
set -euo pipefail

: "\${BASE_DIR:?pi-gen did not provide BASE_DIR}"

bootstrap_script="\${BASE_DIR}/stage0/prerun.sh"
apt_configure_script="\${BASE_DIR}/stage0/00-configure-apt/00-run.sh"
raspbian_sources="\${BASE_DIR}/stage0/00-configure-apt/files/raspbian.sources"

for required_file in "$bootstrap_script" "$apt_configure_script"; do
  if [[ ! -f "$required_file" ]]; then
    echo "Expected pi-gen APT configuration file is missing: $required_file" >&2
    exit 1
  fi
done

# Only ARMHF uses Raspbian. Keep the ARM64 Debian source and Raspberry Pi's
# separate archive.raspberrypi.com repository unchanged.
raspbian_mirror="http://raspbian.raspberrypi.com/raspbian/"
raspbian_archive="http://archive.raspbian.org/raspbian/"

if grep -Fq "$raspbian_mirror" "$bootstrap_script"; then
  sed -i "s|$raspbian_mirror|$raspbian_archive|g" "$bootstrap_script"
elif ! grep -Fq "$raspbian_archive" "$bootstrap_script" &&
     ! grep -Fq "http://deb.debian.org/debian/" "$bootstrap_script"; then
  echo "Unrecognized pi-gen bootstrap repository; refusing to patch an unknown layout." >&2
  exit 1
fi

if [[ -f "$raspbian_sources" ]]; then
  if grep -Fq "$raspbian_mirror" "$raspbian_sources"; then
    sed -i "s|$raspbian_mirror|$raspbian_archive|g" "$raspbian_sources"
  elif ! grep -Fq "$raspbian_archive" "$raspbian_sources"; then
    echo "Unrecognized Raspbian APT source; refusing to patch an unknown layout." >&2
    exit 1
  fi
fi

# Install retry/timeout policy before stage0's first apt-get update.
if ! grep -Fq "80-petcam-network-retries" "$apt_configure_script"; then
  temporary_script="$(mktemp)"
  if ! awk '
    /^on_chroot <<-/ && !inserted {
      print "install -d -m 0755 \\"\${ROOTFS_DIR}/etc/apt/apt.conf.d\\""
      print "printf \\"Acquire::Retries \\\\"5\\\\";\\\\nAcquire::http::Timeout \\\\"30\\\\";\\\\nAcquire::https::Timeout \\\\"30\\\\";\\\\n\\" > \\"\${ROOTFS_DIR}/etc/apt/apt.conf.d/80-petcam-network-retries\\""
      inserted = 1
    }
    { print }
    END { if (!inserted) exit 42 }
  ' "$apt_configure_script" > "$temporary_script"; then
    rm -f "$temporary_script"
    echo "Could not locate pi-gen's stage0 APT update hook; refusing an incomplete patch." >&2
    exit 1
  fi
  cat "$temporary_script" > "$apt_configure_script"
  rm -f "$temporary_script"
fi

grep -Fq "80-petcam-network-retries" "$apt_configure_script"
