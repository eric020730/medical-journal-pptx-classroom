from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import classroom  # noqa: E402
import package_release  # noqa: E402
import qa_check  # noqa: E402


class ClassroomProjectTests(unittest.TestCase):
    def test_project_preserves_exact_classroom_skill_version(self) -> None:
        version = (classroom.SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "v0.2.38-bg-aware-trim")
        self.assertEqual(classroom.semantic_version(), "v0.2.38")

    def test_classroom_skill_is_short_and_distinct(self) -> None:
        skill = (classroom.SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('name: "medical-journal-to-pptx-classroom"', skill)
        self.assertLess(len(skill.splitlines()), 180)
        self.assertTrue(
            (classroom.SKILL_ROOT / "references" / "full_workflow_v0.2.38.md").is_file()
        )

    def test_all_classroom_executable_helpers_are_preserved(self) -> None:
        for alias, filename in classroom.SCRIPT_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertTrue((classroom.SKILL_SCRIPTS / filename).is_file())

    def test_release_filter_keeps_skill_and_excludes_private_artifacts(self) -> None:
        self.assertTrue(
            package_release.should_package(
                Path(".agents/skills/medical-journal-to-pptx-classroom/SKILL.md")
            )
        )
        self.assertTrue(
            package_release.should_package(Path("sample-papers/classroom-demo-paper.pdf"))
        )
        for private_path in (
            Path(".venv/bin/python"),
            Path(".skill-work/run/source.pdf"),
            Path("sample-papers/student-private-paper.pdf"),
            Path("outputs/student-deck.pptx"),
            Path(".env"),
            Path("dist/release.zip"),
            Path("RELEASE-MANIFEST.txt"),
        ):
            with self.subTest(path=private_path):
                self.assertFalse(package_release.should_package(private_path))

    def test_release_preserves_macos_launchers_when_packaged_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            launcher = Path(temporary) / "setup-macos.command"
            launcher.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            launcher.chmod(0o644)
            info = package_release._zip_info("project/setup-macos.command", launcher)
            mode = (info.external_attr >> 16) & 0o777
            self.assertEqual(mode & 0o111, 0o111)

    def test_release_archive_contains_skill_but_no_local_or_student_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = package_release.create_release(Path(temporary) / "classroom.zip")
            archive_path = Path(release["archive"])
            self.assertTrue(Path(release["checksum_file"]).is_file())
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                self.assertTrue(
                    any(
                        name.endswith(
                            "/.agents/skills/medical-journal-to-pptx-classroom/SKILL.md"
                        )
                        for name in names
                    )
                )
                self.assertTrue(any(name.endswith("/RELEASE-MANIFEST.txt") for name in names))
                self.assertFalse(any("/.venv/" in name for name in names))
                self.assertFalse(any("/.skill-work/" in name for name in names))
                self.assertFalse(any(name.endswith(".pptx") for name in names))

    def test_no_original_user_absolute_paths_are_packaged(self) -> None:
        forbidden_path = "/" + "/".join(("Users", "eric")) + "/"
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file() or any(
                component
                in {
                    ".git",
                    ".venv",
                    ".skill-work",
                    ".ruff_cache",
                    ".pytest_cache",
                    "__pycache__",
                    "dist",
                }
                for component in path.parts
            ):
                continue
            if path.suffix.lower() in {".png", ".pdf", ".pyc"}:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(forbidden_path, text, msg=str(path))

    def test_safe_filename_preserves_chinese_and_removes_windows_reserved_characters(self) -> None:
        self.assertEqual(classroom.safe_filename("肝臟 MRI: <Study>?"), "肝臟_MRI_Study")
        self.assertEqual(classroom.safe_filename("CON"), "paper_CON")
        self.assertEqual(classroom.safe_filename("..."), "medical-journal")
        self.assertLessEqual(len(classroom.safe_filename("x" * 200)), 72)

    def test_allocate_output_does_not_overwrite_existing_deck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            papers = root / "papers"
            outputs = root / "outputs"
            work = root / "work"
            source = root / "paper.pdf"
            source.write_bytes(b"%PDF-1.7\n")
            with mock.patch.multiple(classroom, PAPERS_DIR=papers, OUTPUTS_DIR=outputs, WORK_DIR=work):
                first = classroom.allocate_output(source, "lite")
                first.touch()
                second = classroom.allocate_output(source, "lite")
                self.assertNotEqual(first, second)
                self.assertTrue(second.name.endswith("-2.pptx"))

    def test_initialize_run_creates_private_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "study.pdf"
            source.write_bytes(b"%PDF-1.7\nsynthetic\n")
            with mock.patch.multiple(
                classroom,
                PAPERS_DIR=root / "papers",
                OUTPUTS_DIR=root / "outputs",
                WORK_DIR=root / "work",
            ):
                run = classroom.initialize_run(source, "full")
                metadata = json.loads((Path(run["work_dir"]) / "run.json").read_text())
                self.assertEqual(metadata["mode"], "full")
                self.assertEqual(metadata["slide_budget"]["minimum_slides"], 40)
                self.assertTrue((Path(run["work_dir"]) / "RUN_MANIFEST.md").is_file())

    def test_windows_poppler_package_is_detected_without_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = (
                root
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "oschwartz10612.Poppler_Test"
                / "poppler-test"
                / "Library"
                / "bin"
                / "pdftoppm.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()
            options = classroom.binary_candidates(
                "pdftoppm", operating_system="Windows", environ={"LOCALAPPDATA": str(root)}
            )
            self.assertIn(executable, options)

    def test_windows_libreoffice_location_is_detected_without_path(self) -> None:
        candidates = classroom.binary_candidates(
            "soffice",
            operating_system="Windows",
            environ={"ProgramFiles": os.path.join("Program Files")},
        )
        self.assertTrue(any(str(path).endswith(os.path.join("LibreOffice", "program", "soffice.exe"))
                            for path in candidates))

    def test_invalid_pdf_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.pdf"
            invalid.write_text("this is not a pdf", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a readable PDF"):
                classroom.resolve_pdf(str(invalid))

    def test_qa_emoji_detection(self) -> None:
        self.assertTrue(qa_check.has_emoji("📚 繁體中文講稿"))
        self.assertFalse(qa_check.has_emoji("繁體中文講稿"))

    def test_qa_rejects_missing_powerpoint(self) -> None:
        report = qa_check.validate_presentation(Path("missing.pptx"), mode="lite")
        self.assertFalse(report["ok"])
        self.assertIn("not found", report["failures"][0])


if __name__ == "__main__":
    unittest.main()
