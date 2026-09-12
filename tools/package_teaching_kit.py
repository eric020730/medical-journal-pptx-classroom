#!/usr/bin/env python3
"""Add an explicit teaching whitelist to the existing privacy-safe archive."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KIT_VERSION = "2026.09.14-r1"
BASE_COMMIT = "ee5f0975f403d1edb0e7e1e244482b1fdc136295"
ADDITIONS = (
    "START-HERE.md",
    "check-classroom-macos.command",
    "check-classroom-windows.cmd",
    "docs/CLASSROOM-STUDENT-GUIDE.html",
    "docs/CLASSROOM-CHECKLIST.html",
    "docs/CLASSROOM-INSTRUCTOR.md",
    "docs/CLASSROOM-ANNOUNCEMENT.txt",
    "tools/classroom_preflight.py",
    "tools/package_teaching_kit.py",
    "tests/test_classroom_teaching.py",
    ".github/workflows/classroom-teaching-kit.yml",
)


def source_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build() -> Path:
    from package_release import create_release, validate_release_files
    extras = [Path(name) for name in ADDITIONS]
    for rel in extras:
        p = ROOT / rel
        if not p.is_file() or p.is_symlink():
            raise RuntimeError(f"Missing or unsafe teaching file: {rel}")
    with tempfile.TemporaryDirectory(prefix="teaching-base-") as tmp:
        base_path = Path(tmp) / "base.zip"
        create_release(base_path)
        with zipfile.ZipFile(base_path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        roots = {name.split("/")[0] for name in entries}
        if len(roots) != 1:
            raise RuntimeError("Expected a single release root")
        root = roots.pop()
        # Reuse the original privacy scanner, including HTML as text below.
        from package_release import release_files, PERSONAL_PATH_RE
        validate_release_files(release_files() + extras)
        for rel in extras:
            data = (ROOT / rel).read_bytes()
            if PERSONAL_PATH_RE.search(data) or str(Path.home()).encode() in data:
                raise RuntimeError(f"Personal path in teaching file: {rel}")
            entries[f"{root}/{rel.as_posix()}"] = data
        entries.pop(f"{root}/RELEASE-MANIFEST.txt", None)
        build_info = {
            "kit_version": KIT_VERSION,
            "course_date": "2026-09-14",
            "base_engine_commit": BASE_COMMIT,
            "source_commit": source_commit(),
            "source_frozen": True,
            "dependency_versions_frozen": False,
            "contains_offline_runtime": False,
            "account_or_classroom_device_validation": "not_attested",
        }
        entries[f"{root}/TEACHING-BUILD.json"] = (
            json.dumps(build_info, ensure_ascii=False, indent=2) + "\n").encode()
        entries[f"{root}/README-FIRST.txt"] = (
            "2026-09-14 classroom teaching kit\n"
            "Open docs/CLASSROOM-STUDENT-GUIDE.html in your browser.\n"
            "Use only the classroom route. Start with START-HERE.md.\n"
            "Requires internet for app login and dependency installation.\n"
        ).encode()
        manifest = [f"Teaching kit: {KIT_VERSION}", "SHA256  PATH"]
        for name, data in sorted(entries.items()):
            manifest.append(f"{hashlib.sha256(data).hexdigest()}  {name.split('/', 1)[1]}")
        entries[f"{root}/RELEASE-MANIFEST.txt"] = ("\n".join(manifest) + "\n").encode()
        out = ROOT / "dist" / f"medical-journal-pptx-classroom-teaching-{KIT_VERSION}.zip"
        out.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                mode = 0o755 if Path(name).suffix in {".sh", ".command"} or Path(name).name == "journal" else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, data)
        out.with_suffix(".zip.sha256").write_text(
            f"{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}\n", encoding="utf-8")
        with zipfile.ZipFile(out) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Archive integrity failed")
        print(out.name)
        return out


if __name__ == "__main__":
    build()
