#!/usr/bin/env bash
set -euo pipefail

INTEGRATED_INSTALLER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

find_compatible_python() {
  local candidate
  for candidate in python3.12 python3.13 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1 && \
      "${candidate}" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1; then
      command -v "${candidate}"
      return 0
    fi
  done
  return 1
}

if ! INTEGRATED_INSTALLER_PYTHON="$(find_compatible_python)"; then
  printf 'Python 3.11–3.13 was not found. Install Python 3.12 and try again.\n' >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  set -- install
fi

exec "${INTEGRATED_INSTALLER_PYTHON}" "${INTEGRATED_INSTALLER_DIR}/install-global.py" "$@"
