#!/usr/bin/env bash
set -Eeuo pipefail
output="${1:-/out/petcam-runtime.tar.gz}"
output_dir="$(dirname -- "$output")"
mkdir -p "$output_dir"
cd /workspace
[[ -d src/petcam ]] || { echo "PetCam source tree is missing." >&2; exit 1; }
[[ -f deploy/install.sh && -f deploy/start.sh ]] || { echo "PetCam deployment scripts are missing." >&2; exit 1; }
if awk '!/^[[:space:]]*(#|$)/ { found=1 } END { exit !found }' deploy/python/requirements.txt; then
  echo "deploy/python/requirements.txt contains pip dependencies; add a target-compatible offline wheelhouse build first." >&2
  exit 1
fi
tar -czf "$output" --exclude='deploy/image' -C /workspace VERSION src deploy/README.md deploy/install.sh deploy/start.sh deploy/etc deploy/var deploy/features deploy/lib
test -s "$output"
printf 'Assembled PetCam runtime: %s (%s bytes)\n' "$output" "$(stat -c '%s' "$output")"
