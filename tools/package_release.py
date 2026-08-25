#!/usr/bin/env python3
"""Build a deterministic, privacy-safe classroom release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT_ROOT / ".classroom-project.json").read_text(encoding="utf-8"))
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".skill-work",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "dist",
    ".idea",
    ".vscode",
}
EXCLUDED_NAMES = {
    ".DS_Store",
    "RELEASE-MANIFEST.txt",
    "Thumbs.db",
    "diagnostics.json",
}
TEXT_SUFFIXES = {
    "",
    ".command",
    ".cmd",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}


def should_package(relative: Path) -> bool:
    """Return whether a repository-relative path belongs in a public release."""
    if relative.is_absolute() or ".." in relative.parts:
        return False
    if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
        return False
    if relative.name in EXCLUDED_NAMES or relative.name.startswith(".env"):
        return False
    if relative.suffix.lower() in {".log", ".pptx", ".pyc", ".sha256", ".zip"}:
        return False
    if relative.parts and relative.parts[0] == "sample-papers":
        return relative.as_posix() in {
            "sample-papers/README.md",
            "sample-papers/classroom-demo-paper.pdf",
        }
    if relative.parts and relative.parts[0] == "outputs":
        return relative.as_posix() == "outputs/.gitkeep"
    return True


def release_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if should_package(relative):
            files.append(relative)
    return sorted(files, key=lambda value: value.as_posix())


def validate_release_files(files: list[Path]) -> None:
    required = {
        Path("README.md"),
        Path("setup-macos.command"),
        Path("setup-windows.cmd"),
        Path("setup-windows.ps1"),
        Path(".agents/skills/medical-journal-to-pptx-classroom/SKILL.md"),
        Path("sample-papers/classroom-demo-paper.pdf"),
    }
    missing = sorted(required.difference(files), key=lambda value: value.as_posix())
    if missing:
        raise RuntimeError(
            "Release is incomplete; missing: "
            + ", ".join(path.as_posix() for path in missing)
        )

    personal_home = str(Path.home()).encode("utf-8")
    for relative in files:
        if relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = (PROJECT_ROOT / relative).read_bytes()
        if personal_home in data:
            raise RuntimeError(f"Personal home directory found in release file: {relative}")


def _zip_info(archive_name: str, source: Path) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = stat.S_IMODE(source.stat().st_mode)
    if source.name in {"setup-macos.command", "journal"} or source.suffix == ".sh":
        mode |= 0o111
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def create_release(destination: Path | None = None) -> dict[str, Any]:
    version = CONFIG["classroom_version"]
    upstream = CONFIG["upstream_version"].split("-", 1)[0]
    archive_root = CONFIG["project_name"]
    if destination is None:
        destination = (
            PROJECT_ROOT
            / "dist"
            / f"{archive_root}-v{version}-upstream-{upstream}.zip"
        )
    elif not destination.is_absolute():
        destination = (PROJECT_ROOT / destination).resolve()
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")

    files = release_files()
    validate_release_files(files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    manifest_lines = [
        "Medical Journal PPTX Classroom release manifest",
        f"Classroom version: v{version}",
        f"Upstream skill: {CONFIG['upstream_version']}",
        "",
        "SHA256  PATH",
    ]
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for relative in files:
            source = PROJECT_ROOT / relative
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            manifest_lines.append(f"{digest}  {relative.as_posix()}")
            archive_name = f"{archive_root}/{relative.as_posix()}"
            archive.writestr(_zip_info(archive_name, source), data)

        manifest = ("\n".join(manifest_lines) + "\n").encode("utf-8")
        manifest_name = f"{archive_root}/RELEASE-MANIFEST.txt"
        info = zipfile.ZipInfo(manifest_name, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, manifest)

    archive_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    checksum_path = destination.with_suffix(destination.suffix + ".sha256")
    checksum_path.write_text(
        f"{archive_digest}  {destination.name}\n", encoding="utf-8"
    )
    return {
        "archive": str(destination),
        "sha256": archive_digest,
        "checksum_file": str(checksum_path),
        "files": len(files) + 1,
        "size_bytes": destination.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print(json.dumps(create_release(args.out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
