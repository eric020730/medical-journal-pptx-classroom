#!/usr/bin/env bash
set -u
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "${ROOT}" || exit 1
if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  printf 'First run setup-macos.command in this folder.\n'
  code=1
else
  "${ROOT}/.venv/bin/python" "${ROOT}/tools/classroom_preflight.py"
  code=$?
fi
if [[ -t 0 ]]; then
  read -r -p 'Press Return to close. ' _ || true
fi
exit "${code}"
