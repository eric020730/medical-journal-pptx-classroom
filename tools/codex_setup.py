#!/usr/bin/env python3
"""Verify the full local bootstrap; an agent must separately read SKILL.md."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = {
    "PyMuPDF": "pymupdf",
    "python-pptx": "pptx",
    "Pillow": "PIL",
    "pdfplumber": "pdfplumber",
    "numpy": "numpy",
}
SKILL = Path(".agents/skills/medical-journal-to-pptx-integrated")
REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "VERSION",
    "scripts/run.py",
    "scripts/workflow.py",
    "scripts/qa_gate.py",
    "scripts/qa_attestation.py",
    "scripts/render_attestation.py",
    "scripts/build_deck.py",
    "scripts/extract_from_pdf.py",
    "scripts/quality_tools.py",
    "scripts/quality_tools_windows.py",
    "references/full_workflow.md",
)


def numeric_version(text: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", text):
        raise ValueError("Only stable numeric versions are accepted by this bootstrap")
    values = tuple(int(part) for part in text.split("."))
    return values + (0,) * (4 - len(values))


def dependency_problems(root: Path = ROOT) -> list[str]:
    """Check every declared bound and import without running installers."""
    problems: list[str] = []
    seen: set[str] = set()
    for raw in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([\w-]+)(.+)", line)
        if not match or match[1] not in IMPORTS:
            problems.append("unsupported_requirement")
            continue
        name, bounds = match.groups()
        seen.add(name)
        try:
            actual = numeric_version(importlib.metadata.version(name))
            importlib.import_module(IMPORTS[name])
            for bound in bounds.split(","):
                part = re.fullmatch(r"(>=|<=|==|>|<)(\d+(?:\.\d+)*)", bound.strip())
                if not part:
                    raise ValueError("unsupported requirement bound")
                operator, version = part.groups()
                expected = numeric_version(version)
                valid = {
                    ">=": actual >= expected,
                    "<=": actual <= expected,
                    ">": actual > expected,
                    "<": actual < expected,
                    "==": actual == expected,
                }[operator]
                if not valid:
                    raise ValueError("version outside declared bounds")
        except Exception:
            problems.append(name)
    if seen != set(IMPORTS):
        problems.append("missing_requirement_declarations")
    return problems


def build_report(root: Path = ROOT) -> dict:
    result = {
        "schema_version": 2,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "BLOCKED",
        "skill_scope": "repository",
        "skill_read_by_agent": "not_attested",
        "account_quota": "not_checked",
        "pdf_export": "not_run",
        "visual_render": "not_run",
        "next_action": "resolve_blocker",
        "issues": [],
        "doctor_passed": False,
        "smoke_test": "not_run",
        "render_test": "not_run",
        "visual_review": "not_attested",
    }
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        result["issues"].append("wrong_python_environment")
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        result["issues"].append("unsupported_python")
    result["issues"].extend(dependency_problems(root))
    if any(not (root / SKILL / path).is_file() for path in REQUIRED_SKILL_FILES):
        result["issues"].append("incomplete_repository_skill")
    if result["issues"]:
        return result

    from classroom_preflight import collect_report

    local = collect_report()
    result["doctor_passed"] = local["doctor_passed"]
    result["smoke_test"] = local["smoke_test"]
    result["render_test"] = local["render_test"]
    result["pdf_export"] = local["pdf_export"]
    result["visual_render"] = local["visual_render"]
    result["quality_tools"] = local["quality_tools"]
    if local["local_status"] != "FULL_QA_READY":
        result["issues"].append("full_quality_pipeline_failed")
        return result

    result.update(
        state="FULL_QA_READY_SKILL_PENDING",
        next_action="read_repository_skill_then_request_pdf",
    )
    return result


def save_report(report: dict, root: Path = ROOT) -> None:
    directory = root / ".skill-work"
    if directory.is_symlink():
        raise ValueError("Refusing a symlink working directory")
    directory.mkdir(exist_ok=True)
    target = directory / "codex-setup.json"
    if target.is_symlink():
        raise ValueError("Refusing a symlink receipt")
    file_descriptor, temporary = tempfile.mkstemp(
        prefix="codex-setup-", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dependencies-ready", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.dependencies_ready:
        return 1 if dependency_problems() else 0
    report = build_report()
    save_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["state"] == "BLOCKED":
        print("SETUP_BLOCKED: inspect the named blocker. Do not request a student PDF.")
        return 1
    print("FULL_QA_READY_SKILL_PENDING: Codex must now read the repository SKILL.md.")
    print("The synthetic deck was rendered; no student article or account quota was tested.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(
            f"SETUP_BLOCKED: {type(error).__name__}; check the project and permissions.",
            file=sys.stderr,
        )
        raise SystemExit(1)
