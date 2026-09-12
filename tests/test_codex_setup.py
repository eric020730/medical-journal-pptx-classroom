"""Fail-closed contracts for URL-driven full-quality onboarding."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import codex_setup as setup
import classroom_preflight

QUALITY_PATH = (
    ROOT
    / ".agents"
    / "skills"
    / "medical-journal-to-pptx-classroom"
    / "scripts"
    / "quality_tools.py"
)
QUALITY_SPEC = importlib.util.spec_from_file_location("quality_tools", QUALITY_PATH)
quality_tools = importlib.util.module_from_spec(QUALITY_SPEC)
assert QUALITY_SPEC.loader is not None
QUALITY_SPEC.loader.exec_module(quality_tools)

VERSIONS = {
    "PyMuPDF": "1.28.2",
    "python-pptx": "1.0.2",
    "Pillow": "12.0.0",
    "pdfplumber": "0.11.9",
    "numpy": "2.0.0",
}


class DependenciesTests(unittest.TestCase):
    def problems(self, versions=VERSIONS):
        with patch.object(
            setup.importlib.metadata,
            "version",
            side_effect=lambda package: versions[package],
        ), patch.object(setup.importlib, "import_module"):
            return setup.dependency_problems()

    def test_current_bounds_accepted(self):
        self.assertEqual(self.problems(), [])

    def test_lower_and_upper_bounds_are_enforced(self):
        self.assertIn(
            "PyMuPDF", self.problems({**VERSIONS, "PyMuPDF": "1.26.7"})
        )
        self.assertIn("numpy", self.problems({**VERSIONS, "numpy": "3.0.0"}))

    def test_prerelease_is_not_silently_accepted(self):
        self.assertIn(
            "PyMuPDF", self.problems({**VERSIONS, "PyMuPDF": "1.28.2rc1"})
        )

    def test_missing_requirement_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "requirements.txt").write_text("# empty\n", encoding="utf-8")
            self.assertIn(
                "missing_requirement_declarations", setup.dependency_problems(root)
            )


class ReadinessTests(unittest.TestCase):
    def report(self, local=None, prefix=None):
        local = local or {
            "local_status": "FULL_QA_READY",
            "doctor_passed": True,
            "smoke_test": "passed",
            "render_test": "passed",
            "quality_tools": "ready",
            "pdf_export": "passed",
            "visual_render": "passed",
        }
        with patch.object(
            setup.sys, "prefix", prefix or str(ROOT / ".venv")
        ), patch.object(
            setup, "dependency_problems", return_value=[]
        ), patch.object(
            classroom_preflight, "collect_report", return_value=local
        ):
            return setup.build_report()

    def test_full_quality_ready_still_requires_skill_read(self):
        report = self.report()
        self.assertEqual(report["state"], "FULL_QA_READY_SKILL_PENDING")
        self.assertEqual(report["skill_read_by_agent"], "not_attested")
        self.assertEqual(report["render_test"], "passed")
        self.assertEqual(report["pdf_export"], "passed")

    def test_missing_render_or_tools_blocks_article_processing(self):
        for local in (
            {
                "local_status": "LOCAL_BLOCKED",
                "doctor_passed": False,
                "smoke_test": "not_run",
                "render_test": "not_run",
                "quality_tools": "blocked",
                "pdf_export": "not_run",
                "visual_render": "not_run",
            },
            {
                "local_status": "LOCAL_BLOCKED",
                "doctor_passed": True,
                "smoke_test": "failed",
                "render_test": "failed",
                "quality_tools": "ready",
                "pdf_export": "failed",
                "visual_render": "failed",
            },
        ):
            with self.subTest(local=local):
                report = self.report(local)
                self.assertEqual(report["state"], "BLOCKED")
                self.assertIn("full_quality_pipeline_failed", report["issues"])

    def test_wrong_environment_blocked(self):
        report = self.report(prefix=str(ROOT / "not-the-project-venv"))
        self.assertEqual(report["state"], "BLOCKED")
        self.assertIn("wrong_python_environment", report["issues"])

    def test_report_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            setup.save_report(self.report(), Path(temporary))
            report = json.loads(
                (Path(temporary) / ".skill-work/codex-setup.json").read_text()
            )
            self.assertNotIn(str(ROOT), json.dumps(report))
            self.assertFalse(
                list((Path(temporary) / ".skill-work").glob("*.tmp"))
            )


class DistributionTests(unittest.TestCase):
    def test_installers_and_quality_tool_are_in_release(self):
        from package_release import should_package

        for path in (
            "CODEX-START.md",
            "setup-codex.sh",
            "setup-codex.ps1",
            "tools/codex_setup.py",
            ".agents/skills/medical-journal-to-pptx-classroom/scripts/quality_tools.py",
        ):
            self.assertTrue(should_package(Path(path)), path)

    def test_no_package_manager_or_policy_bypass(self):
        for name in ("setup-codex.sh", "setup-codex.ps1"):
            data = (ROOT / name).read_text(encoding="utf-8").lower()
            for forbidden in (
                "sudo ",
                "brew install",
                "winget install",
                "set-executionpolicy",
                "-executionpolicy",
                "invoke-expression",
                "--insecure",
                "curl -k",
                "pip install --system",
            ):
                self.assertNotIn(forbidden, data)
            self.assertIn("quality_tools.py", data)
            self.assertNotIn("\\skils\\", data)

    def test_fixed_quality_assets_use_https_and_sha256(self):
        assets = [
            *(value[:2] for value in quality_tools.PIXI_ASSETS.values()),
            *((value[0], value[1]) for value in quality_tools.LIBREOFFICE_ASSETS.values()),
        ]
        for locator, digest in assets:
            with self.subTest(locator=locator):
                if locator.startswith("http"):
                    self.assertTrue(locator.startswith("https://"))
                self.assertRegex(digest, r"^[a-f0-9]{64}$")
        self.assertRegex(quality_tools.LIBREOFFICE_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertRegex(quality_tools.POPPLER_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertRegex(quality_tools.PIXI_VERSION, r"^\d+\.\d+\.\d+$")

    def test_bootstrap_artifacts_are_not_packaged(self):
        from package_release import should_package

        for path in (
            ".bootstrap/libreoffice/program/soffice",
            ".bootstrap/pixi-home/bin/pdftoppm",
            ".bootstrap/downloads/private.bin",
        ):
            self.assertFalse(should_package(Path(path)))


if __name__ == "__main__":
    unittest.main()
