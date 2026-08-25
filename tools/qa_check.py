#!/usr/bin/env python3
"""Validate classroom PowerPoint outputs using observable presentation data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT_ROOT / ".classroom-project.json").read_text(encoding="utf-8"))
SKILL_ROOT = PROJECT_ROOT / ".agents" / "skills" / CONFIG["skill_name"]
LOGO_PATH = SKILL_ROOT / "assets" / "dr_leether_logo.png"
CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
FIGURE_RE = re.compile(r"\bfig(?:ure)?\.?\s*(\d+)\b", re.IGNORECASE)
EMOJI_RANGES = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF))


def has_emoji(text: str) -> bool:
    return any(any(start <= ord(character) <= end for start, end in EMOJI_RANGES)
               for character in text)


def visible_texts(slide: Any) -> list[str]:
    texts: list[str] = []
    for shape in slide.shapes:
        if getattr(shape, "has_text_frame", False):
            text = shape.text_frame.text.strip()
            if text:
                texts.append(text)
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        texts.append(cell.text.strip())
    return texts


def logo_hash() -> str | None:
    if not LOGO_PATH.is_file():
        return None
    return hashlib.sha256(LOGO_PATH.read_bytes()).hexdigest()


def slide_has_logo(slide: Any, expected_hash: str) -> bool:
    for shape in slide.shapes:
        if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
            continue
        try:
            if hashlib.sha256(shape.image.blob).hexdigest() == expected_hash:
                return True
        except (AttributeError, ValueError):
            continue
    return False


def validate_presentation(
    pptx_path: Path,
    *,
    spec_path: Path | None = None,
    mode: str = "lite",
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if not pptx_path.is_file():
        return {"ok": False, "failures": [f"Presentation not found: {pptx_path}"], "warnings": []}

    try:
        presentation = Presentation(str(pptx_path))
    except Exception as error:
        return {"ok": False, "failures": [f"PowerPoint cannot be opened: {error}"], "warnings": []}

    slides = list(presentation.slides)
    count = len(slides)
    if not slides:
        failures.append("Presentation does not contain any slides.")

    if mode in CONFIG["modes"]:
        limits = CONFIG["modes"][mode]
        if not limits["minimum_slides"] <= count <= limits["maximum_slides"]:
            failures.append(
                f"{mode} mode expects {limits['minimum_slides']}-{limits['maximum_slides']} "
                f"slides but the presentation contains {count}."
            )
    elif mode != "smoke":
        failures.append(f"Unknown QA mode: {mode}")

    width, height = int(presentation.slide_width), int(presentation.slide_height)
    if height <= 0 or abs(width / height - 16 / 9) > 0.03:
        failures.append(f"Presentation is not widescreen 16:9 ({width} × {height}).")

    spec: dict[str, Any] | None = None
    spec_slides: list[dict[str, Any]] = []
    if spec_path is not None:
        if not spec_path.is_file():
            failures.append(f"Deck specification not found: {spec_path}")
        else:
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                spec_slides = list(spec.get("slides", []))
            except (json.JSONDecodeError, OSError, TypeError) as error:
                failures.append(f"Deck specification is invalid: {error}")
            if spec is not None and len(spec_slides) != count:
                failures.append(
                    f"Deck specification contains {len(spec_slides)} slides, "
                    f"but the PowerPoint contains {count}."
                )

    expected_logo = logo_hash()
    if expected_logo is None:
        failures.append(f"Bundled presentation logo is missing: {LOGO_PATH}")

    note_count = 0
    emoji_note_count = 0
    logo_count = 0
    visible_cjk_slides: list[int] = []
    for index, slide in enumerate(slides, start=1):
        for text in visible_texts(slide):
            if CHINESE_RE.search(text):
                visible_cjk_slides.append(index)
                break

        try:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        except (AttributeError, ValueError):
            notes = ""
        if not notes:
            failures.append(f"Slide {index} has no speaker notes.")
        else:
            note_count += 1
            if not CHINESE_RE.search(notes):
                failures.append(f"Slide {index} speaker notes contain no Chinese text.")
            if "**" in notes:
                failures.append(f"Slide {index} speaker notes contain unrendered ** markup.")
            if has_emoji(notes):
                emoji_note_count += 1

        if expected_logo and slide_has_logo(slide, expected_logo):
            logo_count += 1
            present_logo = True
        else:
            present_logo = False

        if index <= len(spec_slides):
            slide_type = spec_slides[index - 1].get("type")
            if slide_type not in {"title", "thanks"} and not present_logo:
                failures.append(f"Slide {index} ({slide_type}) does not contain the bundled logo.")

    if visible_cjk_slides:
        failures.append(
            "English-only slide text contains Chinese on slide(s): "
            + ", ".join(str(index) for index in visible_cjk_slides)
        )
    if slides and emoji_note_count == 0:
        failures.append("Speaker notes do not contain any structural emoji markers.")

    if spec is not None and spec_path is not None:
        type_counts: dict[str, int] = {}
        figure_numbers: dict[str, list[int]] = {}
        for index, entry in enumerate(spec_slides, start=1):
            slide_type = str(entry.get("type", "missing"))
            type_counts[slide_type] = type_counts.get(slide_type, 0) + 1
            if slide_type != "figure":
                continue

            image_name = entry.get("image")
            if not image_name:
                failures.append(f"Figure slide {index} does not reference an image.")
                continue
            image = Path(str(image_name))
            if not image.is_absolute():
                image = (spec_path.parent / image).resolve()
            if not image.is_file():
                failures.append(f"Figure slide {index} image is missing: {image}")
                continue
            if image.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                sidecar = image.with_suffix(image.suffix + ".postprocess.json")
                if not sidecar.is_file():
                    failures.append(f"Figure slide {index} is missing its image sidecar: {sidecar}")
            if re.search(r"(?:^|[_-])panel[_-]?[a-z0-9]+$", image.stem, re.IGNORECASE):
                failures.append(f"Figure slide {index} references a panel fragment: {image.name}")

            caption = f"{entry.get('caption', '')} {entry.get('title', '')}"
            if not re.search(r"\btable\b", caption, re.IGNORECASE):
                match = FIGURE_RE.search(caption)
                if match:
                    figure_numbers.setdefault(match.group(1), []).append(index)

        if type_counts.get("title", 0) != 1:
            failures.append(f"Expected exactly one title slide; found {type_counts.get('title', 0)}.")
        if type_counts.get("thanks", 0) != 1:
            failures.append(f"Expected exactly one closing slide; found {type_counts.get('thanks', 0)}.")
        if type_counts.get("content", 0) == 0:
            failures.append("Presentation contains no teaching-content slides.")
        for number, slide_indexes in sorted(figure_numbers.items()):
            if len(slide_indexes) > 1:
                failures.append(
                    f"Paper Figure {number} appears on multiple slides: "
                    + ", ".join(str(index) for index in slide_indexes)
                )
    elif count > 2 and logo_count == 0:
        failures.append("No embedded presentation logo was found.")

    return {
        "ok": not failures,
        "pptx": str(pptx_path),
        "spec": str(spec_path) if spec_path else None,
        "mode": mode,
        "slides": count,
        "slides_with_notes": note_count,
        "slides_with_emoji_notes": emoji_note_count,
        "slides_with_logo": logo_count,
        "failures": failures,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--mode", choices=("lite", "full", "smoke"), default="lite")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = validate_presentation(
        args.pptx.expanduser().resolve(),
        spec_path=args.spec.expanduser().resolve() if args.spec else None,
        mode=args.mode,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if "slides" in report:
            print(
                f"Slides: {report['slides']} | Notes: {report['slides_with_notes']} | "
                f"Logo: {report['slides_with_logo']} | Mode: {report['mode']}"
            )
        for failure in report["failures"]:
            print(f"[FAIL] {failure}", file=sys.stderr)
        for warning in report["warnings"]:
            print(f"[WARN] {warning}", file=sys.stderr)
        print("Presentation QA passed." if report["ok"] else "Presentation QA failed.")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
