"""Contract tests for student readiness. No model calls or private data."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("classroom_preflight", ROOT / "tools" / "classroom_preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def doctor(*, optional=False, ok=True):
    return (0 if ok else 1, {"ok": ok, "checks": [
        {"label": "Python 3.11-3.13", "status": "ok", "detail": "PRIVATE_ACCOUNT_PATH"},
        {"label": "LibreOffice", "status": "warning" if optional else "ok"},
        {"label": "Poppler", "status": "ok"},
        {"label": "Codex desktop or CLI", "status": "warning"},
    ]})


class ReadinessTests(unittest.TestCase):
    def collect(self, values):
        with patch.object(preflight, "run_json", side_effect=values) as call:
            result = preflight.collect_report()
            return result, call.call_count

    def test_local_ready_still_requires_codex(self):
        r, _ = self.collect([doctor(), (0, {"ok": True})])
        self.assertEqual(r["local_status"], "LOCAL_READY")
        self.assertEqual(r["codex_status"], "CODEX_UNVERIFIED")
        self.assertEqual(r["remaining_quota"], "not_checked")
        self.assertEqual(r["pdf_export"], "not_tested")

    def test_optional_tools_do_not_block_pptx(self):
        r, _ = self.collect([doctor(optional=True), (0, {"ok": True})])
        self.assertEqual(r["local_status"], "LOCAL_PPTX_ONLY")

    def test_doctor_failure_skips_smoke(self):
        r, calls = self.collect([doctor(ok=False)])
        self.assertEqual(calls, 1)
        self.assertEqual(r["smoke_test"], "not_run")
        self.assertEqual(r["local_status"], "LOCAL_BLOCKED")

    def test_empty_doctor_is_not_success(self):
        r, calls = self.collect([(0, {})])
        self.assertEqual(calls, 1)
        self.assertFalse(r["doctor_passed"])

    def test_smoke_failure_is_not_ready(self):
        r, _ = self.collect([doctor(), (1, {"ok": False})])
        self.assertEqual(r["local_status"], "LOCAL_BLOCKED")

    def test_no_raw_details_in_report(self):
        r, _ = self.collect([doctor(), (0, {"ok": True, "work_dir": "PRIVATE_SMOKE_PATH"})])
        self.assertNotIn("PRIVATE", json.dumps(r))

    def test_unknown_labels_are_not_copied(self):
        code, data = doctor()
        data["checks"].append({"label": "PERSONAL_NAME", "status": "ok"})
        r, _ = self.collect([(code, data), (0, {"ok": True})])
        self.assertNotIn("PERSONAL_NAME", json.dumps(r))

    def test_error_check_cannot_be_promoted(self):
        code, data = doctor()
        data["checks"].append({"label": "Pillow", "status": "error"})
        r, calls = self.collect([(code, data)])
        self.assertEqual(calls, 1)
        self.assertFalse(r["doctor_passed"])

    def test_malformed_checks_fail_closed(self):
        r, calls = self.collect([(0, {"ok": True, "checks": "bad"})])
        self.assertEqual(calls, 1)
        self.assertEqual(r["local_status"], "LOCAL_BLOCKED")


if __name__ == "__main__":
    unittest.main()
