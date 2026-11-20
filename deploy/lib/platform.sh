#!/usr/bin/env bash
# Validate the only supported PetCam runtime target: 32-bit ARMHF with an
# ARMv6-or-newer CPU. Raspberry Pi OS 32-bit provides this userspace on both
# the original Pi Zero W and newer Raspberry Pi models.
petcam_platform_fail() {
  printf '[petcam-platform] ERROR: %s\n' "$*" >&2
  return 1
}

validate_petcam_platform() {
  local package_arch long_bits cpuinfo cpu_arch machine

  command -v dpkg >/dev/null 2>&1 || {
    petcam_platform_fail "dpkg is required; install PetCam on Raspberry Pi OS Lite 32-bit."
    return 1
  }
  package_arch="$(dpkg --print-architecture 2>/dev/null || true)"
  [[ "$package_arch" == "armhf" ]] || {
    petcam_platform_fail "PetCam supports only 32-bit ARMHF (ARMv6 baseline); detected dpkg architecture '${package_arch:-unknown}'."
    return 1
  }

  long_bits="$(getconf LONG_BIT 2>/dev/null || true)"
  [[ "$long_bits" == "32" ]] || {
    petcam_platform_fail "PetCam requires a 32-bit userspace; detected '${long_bits:-unknown}'-bit."
    return 1
  }

  cpuinfo="${PETCAM_CPUINFO_FILE:-/proc/cpuinfo}"
  cpu_arch=""
  if [[ -r "$cpuinfo" ]]; then
    cpu_arch="$(awk -F: '/^[[:space:]]*CPU architecture[[:space:]]*:/ { gsub(/[[:space:]]/, "", $2); print $2; exit }' "$cpuinfo")"
  fi
  if [[ "$cpu_arch" =~ ^[0-9]+$ ]]; then
    (( cpu_arch >= 6 )) || {
      petcam_platform_fail "PetCam requires ARMv6 or newer; detected ARM architecture $cpu_arch."
      return 1
    }
  else
    machine="$(uname -m 2>/dev/null || true)"
    case "$machine" in
      armv6l|armv7l|armv8l|aarch64) ;;
      *)
        petcam_platform_fail "Unable to confirm an ARMv6-or-newer CPU (machine '${machine:-unknown}')."
        return 1
        ;;
    esac
  fi

  printf '[petcam-platform] Supported 32-bit ARMHF userspace detected (ARMv%s CPU).\n' "${cpu_arch:-6+}"
}
