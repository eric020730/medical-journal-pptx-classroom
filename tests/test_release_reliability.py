from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import release_version
import package_release
from check_clean_install import minimum_constraints

SCRIPT = ROOT / ".agents/skills/medical-journal-to-pptx-integrated/scripts/qa_attestation.py"
spec = importlib.util.spec_from_file_location("qa_receipt_test", SCRIPT)
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)


class ReleaseVersionTests(unittest.TestCase):
    def test_drift_blocks_check_and_sync_repairs_only_current_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("VERSION", ".classroom-project.json", *release_version.DOCUMENTS,
                         ".agents/skills/medical-journal-to-pptx-integrated/SKILL.md",
                         ".agents/skills/medical-journal-to-pptx-integrated/VERSION"):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            version = root / ".agents/skills/medical-journal-to-pptx-integrated/VERSION"
            version.write_text("v9.8.7\n", encoding="utf-8")
            (root / "VERSION").write_text("9.8.7\n", encoding="utf-8")
            history = root / "history.md"
            history.write_text("Historical v4.3.4\n", encoding="utf-8")
            self.assertEqual(
                set(release_version.synchronize(root)),
                {".classroom-project.json", "docs/GLOBAL-INSTALL.md"},
            )
            with mock.patch.object(package_release, "PROJECT_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "metadata is stale"):
                    package_release.create_skill_release(root / "blocked.zip")
            self.assertFalse((root / "blocked.zip").exists())
            release_version.synchronize(root, write=True)
            self.assertEqual(release_version.synchronize(root), [])
            self.assertEqual(
                release_version.metadata(root)["skill_archive"],
                "medical-journal-to-pptx-integrated-v9.8.7.zip",
            )
            self.assertEqual(history.read_text(encoding="utf-8"), "Historical v4.3.4\n")
            config = json.loads((root / ".classroom-project.json").read_text(encoding="utf-8"))
            self.assertEqual(config["classroom_skill_version"], "v0.2.38-bg-aware-trim")
            version.write_text("v9.8.7-local\n", encoding="utf-8")
            self.assertEqual(release_version.metadata(root)["tag"], "v9.8.7")
            release_version.synchronize(root, write=True)
            self.assertEqual(release_version.synchronize(root), [])
            version.write_text("not-a-version", encoding="utf-8")
            with self.assertRaises(ValueError):
                release_version.metadata(root)

    def test_minimum_profile_pins_every_declared_dependency(self):
        self.assertEqual(minimum_constraints("# comment\nPillow>=10,<14\nnumpy>=1.26,<3\n"),
                         "Pillow==10\nnumpy==1.26\n")
        with self.assertRaises(ValueError):
            minimum_constraints("unbounded-package")


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pptx = self.root / "deck.pptx"
        self.deck_spec = self.root / "spec.json"
        self.pptx.write_bytes(b"original deck")
        self.deck_spec.write_text("{}", encoding="utf-8")

    def validate(self, ok=True):
        return {"ok": ok, "slides": 40, "failures": [] if ok else ["failed gate"], "warnings": []}

    def record(self, validator=None):
        return receipt.record_qa(self.pptx, self.deck_spec, mode="full", style="standard",
                                 validate=validator or self.validate)

    def status(self):
        return receipt.status(self.pptx, self.deck_spec)

    def test_no_record_is_unverified_and_pass_contains_no_private_paths(self):
        self.assertEqual(self.status()["status"], "unverified")
        self.record()
        self.assertEqual(self.status()["status"], "current")
        text = receipt.receipt_path(self.pptx).read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)
        self.assertIs(json.loads(text)["signed"], False)

    def test_deck_spec_and_validator_changes_invalidate_pass(self):
        self.record()
        self.pptx.write_bytes(b"edited slide")
        self.assertEqual(self.status()["status"], "stale")
        self.record()
        self.deck_spec.write_text('{"changed": true}', encoding="utf-8")
        self.assertEqual(self.status()["status"], "stale")
        self.record()
        with mock.patch.object(receipt, "validator_digest", return_value="0" * 64):
            self.assertEqual(self.status()["status"], "stale")

    def test_failed_and_interrupted_retries_invalidate_previous_pass(self):
        self.record()
        self.record(lambda: self.validate(False))
        self.assertFalse(self.status()["ok"])
        self.record()
        def fail():
            raise RuntimeError("interrupted QA")
        with self.assertRaises(RuntimeError):
            self.record(fail)
        self.assertFalse(self.status()["ok"])

    def test_edit_during_gate_is_not_attested(self):
        def change():
            self.pptx.write_bytes(b"edited while validating")
            return self.validate()
        result = self.record(change)
        self.assertFalse(result["ok"])
        self.assertFalse(self.status()["ok"])

    def test_corrupt_receipt_missing_input_and_wrong_style_fail_closed(self):
        path = receipt.receipt_path(self.pptx)
        for value in ("{", "[]", '{"schema":true}', '{"schema":1,"result":"passed"}'):
            path.write_text(value, encoding="utf-8")
            self.assertFalse(self.status()["ok"])
        self.record()
        self.assertFalse(receipt.status(self.pptx, self.deck_spec, style="nice")["ok"])
        self.deck_spec.unlink()
        self.assertFalse(self.status()["ok"])


if __name__ == "__main__":
    unittest.main()
