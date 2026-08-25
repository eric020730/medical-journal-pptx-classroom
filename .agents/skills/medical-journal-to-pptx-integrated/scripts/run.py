#!/usr/bin/env python3
"""Locate the globally installed skill runtime and invoke its portable workflow."""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path


SKILL_NAME = "medical-journal-to-pptx-integrated"
SKILL_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = ("pymupdf", "pptx", "PIL", "pdfplumber", "numpy")


def runtime_directory(
    *, operating_system: str | None = None, environ: dict[str, str] | None = None
) -> Path:
    """Return the per-user runtime cache without depending on a project path."""
    values = os.environ if environ is None else environ
    configured = values.get("MEDICAL_JOURNAL_PPTX_RUNTIME")
    if configured:
        return Path(configured).expanduser().resolve()

    system = operating_system or platform.system()
    if system == "Windows":
        cache = Path(values.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        cache = Path(values.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return (cache / SKILL_NAME / "venv").resolve()


def runtime_python(directory: Path | None = None) -> Path:
    runtime = runtime_directory() if directory is None else directory
    executable = "python.exe" if os.name == "nt" else "python"
    folder = "Scripts" if os.name == "nt" else "bin"
    return runtime / folder / executable


def current_environment_ready() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_IMPORTS)


def choose_python() -> Path:
    override = os.environ.get("MEDICAL_JOURNAL_PPTX_PYTHON")
    if override:
        # Do not resolve a virtualenv's executable symlink: its original path
        # is how Python discovers pyvenv.cfg and the environment's packages.
        candidate = Path(override).expanduser().absolute()
        if not candidate.is_file():
            raise FileNotFoundError(f"Configured skill Python does not exist: {candidate}")
        return candidate

    managed = runtime_python()
    if managed.is_file():
        return managed
    if current_environment_ready():
        return Path(sys.executable).absolute()
    raise RuntimeError(
        "The integrated skill Python runtime is not installed. Run "
        "install-global.py install, or set MEDICAL_JOURNAL_PPTX_PYTHON "
        "to a Python 3.11–3.13 environment containing the skill requirements."
    )


def main(argv: list[str] | None = None) -> int:
    executable = choose_python()
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = [str(executable), str(SKILL_ROOT / "scripts" / "workflow.py"), *arguments]
    environment = dict(os.environ)
    environment.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(command, env=environment, check=False)
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
