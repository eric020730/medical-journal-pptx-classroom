"""Contract tests for full-quality student readiness."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "classroom_preflight", ROOT / "tools" / "classroom_preflight.py"
)
preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)


def doctor(*, quality_ok=True, ok=True):
    checks = [
        {"label": "Python 3.11-3.13", "status": "ok", "detail": "PRIVATE_PATH"},
        {"label": "Repository skill", "status": "ok"},
        {"label": "LibreOffice", "status": "ok" if quality_ok else "error"},
        {"label": "Poppler", "status": "ok" if quality_ok else "error"},
        {"label": "Codex desktop or CLI", "status": "warning"},
    ]
    return (
        0 if ok and quality_ok else 1,
        {"ok": ok and quality_ok, "checks": checks},
    )


def rendered_smoke(*, ok=True, rendered=True):
    payload = {"ok": ok, "styles": {
        style: {"ok": ok, "mode": "full", "style": style, "slides": 40,
                "prebuild_qa": True, "postbuild_qa": True, "image_polarity": True,
                "qa_receipt_current": True, "artifacts_verified": True,
                "render": {"pdf": "PRIVATE.pdf", "contact_sheet": "PRIVATE.jpg",
                           "preview_pages": 40} if rendered else {}}
        for style in ("standard", "nice")
    }}
    if rendered:
        payload["render"] = {
            "pdf": "PRIVATE_DEMO.pdf",
            "contact_sheet": "PRIVATE_CONTACT.jpg",
        }
    return (0 if ok else 1, payload)


class ReadinessTests(unittest.TestCase):
    def collect(self, values):
        with patch.object(preflight, "run_json", side_effect=values) as call:
            result = preflight.collect_report()
            return result, call.call_count

    def test_full_rendered_pipeline_is_ready_but_codex_is_unverified(self):
        report, calls = self.collect([doctor(), rendered_smoke()])
        self.assertEqual(calls, 2)
        self.assertEqual(report["local_status"], "FULL_QA_READY")
        self.assertEqual(report["render_test"], "passed")
        self.assertEqual(report["codex_status"], "CODEX_UNVERIFIED")
        self.assertEqual(report["remaining_quota"], "not_checked")

    def test_missing_libreoffice_or_poppler_blocks_before_smoke(self):
        report, calls = self.collect([doctor(quality_ok=False)])
        self.assertEqual(calls, 1)
        self.assertEqual(report["local_status"], "LOCAL_BLOCKED")
        self.assertEqual(report["smoke_test"], "not_run")

    def test_smoke_without_render_artifacts_is_blocked(self):
        report, calls = self.collect([doctor(), rendered_smoke(rendered=False)])
        self.assertEqual(calls, 2)
        self.assertEqual(report["local_status"], "LOCAL_BLOCKED")
        self.assertEqual(report["render_test"], "failed")

    def test_doctor_or_smoke_failure_is_blocked(self):
        doctor_report, doctor_calls = self.collect([doctor(ok=False)])
        self.assertEqual(doctor_calls, 1)
        self.assertEqual(doctor_report["local_status"], "LOCAL_BLOCKED")

        smoke_report, smoke_calls = self.collect([doctor(), rendered_smoke(ok=False)])
        self.assertEqual(smoke_calls, 2)
        self.assertEqual(smoke_report["local_status"], "LOCAL_BLOCKED")

    def test_no_raw_details_are_copied_to_receipt(self):
        report, _ = self.collect([doctor(), rendered_smoke()])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_empty_or_malformed_doctor_fails_closed(self):
        for response in ((0, {}), (0, {"ok": True, "checks": "bad"})):
            with self.subTest(response=response):
                report, calls = self.collect([response])
                self.assertEqual(calls, 1)
                self.assertEqual(report["local_status"], "LOCAL_BLOCKED")


if __name__ == "__main__":
    unittest.main()
