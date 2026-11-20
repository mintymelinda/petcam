#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
MOCK_BIN="$TMP/bin"
mkdir -p "$MOCK_BIN"

cat > "$MOCK_BIN/dpkg" <<'MOCK'
#!/usr/bin/env bash
[[ "$1" == "--print-architecture" ]] || exit 2
printf '%s\n' "${MOCK_DPKG_ARCH:-armhf}"
MOCK
cat > "$MOCK_BIN/getconf" <<'MOCK'
#!/usr/bin/env bash
[[ "$1" == "LONG_BIT" ]] || exit 2
printf '%s\n' "${MOCK_LONG_BIT:-32}"
MOCK
cat > "$MOCK_BIN/uname" <<'MOCK'
#!/usr/bin/env bash
[[ "$1" == "-m" ]] || exit 2
printf '%s\n' "${MOCK_MACHINE:-armv6l}"
MOCK
chmod +x "$MOCK_BIN/"*

source "$ROOT/deploy/lib/platform.sh"
export PATH="$MOCK_BIN:$PATH"
export PETCAM_CPUINFO_FILE="$TMP/cpuinfo"
printf 'CPU architecture : 6\n' > "$PETCAM_CPUINFO_FILE"

validate_petcam_platform >/dev/null

expect_failure() {
  local description="$1"
  shift
  if env "$@" bash -c 'source "$1"; validate_petcam_platform' _ "$ROOT/deploy/lib/platform.sh" >/dev/null 2>&1; then
    printf 'Expected platform validation to reject %s.\n' "$description" >&2
    exit 1
  fi
}

# Run the validator in a subshell so each negative case has isolated overrides.
export ROOT
expect_failure "ARM64 userspace" "PATH=$PATH" "PETCAM_CPUINFO_FILE=$PETCAM_CPUINFO_FILE" "MOCK_DPKG_ARCH=arm64"
expect_failure "64-bit userspace" "PATH=$PATH" "PETCAM_CPUINFO_FILE=$PETCAM_CPUINFO_FILE" "MOCK_LONG_BIT=64"
printf 'CPU architecture : 5\n' > "$PETCAM_CPUINFO_FILE"
if validate_petcam_platform >/dev/null 2>&1; then
  printf 'Expected ARMv5 CPU to be rejected.\n' >&2
  exit 1
fi
: > "$PETCAM_CPUINFO_FILE"
if MOCK_MACHINE=x86_64 validate_petcam_platform >/dev/null 2>&1; then
  printf 'Expected non-ARM CPU to be rejected.\n' >&2
  exit 1
fi

printf 'PetCam platform validation tests passed.\n'
