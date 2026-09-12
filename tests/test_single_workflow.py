"""The shipped project has one complete route and no stale teaching links."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
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
    def test_exactly_one_discoverable_skill(self):
        skills = list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
        self.assertEqual([p.parent.name for p in skills], ["medical-journal-to-pptx-classroom"])

    def test_only_required_student_documents_remain(self):
        self.assertEqual({p.name for p in (ROOT / "docs").iterdir() if p.is_file()},
                         {"PRIVACY.md", "TROUBLESHOOTING.md"})
        self.assertEqual({p.name for p in ROOT.glob("setup-*")},
                         {"setup-codex.sh", "setup-codex.ps1"})
        self.assertEqual(list(ROOT.glob("install-global*")), [])

    def test_current_markdown_links_resolve(self):
        for p in [ROOT / "README.md", ROOT / "CODEX-START.md", *list((ROOT / "docs").glob("*.md"))]:
            for target in re.findall(r"\]\(([^)]+)\)", p.read_text(encoding="utf-8")):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((p.parent / target.split("#")[0]).is_file(), (p.name, target))

    def test_launchers_and_skill_reference_existing_setup(self):
        for name in ("journal", "journal.cmd", ".agents/skills/medical-journal-to-pptx-classroom/SKILL.md"):
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
            for name in ("VERSION", ".classroom-project.json"):
                shutil.copyfile(ROOT / name, root / name)
            (root / "VERSION").write_text("9.8.7\n", encoding="utf-8")
            self.assertEqual(release_version.synchronize(root), [".classroom-project.json"])
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
                manifest = z.read(prefix + "RELEASE-MANIFEST.txt").decode()
                for line in manifest.splitlines():
                    if re.match(r"^[a-f0-9]{64}  ", line):
                        digest, name = line.split("  ", 1)
                        self.assertEqual(hashlib.sha256(z.read(prefix + name)).hexdigest(), digest)
                self.assertFalse(any("install-global" in name or ".bootstrap/" in name for name in names))

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
