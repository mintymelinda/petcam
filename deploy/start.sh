#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="${1:-${PETCAM_ROOT:-/opt/petcam}}"
ETC_ROOT="${PETCAM_ETC:-/etc/petcam}"
[[ -d "$REPO_ROOT/src/petcam" ]] || { printf '[petcam-start] ERROR: source checkout not found at %s\\n' "$REPO_ROOT" >&2; exit 1; }
command -v openssl >/dev/null || { echo '[petcam-start] ERROR: openssl is required.' >&2; exit 1; }
install -d -m 0755 "$ETC_ROOT"

# Resolve identity at runtime, never while customizing the image in a chroot.
hostname_value="$(hostname -s 2>/dev/null || hostname)"
if [[ ! "$hostname_value" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]]; then
  hostname_value=petcam
fi
mdns_hostname="${hostname_value}.local"
certificate_valid=0
if [[ -s "$ETC_ROOT/web-manager.crt" && -s "$ETC_ROOT/web-manager.key" ]] &&
  openssl x509 -in "$ETC_ROOT/web-manager.crt" -noout -ext subjectAltName 2>/dev/null |
    grep -Fq "DNS:$mdns_hostname"; then
  certificate_valid=1
fi

if (( ! certificate_valid )); then
  printf '[petcam-start] Generating the device HTTPS certificate for %s.\\n' "$mdns_hostname"
  san_entries=("DNS:$hostname_value" "DNS:$mdns_hostname")
  if command -v ip >/dev/null 2>&1; then
    while IFS= read -r address; do
      [[ -n "$address" ]] && san_entries+=("IP:$address")
    done < <(ip -o -4 addr show scope global 2>/dev/null | awk '{ split($4, value, "/"); print value[1] }')
    while IFS= read -r address; do
      [[ -n "$address" ]] && san_entries+=("IP:$address")
    done < <(ip -o -6 addr show scope global 2>/dev/null | awk '{ split($4, value, "/"); print value[1] }')
  fi
  san_value="$(IFS=,; printf '%s' "${san_entries[*]}")"
  key_tmp="$ETC_ROOT/web-manager.key.tmp.$$"
  cert_tmp="$ETC_ROOT/web-manager.crt.tmp.$$"
  trap 'rm -f "$key_tmp" "$cert_tmp"' EXIT
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -subj "/CN=$mdns_hostname" -addext "subjectAltName=$san_value" \
    -keyout "$key_tmp" -out "$cert_tmp"
  install -m 0600 "$key_tmp" "$ETC_ROOT/web-manager.key"
  install -m 0644 "$cert_tmp" "$ETC_ROOT/web-manager.crt"
  rm -f "$key_tmp" "$cert_tmp"
  trap - EXIT
fi
chmod 0600 "$ETC_ROOT/web-manager.key"
printf '[petcam-start] Setup portal: https://%s:8443/setup\\n' "$mdns_hostname"
[[ "${PETCAM_INITIALIZE_ONLY:-0}" == 1 ]] && exit 0
cd "$REPO_ROOT"
exec env PYTHONPATH="$REPO_ROOT/src" /usr/bin/python3 -m petcam.infrastructure.system.supervisor
