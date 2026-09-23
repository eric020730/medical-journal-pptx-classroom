"""The shipped classroom route stays simple while the global skill remains releasable."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package_release
import release_version


class SingleWorkflowTests(unittest.TestCase):
    def test_only_integrated_skill_is_discoverable(self):
        skills = list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
        self.assertEqual(
            {p.parent.name for p in skills},
            {"medical-journal-to-pptx-integrated"},
        )

    def test_only_required_student_documents_remain(self):
        self.assertEqual({p.name for p in (ROOT / "docs").iterdir() if p.is_file()},
                         {"PRIVACY.md", "TROUBLESHOOTING.md", "GLOBAL-INSTALL.md"})
        self.assertEqual({p.name for p in ROOT.glob("setup-*")},
                         {"setup-codex.sh", "setup-codex.ps1"})
        self.assertEqual(
            {p.name for p in ROOT.glob("install-global*")},
            {"install-global.py", "install-global.sh", "install-global.ps1", "install-global.cmd"},
        )

    def test_current_markdown_links_resolve(self):
        for p in [ROOT / "README.md", ROOT / "CODEX-START.md", *list((ROOT / "docs").glob("*.md"))]:
            for target in re.findall(r"\]\(([^)]+)\)", p.read_text(encoding="utf-8")):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((p.parent / target.split("#")[0]).is_file(), (p.name, target))

    def test_launchers_and_skill_reference_existing_setup(self):
        for name in ("journal", "journal.cmd", ".agents/skills/medical-journal-to-pptx-integrated/SKILL.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for old in ("setup-" + "macos.command", "setup-" + "windows.cmd"):
                self.assertNotIn(old, text)
            self.assertIn("setup-codex", text)

    def test_main_url_and_consent_are_documented(self):
        text = (ROOT / "CODEX-START.md").read_text(encoding="utf-8")
        for expected in ("一般專案首頁", "`main`", "只有貼網址", "已有明確安裝", "收到檔案後直接接續製作"):
            self.assertIn(expected, text)
        self.assertNotIn("teaching/", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_version_drift_blocks_packaging_and_is_repairable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "VERSION", ".classroom-project.json", "README.md", "docs/GLOBAL-INSTALL.md",
                ".agents/skills/medical-journal-to-pptx-integrated/SKILL.md",
                ".agents/skills/medical-journal-to-pptx-integrated/VERSION",
            ):
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            (root / "VERSION").write_text("9.8.7\n", encoding="utf-8")
            (root / ".agents/skills/medical-journal-to-pptx-integrated/VERSION").write_text(
                "v9.8.7\n", encoding="utf-8"
            )
            self.assertEqual(
                set(release_version.synchronize(root)),
                {".classroom-project.json", "docs/GLOBAL-INSTALL.md"},
            )
            with mock.patch.object(package_release, "PROJECT_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "metadata is stale"):
                    package_release.create_release(root / "blocked.zip")
            release_version.synchronize(root, write=True)
            self.assertEqual(release_version.synchronize(root), [])
            self.assertEqual(release_version.metadata(root)["archive"], "medical-journal-pptx-classroom-v9.8.7.zip")
            (root / "VERSION").write_text("not-a-version", encoding="utf-8")
            with self.assertRaises(ValueError):
                release_version.metadata(root)

    def test_archive_is_complete_and_all_manifest_hashes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = package_release.create_release(Path(tmp) / "project.zip")
            with zipfile.ZipFile(result["archive"]) as z:
                names = z.namelist()
                self.assertEqual(sum(name.endswith("/SKILL.md") for name in names), 1)
                self.assertTrue(any(name.endswith("/setup-codex.sh") for name in names))
                self.assertTrue(any(name.endswith("/setup-codex.ps1") for name in names))
                prefix = "medical-journal-pptx-classroom/"
                for core in ("run.py", "workflow.py", "qa_check.py", "qa_attestation.py",
                             "render_attestation.py", "notes_quality.py", "article_asset_map.py",
                             "source_crops.py", "quality_tools.py", "quality_tools_windows.py"):
                    self.assertIn(prefix + ".agents/skills/medical-journal-to-pptx-integrated/scripts/" + core, names)
                self.assertNotIn(prefix + "tools/qa_check.py", names)
                self.assertNotIn(prefix + "tools/image_polarity.py", names)
                self.assertFalse(any("tests/fixtures/" in name for name in names))
                manifest = z.read(prefix + "RELEASE-MANIFEST.txt").decode()
                for line in manifest.splitlines():
                    if re.match(r"^[a-f0-9]{64}  ", line):
                        digest, name = line.split("  ", 1)
                        self.assertEqual(hashlib.sha256(z.read(prefix + name)).hexdigest(), digest)
                self.assertFalse(any("install-global" in name or ".bootstrap/" in name for name in names))

    def test_extracted_classroom_archive_can_check_version_and_repackage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = package_release.create_release(root / "original.zip")
            with zipfile.ZipFile(result["archive"]) as archive:
                archive.extractall(root / "extracted")
            shipped = root / "extracted/medical-journal-pptx-classroom"
            for command in (["tools/release_version.py"],
                            ["tools/package_release.py", "--out", str(root / "repacked.zip")]):
                completed = subprocess.run([sys.executable, *command], cwd=shipped,
                                           text=True, capture_output=True)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue((root / "repacked.zip").is_file())

    def test_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = package_release.create_release(Path(tmp) / "one.zip")
            two = package_release.create_release(Path(tmp) / "two.zip")
            self.assertEqual(one["sha256"], two["sha256"])

    def test_unknown_private_files_are_not_shipped(self):
        for name in ("docs/patient.txt", "tools/patient.py", ".bootstrap/python/bin/python", "sample-papers/private.pdf", "outputs/my.pptx"):
            self.assertFalse(package_release.should_package(Path(name)))


if __name__ == "__main__":
    unittest.main()
