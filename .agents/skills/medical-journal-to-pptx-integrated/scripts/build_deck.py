#!/usr/bin/env python3
"""Build one canonical medical-journal deck in standard or nice visual style."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import build_deck_nice
import build_deck_standard


STYLE_IMAGE_BOXES = {
    "standard": {"width_in": 12.10, "height_in": 4.85},
    "nice": {"width_in": 12.13, "height_in": 4.95},
}


def normalize_specification(spec: dict[str, Any], *, style: str) -> dict[str, Any]:
    """Preserve canonical section types while adapting aliases for each builder."""
    if style == "standard":
        slides = []
        for slide in spec.get("slides", []):
            normalized = dict(slide)
            if normalized.get("type") == "section":
                normalized["type"] = "part"
            slides.append(normalized)
        return {**spec, "slides": slides}

    if style != "nice":
        raise ValueError(f"Unknown visual style: {style}")
    slides = []
    for slide in spec.get("slides", []):
        normalized = dict(slide)
        slide_type = normalized.get("type")
        if slide_type == "part":
            normalized["type"] = "section"
            number = normalized.get("number")
            if isinstance(number, int):
                normalized["number"] = f"{number:02d}"
        elif slide_type in {"outline", "references"}:
            normalized["type"] = "content"
            normalized.setdefault("body", normalized.get("items", []))
            normalized.setdefault(
                "kicker", "LEARNING OUTLINE" if slide_type == "outline" else "KEY REFERENCES"
            )
        slides.append(normalized)
    return {**spec, "slides": slides}


def build(
    spec_path: Path,
    destination: Path,
    *,
    style: str = "standard",
    allow_unprocessed_assets: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    spec_path = spec_path.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"Presentation already exists: {destination}. Choose a new path or use --overwrite."
        )
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    if not allow_unprocessed_assets:
        build_deck_standard.require_postprocessed_figure_assets(specification, spec_path.parent)

    normalized = normalize_specification(specification, style=style)
    if style == "standard":
        # Underlying builders print logo diagnostics; keep machine-readable JSON clean.
        with contextlib.redirect_stdout(sys.stderr):
            presentation = build_deck_standard.build(
                normalized,
                spec_path.parent,
                require_processed_assets=not allow_unprocessed_assets,
            )
    else:
        logo = build_deck_nice.resolve_logo(normalized.get("meta", {}), spec_path.parent)
        if logo is None:
            raise RuntimeError("The bundled presentation logo is missing.")
        presentation = build_deck_nice.Builder(
            normalized, os.fspath(spec_path.parent), logo
        ).build()

    destination.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(os.fspath(destination))
    return {
        "pptx": str(destination),
        "style": style,
        "slides": len(presentation.slides),
        "image_box": STYLE_IMAGE_BOXES[style],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--style", choices=("standard", "nice"), default="standard")
    parser.add_argument("--allow-unprocessed-assets", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build(
        args.spec,
        args.out,
        style=args.style,
        allow_unprocessed_assets=args.allow_unprocessed_assets,
        overwrite=args.overwrite,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"saved {payload['pptx']} ({payload['slides']} slides; {args.style} style)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
