#!/usr/bin/env python3
"""Local classroom gate. Never claims to verify a Codex account or quota."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "Python 3.11-3.13", "Repository skill", "Classroom skill version",
    "PyMuPDF", "python-pptx", "Pillow", "pdfplumber", "numpy",
    "Source papers", "Presentation outputs", "Private working files",
    "LibreOffice", "Poppler", "Codex desktop or CLI",
}


def run_json(arguments: list[str], timeout: int = 300) -> tuple[int, dict]:
    """Capture raw output only in memory; do not persist paths or exception text."""
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "classroom.py"), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
        data = json.loads(proc.stdout)
        return proc.returncode, data if isinstance(data, dict) else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1, {}


def collect_report() -> dict:
    doctor_code, doctor = run_json(["doctor", "--json"])
    checks = []
    raw_checks = doctor.get("checks", [])
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if not isinstance(item, dict) or item.get("label") not in LABELS:
                continue
            status = item.get("status")
            checks.append({"label": item["label"], "status": status if status in
                           {"ok", "warning", "error"} else "error"})
    doctor_ok = doctor_code == 0 and doctor.get("ok") is True and bool(checks)
    doctor_ok = doctor_ok and not any(x["status"] == "error" for x in checks)
    smoke_ok = False
    if doctor_ok:
        smoke_code, smoke = run_json(["smoke-test", "--json"])
        smoke_ok = smoke_code == 0 and smoke.get("ok") is True
    optional_missing = [x["label"] for x in checks if
                        x["label"] in {"LibreOffice", "Poppler"} and x["status"] != "ok"]
    local = "LOCAL_BLOCKED"
    if doctor_ok and smoke_ok:
        local = "LOCAL_PPTX_ONLY" if optional_missing else "LOCAL_READY"
    return {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "local_status": local,
        "doctor_passed": doctor_ok,
        "smoke_test": "passed" if smoke_ok else ("failed" if doctor_ok else "not_run"),
        "checks": checks,
        "optional_missing": optional_missing,
        "codex_status": "CODEX_UNVERIFIED",
        "account_login": "not_checked",
        "skill_loading": "not_checked",
        "local_agent_execution": "not_checked",
        "remaining_quota": "not_checked",
        "pdf_export": "not_tested",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / ".skill-work" / "classroom-preflight.json")
    args = parser.parse_args(argv)
    print("Checking local tools (no Codex model calls). Raw diagnostics stay private.")
    report = collect_report()
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("Could not save report. Check folder permissions; no account data was requested.")
        return 1
    for item in report["checks"]:
        print(f"[{item['status'].upper()}] {item['label']}")
    print(f"Local: {report['local_status']}")
    print(f"Smoke test: {report['smoke_test']}")
    print("Codex: CODEX_UNVERIFIED (manual read-skill + local doctor task required)")
    print("PDF export was not tested. Tool presence is not proof of successful rendering.")
    print("Read CODEX-START.md for the next step.")
    print("Default report: .skill-work/classroom-preflight.json (no raw paths or logs)")
    if report["local_status"] == "LOCAL_BLOCKED":
        print("Use the platform setup script or ask the instructor. Do not bypass device policy.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
