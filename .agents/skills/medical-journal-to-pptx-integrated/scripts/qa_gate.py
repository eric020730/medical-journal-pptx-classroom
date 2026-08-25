#!/usr/bin/env python3
"""Enforce deck, PDF-polarity, bilingual, asset, and presentation quality gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import deck_quality
import qa_check


def check_specification(spec: Path, *, mode: str, style: str) -> dict[str, Any]:
    """Run both independent prebuild validators against one canonical spec."""
    integrated = qa_check.validate_specification(spec, mode=mode)
    report = deck_quality.Report()
    if integrated.get("stage") == "specification":
        try:
            deck_quality.check_spec(spec, report, content_mode=mode, style=style)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report.fail("deck_specification", str(error), "Repair the JSON deck specification.")

    failures = list(dict.fromkeys([
        *integrated.get("failures", []),
        *(message for level, _, message, _ in report.items if level == "FAIL"),
    ]))
    warnings = list(dict.fromkeys([
        *integrated.get("warnings", []),
        *(message for level, _, message, _ in report.items if level == "WARN"),
    ]))
    return {
        "ok": not failures,
        "stage": "specification",
        "spec": str(spec),
        "mode": mode,
        "style": style,
        "slides": integrated.get("slides"),
        "image_polarity": integrated.get("image_polarity"),
        "failures": failures,
        "warnings": warnings,
        "deck_checks": [
            {"level": level, "check": check, "message": message, "fix": fix}
            for level, check, message, fix in report.items
        ],
    }


def check_presentation(
    pptx: Path, *, spec: Path | None, mode: str, style: str
) -> dict[str, Any]:
    """Run independent built-file and teaching-presentation validators."""
    integrated = qa_check.validate_presentation(pptx, spec_path=spec, mode=mode)
    report = deck_quality.Report()
    if integrated.get("stage") == "presentation":
        try:
            deck_quality.check_pptx(
                pptx, report, spec, content_mode=mode, style=style
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            report.fail("deck_presentation", str(error), "Rebuild the damaged PowerPoint.")

    failures = list(dict.fromkeys([
        *integrated.get("failures", []),
        *(message for level, _, message, _ in report.items if level == "FAIL"),
    ]))
    warnings = list(dict.fromkeys([
        *integrated.get("warnings", []),
        *(message for level, _, message, _ in report.items if level == "WARN"),
    ]))
    return {
        **integrated,
        "ok": not failures,
        "style": style,
        "failures": failures,
        "warnings": warnings,
        "deck_checks": [
            {"level": level, "check": check, "message": message, "fix": fix}
            for level, check, message, fix in report.items
        ],
    }


def check_all(spec: Path, pptx: Path, *, mode: str, style: str) -> dict[str, Any]:
    before = check_specification(spec, mode=mode, style=style)
    after = check_presentation(pptx, spec=spec, mode=mode, style=style)
    failures = list(dict.fromkeys([*before["failures"], *after["failures"]]))
    warnings = list(dict.fromkeys([*before["warnings"], *after["warnings"]]))
    return {
        "ok": not failures,
        "stage": "all",
        "mode": mode,
        "style": style,
        "spec": str(spec),
        "pptx": str(pptx),
        "slides": after.get("slides"),
        "image_polarity": before.get("image_polarity"),
        "failures": failures,
        "warnings": warnings,
        "specification": before,
        "presentation": after,
    }


def print_report(report: dict[str, Any]) -> None:
    print(
        f"Integrated {report['stage']} QA | mode={report['mode']} | "
        f"style={report['style']} | slides={report.get('slides', 'unknown')}"
    )
    polarity = report.get("image_polarity")
    if polarity:
        print(
            "PDF image polarity: "
            f"{polarity['checked_figures']} checked; "
            f"{polarity['unsafe_raw_streams']} inverted raw stream(s) isolated."
        )
    for failure in report.get("failures", []):
        print(f"[FAIL] {failure}", file=sys.stderr)
    for warning in report.get("warnings", []):
        print(f"[WARN] {warning}", file=sys.stderr)
    print("RESULT: PASSES gate." if report["ok"] else "RESULT: NOT READY.")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    stages = command.add_subparsers(dest="stage", required=True)
    prebuild = stages.add_parser("spec", help="Validate a deck before building")
    prebuild.add_argument("spec", type=Path)
    built = stages.add_parser("pptx", help="Validate a built PowerPoint")
    built.add_argument("pptx", type=Path)
    built.add_argument("--spec", type=Path)
    combined = stages.add_parser("all", help="Run both required quality stages")
    combined.add_argument("spec", type=Path)
    combined.add_argument("--pptx", type=Path, required=True)
    for stage in (prebuild, built, combined):
        stage.add_argument("--mode", choices=("full",), default="full")
        stage.add_argument("--style", choices=("standard", "nice"), default="standard")
        stage.add_argument("--json", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.stage == "spec":
        report = check_specification(args.spec.resolve(), mode=args.mode, style=args.style)
    elif args.stage == "pptx":
        report = check_presentation(
            args.pptx.resolve(),
            spec=args.spec.resolve() if args.spec else None,
            mode=args.mode,
            style=args.style,
        )
    else:
        report = check_all(args.spec.resolve(), args.pptx.resolve(), mode=args.mode, style=args.style)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
