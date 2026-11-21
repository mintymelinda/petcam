#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="${1:-${PETCAM_ROOT:-/opt/petcam}}"
ETC_ROOT="${PETCAM_ETC:-/etc/petcam}"
[[ -d "$REPO_ROOT/src/petcam" ]] || { printf '[petcam-start] ERROR: source checkout not found at %s\\n' "$REPO_ROOT" >&2; exit 1; }
command -v openssl >/dev/null || { echo '[petcam-start] ERROR: openssl is required.' >&2; exit 1; }
install -d -m 0755 "$ETC_ROOT"

# Raspberry Pi Imager writes the configured hostname into the OS identity
# (including an FQDN when one is supplied). Resolve it at boot, not in the
# image-building chroot, and keep both the short name and configured FQDN.
hostname_value="$(hostname -s 2>/dev/null || hostname)"
fqdn_value="$(hostname -f 2>/dev/null || true)"
domain_value="$(hostname -d 2>/dev/null || true)"
if [[ ! "$hostname_value" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]]; then
  hostname_value=petcam
fi
valid_fqdn() {
  [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]]
}
if ! valid_fqdn "$fqdn_value" && valid_fqdn "$hostname_value.$domain_value"; then
  fqdn_value="$hostname_value.$domain_value"
fi
if ! valid_fqdn "$fqdn_value"; then
  fqdn_value=""
fi
mdns_hostname="${hostname_value}.local"
portal_hostname="${fqdn_value:-$mdns_hostname}"

# The certificate is valid only while it covers every currently configured
# DNS identity and every current global interface address. This also rotates
# a stale certificate after Raspberry Pi Imager hostname changes or DHCP
# assigns a different address.
san_entries=("DNS:$hostname_value" "DNS:$mdns_hostname")
if [[ -n "$fqdn_value" ]]; then
  san_entries+=("DNS:$fqdn_value")
fi
if command -v ip >/dev/null 2>&1; then
  while IFS= read -r address; do
    [[ -n "$address" ]] && san_entries+=("IP:$address")
  done < <(ip -o -4 addr show scope global 2>/dev/null | awk '{ split($4, value, "/"); print value[1] }')
  while IFS= read -r address; do
    [[ -n "$address" ]] && san_entries+=("IP:$address")
  done < <(ip -o -6 addr show scope global 2>/dev/null | awk '{ split($4, value, "/"); print value[1] }')
fi

certificate_valid=0
if [[ -s "$ETC_ROOT/web-manager.crt" && -s "$ETC_ROOT/web-manager.key" ]]; then
  certificate_sans="$(openssl x509 -in "$ETC_ROOT/web-manager.crt" -noout -ext subjectAltName 2>/dev/null || true)"
  if [[ -n "$certificate_sans" ]]; then
    certificate_valid=1
    for san in "${san_entries[@]}"; do
      if ! grep -Fq "$san" <<<"$certificate_sans"; then
        certificate_valid=0
        break
      fi
    done
  fi
fi

if (( ! certificate_valid )); then
  printf '[petcam-start] Generating the device HTTPS certificate for %s.\\n' "$portal_hostname"
  san_value="$(IFS=,; printf '%s' "${san_entries[*]}")"
  key_tmp="$ETC_ROOT/web-manager.key.tmp.$$"
  cert_tmp="$ETC_ROOT/web-manager.crt.tmp.$$"
  trap 'rm -f "$key_tmp" "$cert_tmp"' EXIT
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \\
    -subj "/CN=$portal_hostname" -addext "subjectAltName=$san_value" \\
    -keyout "$key_tmp" -out "$cert_tmp"
  install -m 0600 "$key_tmp" "$ETC_ROOT/web-manager.key"
  install -m 0644 "$cert_tmp" "$ETC_ROOT/web-manager.crt"
  rm -f "$key_tmp" "$cert_tmp"
  trap - EXIT
fi
chmod 0600 "$ETC_ROOT/web-manager.key"
printf '[petcam-start] Setup portal: https://%s:8443/setup\\n' "$portal_hostname"
[[ "${PETCAM_INITIALIZE_ONLY:-0}" == 1 ]] && exit 0
cd "$REPO_ROOT"
exec env PYTHONPATH="$REPO_ROOT/src" /usr/bin/python3 -m petcam.infrastructure.system.supervisor
