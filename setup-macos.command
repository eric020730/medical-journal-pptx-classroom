#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SKIP_SYSTEM=0
SKIP_SMOKE=0

for option in "$@"; do
  case "${option}" in
    --skip-system) SKIP_SYSTEM=1 ;;
    --skip-smoke) SKIP_SMOKE=1 ;;
    --help|-h)
      printf 'Usage: ./setup-macos.command [--skip-system] [--skip-smoke]\n'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "${option}" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  printf 'This installer is for macOS. On Windows run setup-windows.cmd.\n' >&2
  exit 1
fi

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:${PATH}"
cd "${PROJECT_ROOT}"

say() {
  printf '\n==> %s\n' "$1"
}

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

install_homebrew() {
  local installer
  say 'Homebrew is not installed. Downloading the official Homebrew installer.'
  printf 'macOS may ask for an administrator password or Command Line Tools.\n'
  installer="$(mktemp -t medical-journal-homebrew.XXXXXX)"
  curl --fail --silent --show-error --location \
    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh' \
    --output "${installer}"
  /bin/bash "${installer}"
  rm -f "${installer}"
  export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:${PATH}"
  if ! command -v brew >/dev/null 2>&1; then
    printf 'Homebrew installation completed but brew was not found. Restart Terminal and try again.\n' >&2
    exit 1
  fi
}

if [[ "${SKIP_SYSTEM}" -eq 0 ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    install_homebrew
  fi

  if ! find_compatible_python >/dev/null 2>&1; then
    say 'Installing the recommended Python 3.12.'
    brew install python@3.12
  fi

  if ! command -v pdftoppm >/dev/null 2>&1; then
    say 'Installing Poppler for PDF previews.'
    brew install poppler
  else
    say 'Poppler is already installed.'
  fi

  if [[ -x '/Applications/LibreOffice.app/Contents/MacOS/soffice' ]] || \
    command -v soffice >/dev/null 2>&1; then
    say 'LibreOffice is already installed.'
  else
    say 'Installing LibreOffice for PowerPoint-to-PDF export.'
    brew install --cask libreoffice
  fi
fi

if ! PROJECT_BOOTSTRAP_PYTHON="$(find_compatible_python)"; then
  printf 'Python 3.11-3.13 was not found. Install Python 3.12 and rerun this installer.\n' >&2
  exit 1
fi

say "Using Python: ${PROJECT_BOOTSTRAP_PYTHON}"
if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  "${PROJECT_BOOTSTRAP_PYTHON}" -m venv "${PROJECT_ROOT}/.venv"
fi

PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
say 'Installing required Python packages.'
"${PROJECT_PYTHON}" -m pip install --upgrade pip
"${PROJECT_PYTHON}" -m pip install --requirement "${PROJECT_ROOT}/requirements.txt"

mkdir -p "${PROJECT_ROOT}/sample-papers" "${PROJECT_ROOT}/outputs" "${PROJECT_ROOT}/.skill-work"
chmod +x "${PROJECT_ROOT}/journal" "${PROJECT_ROOT}/setup-macos.command"

say 'Generating the fictional practice article.'
"${PROJECT_PYTHON}" "${PROJECT_ROOT}/tools/classroom.py" demo

say 'Checking the local environment.'
if [[ "${SKIP_SYSTEM}" -eq 0 ]]; then
  "${PROJECT_PYTHON}" "${PROJECT_ROOT}/tools/classroom.py" doctor --strict
else
  "${PROJECT_PYTHON}" "${PROJECT_ROOT}/tools/classroom.py" doctor
fi

if [[ "${SKIP_SMOKE}" -eq 0 ]]; then
  say 'Running an end-to-end PDF-to-PowerPoint smoke test.'
  "${PROJECT_PYTHON}" "${PROJECT_ROOT}/tools/classroom.py" smoke-test
fi

say 'Installation complete.'
printf '1. Open this project folder in the ChatGPT/Codex desktop app.\n'
printf '2. Add a journal PDF or choose sample-papers/classroom-demo-paper.pdf.\n'
printf '3. Start a task with: $medical-journal-to-pptx-classroom\n'
printf '4. Find finished presentations in: %s/outputs\n' "${PROJECT_ROOT}"
