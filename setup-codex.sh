#!/usr/bin/env bash
# Agent-friendly local setup. No sudo, Homebrew, profile edits, or global skills.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
[[ -f .classroom-project.json ]] || { echo 'SETUP_BLOCKED: incomplete project'; exit 1; }
for dir in .bootstrap .venv .skill-work; do
  [[ ! -L "$ROOT/$dir" ]] || { echo "SETUP_BLOCKED: $dir is a symlink"; exit 1; }
done
if [[ "${1:-}" == '--check-only' ]]; then
  [[ $# == 1 ]] || exit 2
  exec "$ROOT/.venv/bin/python" "$ROOT/tools/codex_setup.py" --check
fi
[[ $# == 0 ]] || { echo 'Usage: bash setup-codex.sh [--check-only]'; exit 2; }
mkdir -p .bootstrap .skill-work
mkdir .bootstrap/setup.lock 2>/dev/null || { echo 'SETUP_BLOCKED: another setup may be active; do not delete its lock blindly'; exit 1; }
TMP=''
cleanup() { [[ -z "$TMP" ]] || rm -rf -- "$TMP"; rmdir .bootstrap/setup.lock 2>/dev/null || true; }
trap cleanup EXIT
# Invalidate only this tool's old receipt before changing the environment.
[[ ! -L .skill-work/codex-setup.json ]] || { echo 'SETUP_BLOCKED: receipt is a symlink'; exit 1; }
rm -f .skill-work/codex-setup.json
export UV_CACHE_DIR="$ROOT/.bootstrap/cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/.bootstrap/python"
export UV_PYTHON_BIN_DIR="$ROOT/.bootstrap/python-bin"
export UV_TOOL_DIR="$ROOT/.bootstrap/tools"
export UV_TOOL_BIN_DIR="$ROOT/.bootstrap/tool-bin"
export UV_PYTHON_INSTALL_REGISTRY=false
export UV_PYTHON_INSTALL_BIN=false
export UV_PYTHON_PREFERENCE=only-managed
export UV_NO_CONFIG=1
export PYTHONUTF8=1
PY="$ROOT/.venv/bin/python"
if [[ -e .venv ]]; then
  [[ -x "$PY" ]] && "$PY" -c 'import sys; raise SystemExit(not ((3,11)<=sys.version_info[:2]<=(3,13)))' || {
    echo 'SETUP_BLOCKED: existing .venv is incomplete or unsupported; it was not removed. Ask the instructor.'; exit 1;
  }
fi
# A repeat setup with compatible dependencies needs neither downloads nor uv.
if [[ -x "$PY" ]] && "$PY" tools/codex_setup.py --dependencies-ready; then
  echo 'Reusing this project environment. Running readiness checks.'
else
  echo 'Preparing project-local Python tooling. Internet approval may be required.'
  VERSION='0.8.22'
  case "$(uname -s):$(uname -m)" in
    Darwin:arm64) TARGET=aarch64-apple-darwin; HASH=3f61099e261e449527141dbf125629fab33ad696468c8c90cebbac40185a306c ;;
    Darwin:x86_64) TARGET=x86_64-apple-darwin; HASH=76638fdcfa91357858771551a1c88de1f7c3b270b33ab1866f8a0618d9e442d8 ;;
    Linux:x86_64) TARGET=x86_64-unknown-linux-gnu; HASH=741ff1f5742c5a4a25d2f829e8395355e43f7a5ae2ebc6368e9ae2df0efb69cf ;;
    Linux:aarch64) TARGET=aarch64-unknown-linux-gnu; HASH=726b72a137fda33565143325f7d31c42cd30ff9ccdf067e00d124d37b4081cb2 ;;
    *) echo 'SETUP_BLOCKED: unsupported OS/architecture for this bootstrap'; exit 1 ;;
  esac
  command -v curl >/dev/null || { echo 'SETUP_BLOCKED: curl missing'; exit 1; }
  command -v tar >/dev/null || { echo 'SETUP_BLOCKED: tar missing'; exit 1; }
  TMP="$(mktemp -d "$ROOT/.bootstrap/download.XXXXXX")"
  ARCHIVE="$TMP/uv.tar.gz"
  curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fLsS --retry 2 \
    "https://github.com/astral-sh/uv/releases/download/$VERSION/uv-$TARGET.tar.gz" -o "$ARCHIVE"
  if command -v shasum >/dev/null; then
    ACTUAL="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null; then
    ACTUAL="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
  else
    echo 'SETUP_BLOCKED: SHA-256 tool missing'; exit 1
  fi
  [[ "$ACTUAL" == "$HASH" ]] || { echo 'SETUP_BLOCKED: uv checksum mismatch; nothing executed'; exit 1; }
  tar -xzf "$ARCHIVE" -C "$TMP"
  UV="$TMP/uv-$TARGET/uv"
  [[ -x "$UV" ]] || { echo 'SETUP_BLOCKED: verified uv archive layout unexpected'; exit 1; }
  if [[ ! -e .venv ]]; then
    "$UV" --no-config venv --python 3.12 --seed "$ROOT/.venv"
  fi
  "$UV" --no-config pip install --python "$PY" --only-binary :all: --requirement "$ROOT/requirements.txt"
fi
chmod +x "$ROOT/journal"
# No paper is processed during setup. The agent reads the skill after this passes.
"$PY" "$ROOT/tools/codex_setup.py" --check
