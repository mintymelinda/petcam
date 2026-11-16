#!/usr/bin/env bash
# Feature dependency discovery and installation for PetCam.
#
# Each deploy/features/<feature>/requirements.apt file contains one Debian
# package name per line. Blank lines and comments are ignored.

feature_dependency_log() {
  printf '[petcam-dependencies] %s\n' "$*"
}

collect_feature_packages() {
  local features_root="$1"
  local manifest line package
  local -A seen=()

  [[ -d "$features_root" ]] || {
    printf 'Feature directory does not exist: %s\n' "$features_root" >&2
    return 1
  }

  while IFS= read -r manifest; do
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%%#*}"
      # Trim leading and trailing whitespace without evaluating manifest data.
      line="$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' <<< "$line")"
      [[ -z "$line" ]] && continue
      package="$line"
      if [[ ! "$package" =~ ^[a-z0-9][a-z0-9+.-]*$ ]]; then
        printf 'Invalid apt package in %s: %s\n' "$manifest" "$package" >&2
        return 1
      fi
      seen["$package"]=1
    done < "$manifest"
  done < <(find "$features_root" -mindepth 2 -maxdepth 2 -type f -name requirements.apt -print | sort)

  if (("${#seen[@]}" > 0)); then
    printf '%s\n' "${!seen[@]}" | sort
  fi
}

install_feature_dependencies() {
  local features_root="$1"
  local -a packages=()
  local packages_output

  packages_output="$(collect_feature_packages "$features_root")" || return 1
  if [[ -n "$packages_output" ]]; then
    mapfile -t packages <<< "$packages_output"
  fi
  if (("${#packages[@]}" == 0)); then
    feature_dependency_log "No feature system dependencies declared."
    return 0
  fi

  feature_dependency_log "Discovered ${#packages[@]} unique system packages across feature manifests."
  apt-get update
  apt-get install -y --no-install-recommends "${packages[@]}"
}
