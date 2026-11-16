#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="${1:-${PETCAM_ROOT:-/opt/petcam}}"
ETC_ROOT="${PETCAM_ETC:-/etc/petcam}"
[[ -d "$REPO_ROOT/src/petcam" ]] || { printf '[petcam-start] ERROR: source checkout not found at %s\n' "$REPO_ROOT" >&2; exit 1; }
command -v openssl >/dev/null || { echo '[petcam-start] ERROR: openssl is required.' >&2; exit 1; }
install -d -m 0755 "$ETC_ROOT"
if [[ ! -s "$ETC_ROOT/web-manager.crt" || ! -s "$ETC_ROOT/web-manager.key" ]]; then
  printf '[petcam-start] Generating the device HTTPS certificate.\n'
  hostname_value="$(hostname -f 2>/dev/null || hostname)"
  key_tmp="$ETC_ROOT/web-manager.key.tmp.$$"
  cert_tmp="$ETC_ROOT/web-manager.crt.tmp.$$"
  trap 'rm -f "$key_tmp" "$cert_tmp"' EXIT
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=$hostname_value" -addext "subjectAltName=DNS:$hostname_value" -keyout "$key_tmp" -out "$cert_tmp"
  install -m 0600 "$key_tmp" "$ETC_ROOT/web-manager.key"
  install -m 0644 "$cert_tmp" "$ETC_ROOT/web-manager.crt"
  rm -f "$key_tmp" "$cert_tmp"
  trap - EXIT
fi
chmod 0600 "$ETC_ROOT/web-manager.key"
[[ "${PETCAM_INITIALIZE_ONLY:-0}" == 1 ]] && exit 0
cd "$REPO_ROOT"
exec env PYTHONPATH="$REPO_ROOT/src" /usr/bin/python3 -m petcam.infrastructure.system.supervisor
