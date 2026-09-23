#!/usr/bin/env python3
"""Build a deterministic, privacy-safe classroom release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import Any

from release_version import metadata, synchronize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT_ROOT / ".classroom-project.json").read_text(encoding="utf-8"))
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".bootstrap",
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
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3"}
PERSONAL_PATH_RE = re.compile(
    rb"(?:/(?:Users|home)/[^/\s\"']+/|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+[\\/])"
)
PUBLIC_ROOT_FILES = {
    ".classroom-project.json", ".gitattributes", ".gitignore", "AGENTS.md",
    "NOTICE.md", "README.md", "CODEX-START.md", "VERSION", "journal", "journal.cmd",
    "requirements.txt", "setup-codex.sh", "setup-codex.ps1",
    "install-global.py", "install-global.sh", "install-global.ps1", "install-global.cmd",
}
PUBLIC_DOCUMENTS = {"PRIVACY.md", "TROUBLESHOOTING.md", "GLOBAL-INSTALL.md"}
PUBLIC_TOOLS = {
    "classroom.py", "make_demo_paper.py", "package_release.py",
    "release_version.py", "classroom_preflight.py", "codex_setup.py",
    "check_clean_install.py",
}
PUBLIC_TESTS = {
    "test_advanced_qa.py", "test_classroom.py", "test_classroom_teaching.py",
    "test_codex_setup.py", "test_single_workflow.py", "test_integrated_skill.py",
    "test_release_reliability.py", "test_source_crops.py", "test_native_panel_qa.py",
    "test_medical_edge_trim.py",
}
PUBLIC_GITHUB_FILES = {
    ".github/ISSUE_TEMPLATE/environment-report.yml", ".github/dependabot.yml",
    ".github/pull_request_template.md", ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
}
PUBLIC_SKILL_NAMES = {
    "medical-journal-to-pptx-integrated",
}


def is_public_skill_file(relative: Path) -> bool:
    """Default-deny skill files so accidental medical images never reach a ZIP."""
    parts = relative.parts
    if len(parts) < 4 or parts[:2] != (".agents", "skills") or parts[2] not in PUBLIC_SKILL_NAMES:
        return False
    within = parts[3:]
    if len(within) == 1:
        return within[0] in {"SKILL.md", "VERSION", "CHANGELOG.md", "requirements.txt"}
    if len(within) != 2:
        return False
    directory, filename = within
    if directory == "scripts":
        return filename.endswith(".py")
    if directory == "references":
        return filename.endswith(".md")
    if directory == "agents":
        return filename == "openai.yaml"
    if directory == "assets":
        return filename == "dr_leether_logo.png"
    return False


def should_package(relative: Path) -> bool:
    """Return whether a repository-relative path belongs in a public release."""
    if relative.is_absolute() or ".." in relative.parts:
        return False
    if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
        return False
    if relative.name in EXCLUDED_NAMES or relative.name.startswith(".env"):
        return False
    if relative.suffix.lower() in SENSITIVE_SUFFIXES:
        return False
    if relative.name.lower() == "credentials.json" or relative.name.startswith("service-account"):
        return False
    if relative.suffix.lower() in {".log", ".pptx", ".pyc", ".sha256", ".zip"}:
        return False
    if len(relative.parts) == 1:
        return relative.name in PUBLIC_ROOT_FILES
    if is_public_skill_file(relative):
        return True
    if len(relative.parts) == 2:
        directory, filename = relative.parts
        if directory == "docs":
            return filename in PUBLIC_DOCUMENTS
        if directory == "tools":
            return filename in PUBLIC_TOOLS
        if directory == "tests":
            return filename in PUBLIC_TESTS
        if directory == "sample-papers":
            return filename in {"README.md", "classroom-demo-paper.pdf"}
        if directory == "outputs":
            return filename == ".gitkeep"
    return relative.as_posix() in PUBLIC_GITHUB_FILES


def release_files() -> list[Path]:
    """List the beginner classroom ZIP; the global skill has its own archive."""
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if (
            relative.name.startswith("install-global")
            or relative == Path("docs/GLOBAL-INSTALL.md")
            or relative == Path("tools/check_clean_install.py")
            or relative in {
                Path("tests/test_integrated_skill.py"),
                Path("tests/test_release_reliability.py"),
                Path(".github/workflows/release.yml"),
            }
        ):
            continue
        if relative.parts[:1] == ("tests",):
            continue
        if should_package(relative):
            files.append(relative)
    return sorted(files, key=lambda value: value.as_posix())


def validate_release_files(files: list[Path]) -> None:
    required = {
        Path(name) for name in (
            "README.md", "AGENTS.md", "CODEX-START.md", "VERSION",
            "setup-codex.sh", "setup-codex.ps1", "tools/codex_setup.py",
            "tools/classroom_preflight.py", "requirements.txt",
            ".agents/skills/medical-journal-to-pptx-integrated/SKILL.md",
            "sample-papers/classroom-demo-paper.pdf",
        )
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
        if personal_home in data or PERSONAL_PATH_RE.search(data):
            raise RuntimeError(f"Personal absolute directory found in release file: {relative}")


def _zip_info(archive_name: str, source: Path) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = stat.S_IMODE(source.stat().st_mode)
    if source.name in {"journal"} or source.suffix == ".sh":
        mode |= 0o111
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def create_release(destination: Path | None = None) -> dict[str, Any]:
    assert_versions_current()
    version = metadata(PROJECT_ROOT)["version"]
    archive_root = CONFIG["project_name"]
    if destination is None:
        destination = (
            PROJECT_ROOT
            / "dist"
            / f"{archive_root}-v{version}.zip"
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
        "kind": "classroom",
        "archive": str(destination),
        "sha256": archive_digest,
        "checksum_file": str(checksum_path),
        "files": len(files) + 1,
        "size_bytes": destination.stat().st_size,
    }


def integrated_skill_files() -> list[tuple[Path, str]]:
    """List only the self-contained skill and standalone installation files."""
    skill_name = "medical-journal-to-pptx-integrated"
    skill_root = PROJECT_ROOT / ".agents" / "skills" / skill_name
    files: list[tuple[Path, str]] = []
    for path in skill_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if should_package(relative) and is_public_skill_file(relative):
            files.append((relative, f"skill/{path.relative_to(skill_root).as_posix()}"))
    for relative in (
        Path("install-global.py"), Path("install-global.sh"),
        Path("install-global.ps1"), Path("install-global.cmd"),
        Path("docs/GLOBAL-INSTALL.md"), Path("NOTICE.md"),
    ):
        if not (PROJECT_ROOT / relative).is_file():
            raise RuntimeError(f"Integrated skill release is incomplete; missing: {relative}")
        files.append((relative, relative.as_posix()))
    return sorted(files, key=lambda entry: entry[1])


def create_skill_release(destination: Path | None = None) -> dict[str, Any]:
    """Build a deterministic skill-only ZIP without papers, decks, or run data."""
    assert_versions_current()
    info = metadata(PROJECT_ROOT)
    skill_name = "medical-journal-to-pptx-integrated"
    archive_root = f"{skill_name}-{info['tag']}"
    destination = (
        PROJECT_ROOT / "dist" / f"{archive_root}.zip"
        if destination is None else destination.expanduser().absolute()
    )
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    files = integrated_skill_files()
    required = {
        "skill/SKILL.md", "skill/VERSION", "install-global.py",
        "install-global.sh", "install-global.ps1",
    }
    missing = sorted(required.difference(name for _, name in files))
    if missing:
        raise RuntimeError("Integrated skill release is incomplete: " + ", ".join(missing))
    personal_home = str(Path.home()).encode("utf-8")
    for relative, archive_name in files:
        if Path(archive_name).suffix.lower() in {".pdf", ".pptx"}:
            raise RuntimeError(f"Private paper or deck cannot enter a skill release: {relative}")
        if relative.suffix.lower() in TEXT_SUFFIXES:
            data = (PROJECT_ROOT / relative).read_bytes()
            if personal_home in data or PERSONAL_PATH_RE.search(data):
                raise RuntimeError(f"Personal absolute directory found in release file: {relative}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    manifest_lines = [
        "Medical Journal PPTX Integrated skill release manifest",
        f"Integrated skill version: {info['skill_version']}", "", "SHA256  PATH",
    ]
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for relative, archive_name in files:
            source = PROJECT_ROOT / relative
            data = source.read_bytes()
            manifest_lines.append(f"{hashlib.sha256(data).hexdigest()}  {archive_name}")
            archive.writestr(_zip_info(f"{archive_root}/{archive_name}", source), data)
        info_zip = zipfile.ZipInfo(
            f"{archive_root}/RELEASE-MANIFEST.txt", date_time=(2020, 1, 1, 0, 0, 0)
        )
        info_zip.compress_type = zipfile.ZIP_DEFLATED
        info_zip.create_system = 3
        info_zip.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info_zip, ("\n".join(manifest_lines) + "\n").encode("utf-8"))
    archive_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    checksum = destination.with_suffix(destination.suffix + ".sha256")
    checksum.write_text(f"{archive_digest}  {destination.name}\n", encoding="utf-8")
    return {
        "kind": "integrated-skill", "archive": str(destination),
        "sha256": archive_digest, "checksum_file": str(checksum),
        "files": len(files) + 1, "size_bytes": destination.stat().st_size,
    }


def assert_versions_current() -> None:
    changed = synchronize(PROJECT_ROOT)
    if changed:
        raise RuntimeError("Release metadata is stale: " + ", ".join(changed)
                           + ". Run python tools/release_version.py --write.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--kind", choices=("classroom", "skill", "all"), default="classroom")
    args = parser.parse_args()
    if args.kind == "all":
        if args.out is not None:
            parser.error("--out cannot be combined with --kind all")
        payload: Any = {"releases": [create_release(), create_skill_release()]}
    elif args.kind == "skill":
        payload = create_skill_release(args.out)
    else:
        payload = create_release(args.out)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
