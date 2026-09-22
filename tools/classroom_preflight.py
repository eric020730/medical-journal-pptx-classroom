#!/usr/bin/env python3
"""Fail-closed full-quality local gate; never verifies Codex login or quota."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "Python 3.11-3.13", "Project Python environment", "Repository skill", "Classroom skill version",
    "PyMuPDF", "python-pptx", "Pillow", "pdfplumber", "numpy",
    "Source papers", "Presentation outputs", "Private working files",
    "LibreOffice", "Poppler", "Codex desktop or CLI",
}


def run_json(arguments: list[str], timeout: int = 900) -> tuple[int, dict]:
    """Capture raw output only in memory; do not persist paths or exception text."""
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "classroom.py"), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        data = json.loads(proc.stdout)
        return proc.returncode, data if isinstance(data, dict) else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1, {}


def integrated_smoke_ready(smoke: dict) -> bool:
    """A short/partial/one-style smoke cannot attest the full student workflow."""
    styles = smoke.get("styles")
    if not isinstance(styles, dict) or set(styles) != {"standard", "nice"}:
        return False
    for style, report in styles.items():
        if not isinstance(report, dict):
            return False
        render = report.get("render")
        if (report.get("ok") is not True or report.get("style") != style
                or report.get("mode") != "full" or report.get("slides") != 40
                or report.get("prebuild_qa") is not True
                or report.get("postbuild_qa") is not True
                or report.get("image_polarity") is not True
                or report.get("qa_receipt_current") is not True
                or report.get("artifacts_verified") is not True
                or not isinstance(render, dict) or not render.get("pdf")
                or not render.get("contact_sheet") or render.get("preview_pages") != 40):
            return False
    return True


def collect_report() -> dict:
    doctor_code, doctor = run_json(["doctor", "--strict", "--json"])
    checks: list[dict[str, str]] = []
    raw_checks = doctor.get("checks", [])
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if not isinstance(item, dict) or item.get("label") not in LABELS:
                continue
            status = item.get("status")
            checks.append(
                {
                    "label": item["label"],
                    "status": status if status in {"ok", "warning", "error"} else "error",
                }
            )

    doctor_ok = doctor_code == 0 and doctor.get("ok") is True and bool(checks)
    doctor_ok = doctor_ok and not any(item["status"] == "error" for item in checks)
    native_ok = all(
        any(item["label"] == label and item["status"] == "ok" for item in checks)
        for label in ("LibreOffice", "Poppler")
    )

    smoke_ok = False
    render_ok = False
    if doctor_ok and native_ok:
        smoke_code, smoke = run_json(["smoke-test", "--render", "--json"])
        render = smoke.get("render")
        render_artifacts = (
            isinstance(render, dict)
            and bool(render.get("pdf"))
            and bool(render.get("contact_sheet"))
        )
        smoke_ok = smoke_code == 0 and smoke.get("ok") is True and render_artifacts and integrated_smoke_ready(smoke)
        render_ok = smoke_ok

    full_ready = doctor_ok and native_ok and smoke_ok and render_ok
    return {
        "schema_version": 3,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "local_status": "FULL_QA_READY" if full_ready else "LOCAL_BLOCKED",
        "doctor_passed": doctor_ok and native_ok,
        "integrated_styles": ["standard", "nice"] if smoke_ok else [],
        "slides_per_style": 40 if smoke_ok else None,
        "visual_review": "not_attested",
        "smoke_test": "passed" if smoke_ok else (
            "failed" if doctor_ok and native_ok else "not_run"
        ),
        "render_test": "passed" if render_ok else (
            "failed" if doctor_ok and native_ok else "not_run"
        ),
        "checks": checks,
        "quality_tools": "ready" if native_ok else "blocked",
        "codex_status": "CODEX_UNVERIFIED",
        "account_login": "not_checked",
        "skill_loading": "not_checked",
        "local_agent_execution": "not_checked",
        "remaining_quota": "not_checked",
        "pdf_export": "passed" if render_ok else (
            "failed" if doctor_ok and native_ok else "not_run"
        ),
        "visual_render": "passed" if render_ok else (
            "failed" if doctor_ok and native_ok else "not_run"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / ".skill-work" / "classroom-preflight.json",
    )
    args = parser.parse_args(argv)
    print("Checking the full local pipeline, including rendered visual QA.")
    report = collect_report()
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        print("Could not save report. Check folder permissions; no account data was requested.")
        return 1
    for item in report["checks"]:
        print(f"[{item['status'].upper()}] {item['label']}")
    print(f"Local: {report['local_status']}")
    print(f"Synthetic build: {report['smoke_test']}")
    print(f"PPTX → PDF → preview render: {report['render_test']}")
    print("Codex: CODEX_UNVERIFIED; the agent must still read the complete repository skill.")
    print("Default report: .skill-work/classroom-preflight.json (no raw paths or logs)")
    if report["local_status"] != "FULL_QA_READY":
        print("Full-quality setup is blocked. Do not continue with a student article.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
