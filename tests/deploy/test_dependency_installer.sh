#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/deploy/lib/dependencies.sh"

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

FEATURES="$TMP_ROOT/features"
mkdir -p "$FEATURES/core" "$FEATURES/camera" "$FEATURES/empty"
cat > "$FEATURES/core/requirements.apt" <<'EOF'
# Core packages
python3
openssl

cron # boot trigger
EOF
cat > "$FEATURES/camera/requirements.apt" <<'EOF'
v4l-utils
python3
EOF

actual="$(collect_feature_packages "$FEATURES")"
expected="$(printf '%s\n' cron openssl python3 v4l-utils)"
[[ "$actual" == "$expected" ]] || {
  printf 'Unexpected package collection.\nExpected:\n%s\nActual:\n%s\n' "$expected" "$actual" >&2
  exit 1
}

# Empty feature manifests are valid and result in no packages.
: > "$FEATURES/empty/requirements.apt"
mkdir -p "$TMP_ROOT/empty-features"
[[ -z "$(collect_feature_packages "$TMP_ROOT/empty-features")" ]]

# Manifest data must never be interpreted as shell or apt options.
printf '%s\n' '--assume-yes' > "$FEATURES/core/requirements.apt"
if collect_feature_packages "$FEATURES" >/dev/null 2>&1; then
  printf 'Expected invalid package manifest to fail.\n' >&2
  exit 1
fi

if collect_feature_packages "$TMP_ROOT/missing" >/dev/null 2>&1; then
  printf 'Expected missing feature directory to fail.\n' >&2
  exit 1
fi

printf 'Feature dependency installer tests passed.\n'
