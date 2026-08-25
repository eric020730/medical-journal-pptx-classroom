#!/usr/bin/env python3
"""Install, upgrade, inspect, or remove the standalone global medical-journal skill."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping


SKILL_NAME = "medical-journal-to-pptx-integrated"
PACKAGE_IMPORTS = ("pymupdf", "pptx", "PIL", "pdfplumber", "numpy")
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".venv", ".skill-work")


def global_skills_directory(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured = values.get("CODEX_HOME")
    return (
        Path(configured).expanduser() / "skills"
        if configured else Path.home() / ".agents" / "skills"
    ).absolute()


def runtime_directory(
    *, operating_system: str | None = None, environ: Mapping[str, str] | None = None
) -> Path:
    values = os.environ if environ is None else environ
    if values.get("MEDICAL_JOURNAL_PPTX_RUNTIME"):
        return Path(values["MEDICAL_JOURNAL_PPTX_RUNTIME"]).expanduser().absolute()
    if (operating_system or platform.system()) == "Windows":
        cache = Path(values.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        cache = Path(values.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return (cache / SKILL_NAME / "venv").absolute()


def runtime_python(runtime: Path) -> Path:
    return runtime / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )


def skill_identity(skill: Path) -> str:
    entrypoint = skill / "SKILL.md"
    if not entrypoint.is_file():
        raise ValueError(f"Skill entry point is missing: {entrypoint}")
    match = re.search(
        r"^name:\s*[\"']?([a-z0-9-]+)[\"']?\s*$",
        entrypoint.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Skill frontmatter does not contain a valid name: {entrypoint}")
    return match.group(1)


def source_directory(explicit: Path | None = None) -> Path:
    installer_root = Path(__file__).absolute().parent
    options = [explicit.expanduser().absolute()] if explicit else [
        installer_root / ".agents" / "skills" / SKILL_NAME,
        installer_root / "skill",
        installer_root / SKILL_NAME,
        installer_root,
    ]
    for option in options:
        if (option / "SKILL.md").is_file() and skill_identity(option) == SKILL_NAME:
            return option
    raise FileNotFoundError(
        "The integrated skill was not found beside this installer. Extract the complete "
        "GitHub release ZIP or provide --source /path/to/the/skill."
    )


def destination_directory(target: Path | None) -> Path:
    root = target.expanduser().absolute() if target else global_skills_directory()
    return root / SKILL_NAME


def assert_compatible_python() -> None:
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError(
            f"Python 3.11–3.13 is required; this installer is running {platform.python_version()}."
        )


def install_dependencies(source: Path, runtime: Path) -> Path:
    executable = runtime_python(runtime)
    if not executable.is_file():
        runtime.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(runtime)], check=True, stdout=sys.stderr)
    subprocess.run(
        [str(executable), "-m", "pip", "install", "--requirement", str(source / "requirements.txt")],
        check=True,
        stdout=sys.stderr,
    )
    return executable


def verify_skill(skill: Path, python: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(python), str(skill / "scripts" / "workflow.py"), "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = json.loads(result.stdout)
    if not report.get("ok"):
        raise RuntimeError("Installed skill runtime verification failed.")
    return report


def install(
    *, source: Path, destination: Path, runtime: Path, upgrade: bool, skip_dependencies: bool
) -> dict[str, Any]:
    assert_compatible_python()
    if skill_identity(source) != SKILL_NAME:
        raise ValueError("The source does not contain the integrated medical-journal skill.")
    if destination.exists():
        if skill_identity(destination) != SKILL_NAME:
            raise ValueError(f"Refusing to replace an unrelated skill: {destination}")
        if not upgrade:
            raise FileExistsError(f"Skill already installed: {destination}. Use the upgrade command.")
    elif upgrade:
        raise FileNotFoundError(f"Skill is not installed: {destination}. Run install first.")

    python = (
        Path(sys.executable).absolute()
        if skip_dependencies else install_dependencies(source, runtime)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{SKILL_NAME}-staging-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / SKILL_NAME
        shutil.copytree(source, staged, ignore=IGNORED)
        skill_identity(staged)
        previous: Path | None = None
        if destination.exists():
            previous = destination.parent / f".{SKILL_NAME}-backup-{uuid.uuid4().hex}"
            destination.rename(previous)
        try:
            staged.rename(destination)
            doctor = verify_skill(destination, python)
        except Exception:
            if destination.exists() and destination.name == SKILL_NAME:
                shutil.rmtree(destination)
            if previous is not None and previous.exists():
                previous.rename(destination)
            raise
        if previous is not None:
            shutil.rmtree(previous)

    version = (destination / "VERSION").read_text(encoding="utf-8").strip()
    return {
        "ok": True,
        "action": "upgrade" if upgrade else "install",
        "skill_name": SKILL_NAME,
        "version": version,
        "install_path": str(destination),
        "runtime": str(runtime),
        "python": str(python),
        "runtime_managed": not skip_dependencies,
        "doctor": doctor,
        "legacy_skills_removed": [],
    }


def uninstall(destination: Path, *, runtime: Path, purge_runtime: bool) -> dict[str, Any]:
    if not destination.is_dir():
        raise FileNotFoundError(f"Integrated skill is not installed: {destination}")
    if destination.name != SKILL_NAME or skill_identity(destination) != SKILL_NAME:
        raise ValueError(f"Refusing to delete an unrelated or broad directory: {destination}")
    shutil.rmtree(destination)
    removed_runtime = False
    if purge_runtime and runtime.exists():
        if runtime.name != "venv" or runtime.parent.name != SKILL_NAME:
            raise ValueError(f"Refusing to purge a nonstandard runtime directory: {runtime}")
        shutil.rmtree(runtime)
        removed_runtime = True
    return {
        "ok": True,
        "action": "uninstall",
        "skill_name": SKILL_NAME,
        "removed_path": str(destination),
        "runtime_removed": removed_runtime,
        "legacy_skills_removed": [],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    actions = root.add_subparsers(dest="action", required=True)
    for name in ("install", "upgrade"):
        action = actions.add_parser(name, help=f"{name.capitalize()} the global skill")
        action.add_argument("--source", type=Path, help="Explicit unpacked skill directory")
        action.add_argument("--target", type=Path, help="Global skills parent directory")
        action.add_argument("--runtime-dir", type=Path, help="Shared Python runtime directory")
        action.add_argument("--skip-deps", action="store_true", help="Use the current Python environment")
        action.add_argument("--json", action="store_true")
    remove = actions.add_parser("uninstall", help="Remove only this integrated skill")
    remove.add_argument("--target", type=Path)
    remove.add_argument("--runtime-dir", type=Path)
    remove.add_argument("--purge-runtime", action="store_true")
    remove.add_argument("--json", action="store_true")
    status = actions.add_parser("status", help="Display global installation and runtime status")
    status.add_argument("--target", type=Path)
    status.add_argument("--runtime-dir", type=Path)
    status.add_argument("--json", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    destination = destination_directory(args.target)
    runtime = args.runtime_dir.expanduser().absolute() if args.runtime_dir else runtime_directory()
    if args.action in {"install", "upgrade"}:
        payload = install(
            source=source_directory(args.source), destination=destination, runtime=runtime,
            upgrade=args.action == "upgrade", skip_dependencies=args.skip_deps,
        )
    elif args.action == "uninstall":
        payload = uninstall(destination, runtime=runtime, purge_runtime=args.purge_runtime)
    else:
        version_file = destination / "VERSION"
        payload = {
            "skill_name": SKILL_NAME,
            "installed": destination.is_dir(),
            "install_path": str(destination),
            "version": version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None,
            "runtime": str(runtime),
            "runtime_ready": runtime_python(runtime).is_file(),
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            if key != "doctor":
                print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"ERROR: installation command exited with status {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
