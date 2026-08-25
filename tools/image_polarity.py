#!/usr/bin/env python3
"""Compare extracted radiology images against their rendered PDF appearance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
from PIL import Image


SAMPLE_SIZE = 96
MIN_STANDARD_DEVIATION = 8.0
MATCH_THRESHOLD = 0.55
FINAL_ASSET_INVERSION_THRESHOLD = -0.72
POSTPROCESS_SUFFIX = ".postprocess.json"


def _grayscale_samples(image: Image.Image) -> np.ndarray:
    """Downsample the center so small PDF borders cannot dominate comparison."""
    grayscale = image.convert("L")
    inset_x = max(0, int(grayscale.width * 0.025))
    inset_y = max(0, int(grayscale.height * 0.025))
    if grayscale.width > inset_x * 2 and grayscale.height > inset_y * 2:
        grayscale = grayscale.crop(
            (inset_x, inset_y, grayscale.width - inset_x, grayscale.height - inset_y)
        )
    resized = grayscale.resize(
        (SAMPLE_SIZE, SAMPLE_SIZE), Image.Resampling.BILINEAR
    )
    return np.asarray(resized, dtype=np.float64).reshape(-1)


def compare_polarity(candidate: Image.Image, reference: Image.Image) -> dict[str, Any]:
    """Classify whether an image follows or reverses its PDF grayscale."""
    actual = _grayscale_samples(candidate)
    expected = _grayscale_samples(reference)
    actual_deviation = float(np.std(actual))
    expected_deviation = float(np.std(expected))
    if min(actual_deviation, expected_deviation) < MIN_STANDARD_DEVIATION:
        return {
            "status": "inconclusive",
            "correlation": None,
            "reason": "insufficient_grayscale_variation",
        }

    actual -= float(np.mean(actual))
    expected -= float(np.mean(expected))
    denominator = float(np.linalg.norm(actual) * np.linalg.norm(expected))
    if denominator <= 0:
        return {"status": "inconclusive", "correlation": None, "reason": "zero_norm"}

    correlation = float(np.dot(actual, expected) / denominator)
    if correlation <= -MATCH_THRESHOLD:
        status = "inverted"
    elif correlation >= MATCH_THRESHOLD:
        status = "correct"
    else:
        status = "inconclusive"
    return {"status": status, "correlation": round(correlation, 4)}


def _resolve_path(path: str | Path, root: Path) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _render_reference(page: pymupdf.Page, bbox: dict[str, Any]) -> Image.Image:
    rectangle = pymupdf.Rect(
        float(bbox["x0"]),
        float(bbox["y0"]),
        float(bbox["x1"]),
        float(bbox["y1"]),
    )
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=rectangle, alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def audit_extraction(manifest_path: Path, *, persist: bool = True) -> dict[str, Any]:
    """Audit raw streams and safe rendered figures against the original PDF."""
    manifest_path = manifest_path.expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path /= "manifest.json"
    if not manifest_path.is_file():
        return {
            "ok": False,
            "manifest": str(manifest_path),
            "failures": [f"Extraction manifest not found: {manifest_path}"],
            "warnings": [],
            "figures": [],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return {
            "ok": False,
            "manifest": str(manifest_path),
            "failures": [f"Extraction manifest is unreadable: {error}"],
            "warnings": [],
            "figures": [],
        }

    extracted = manifest_path.parent
    source_pdf = _resolve_path(str(manifest.get("pdf", "")), extracted)
    if not source_pdf.is_file():
        return {
            "ok": False,
            "manifest": str(manifest_path),
            "failures": [f"Original PDF is unavailable for image comparison: {source_pdf}"],
            "warnings": [],
            "figures": [],
        }

    sources = {
        str(entry.get("file")): entry
        for entry in manifest.get("images", [])
        if isinstance(entry, dict)
    }
    failures: list[str] = []
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []

    with pymupdf.open(source_pdf) as document:
        for figure in manifest.get("figures", []):
            source_name = str(figure.get("source", ""))
            source = sources.get(source_name, {})
            page_number = int(figure.get("page", source.get("page", 0)) or 0)
            if not (1 <= page_number <= len(document)):
                warnings.append(f"Cannot compare figure with invalid page: {source_name}")
                continue

            raw_path = _resolve_path(source_name, extracted)
            rendered_path = _resolve_path(str(figure.get("file", "")), extracted)
            raw_bbox = source.get("bbox_pt")
            rendered_bbox = figure.get("bbox_pt")
            if not isinstance(raw_bbox, dict) or not isinstance(rendered_bbox, dict):
                warnings.append(f"No PDF image rectangle for grayscale comparison: {source_name}")
                continue
            if not raw_path.is_file() or not rendered_path.is_file():
                failures.append(
                    f"Image grayscale audit is missing a source or rendered figure: {source_name}"
                )
                continue

            page = document[page_number - 1]
            with Image.open(raw_path) as raw:
                raw_result = compare_polarity(raw, _render_reference(page, raw_bbox))
            with Image.open(rendered_path) as rendered:
                rendered_result = compare_polarity(
                    rendered, _render_reference(page, rendered_bbox)
                )

            if rendered_result["status"] == "inverted":
                failures.append(
                    f"Rendered figure {rendered_path.name} has inverted grayscale on PDF page "
                    f"{page_number}; use a page-rendered image with PDF color decoding."
                )

            finding = {
                "page": page_number,
                "source": source_name,
                "source_path": str(raw_path),
                "rendered": str(figure.get("file", "")),
                "rendered_path": str(rendered_path),
                "raw": raw_result,
                "rendered_polarity": rendered_result,
            }
            findings.append(finding)
            figure["polarity"] = {
                "raw": raw_result,
                "rendered": rendered_result,
            }

    unsafe_sources = [
        finding for finding in findings if finding["raw"]["status"] == "inverted"
    ]
    report = {
        "ok": not failures,
        "manifest": str(manifest_path),
        "source_pdf": str(source_pdf),
        "checked_figures": len(findings),
        "unsafe_raw_streams": len(unsafe_sources),
        "corrected_rendered_figures": sum(
            finding["rendered_polarity"]["status"] == "correct"
            for finding in findings
        ),
        "failures": failures,
        "warnings": warnings,
        "figures": findings,
    }

    if persist:
        report_path = extracted / "polarity-report.json"
        report["report"] = str(report_path)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest["polarity_audit"] = {
            "ok": report["ok"],
            "checked_figures": report["checked_figures"],
            "unsafe_raw_streams": report["unsafe_raw_streams"],
            "corrected_rendered_figures": report["corrected_rendered_figures"],
            "report": report_path.name,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return report


def _provenance_paths(
    sidecar: dict[str, Any], asset: Path, *, visited: set[Path] | None = None
) -> list[Path]:
    visited = set() if visited is None else visited
    values: list[str] = []
    source = sidecar.get("source")
    if isinstance(source, str) and source.strip():
        values.append(source)
    inputs = sidecar.get("source_inputs")
    if isinstance(inputs, list):
        values.extend(value for value in inputs if isinstance(value, str) and value.strip())
    paths: list[Path] = []
    for value in values:
        path = _resolve_path(value, asset.parent)
        if path in visited:
            continue
        visited.add(path)
        paths.append(path)
        parent_sidecar = path.with_suffix(path.suffix + POSTPROCESS_SUFFIX)
        if not parent_sidecar.is_file():
            continue
        try:
            parent = json.loads(parent_sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(parent, dict):
            paths.extend(_provenance_paths(parent, path, visited=visited))
    return paths


def audit_final_assets(spec_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Reject final figures that descend from known inverted embedded streams."""
    spec_path = spec_path.expanduser().resolve()
    if not spec_path.is_file():
        return {"ok": False, "failures": [f"Deck specification not found: {spec_path}"]}
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    checked = 0
    unsafe = {
        Path(finding["source_path"]).resolve(): finding
        for finding in report.get("figures", [])
        if finding.get("raw", {}).get("status") == "inverted"
    }
    references = [
        finding
        for finding in report.get("figures", [])
        if finding.get("rendered_polarity", {}).get("status") == "correct"
    ]

    for index, slide in enumerate(spec.get("slides", []), start=1):
        if slide.get("type") != "figure" or not slide.get("image"):
            continue
        asset = _resolve_path(str(slide["image"]), spec_path.parent)
        sidecar_path = asset.with_suffix(asset.suffix + POSTPROCESS_SUFFIX)
        if not asset.is_file() or not sidecar_path.is_file():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(sidecar.get("asset_type", "figure")).lower() in {"table", "flowchart"}:
            continue

        provenance = _provenance_paths(sidecar, asset)
        source_inputs = sidecar.get("source_inputs")
        panel_count = sidecar.get("panels", 1)
        composite = (
            isinstance(source_inputs, list) and len(source_inputs) > 1
        ) or (
            isinstance(panel_count, int) and panel_count > 1
        )
        candidates = provenance if composite else [asset, *provenance]
        for candidate in dict.fromkeys(candidates):
            finding = unsafe.get(candidate)
            if finding is not None:
                failures.append(
                    f"Figure slide {index} uses inverted raw PDF image {candidate.name} "
                    f"from page {finding['page']}; rebuild it from "
                    f"{finding['rendered']} instead."
                )
                continue

            if not candidate.is_file():
                continue
            with Image.open(candidate) as actual:
                best: tuple[float, dict[str, Any]] | None = None
                aspect = actual.width / max(1, actual.height)
                for reference in references:
                    reference_path = Path(reference["rendered_path"])
                    if not reference_path.is_file():
                        continue
                    with Image.open(reference_path) as expected:
                        reference_aspect = expected.width / max(1, expected.height)
                        if abs(aspect / reference_aspect - 1) > 0.18:
                            continue
                        result = compare_polarity(actual, expected)
                    score = result.get("correlation")
                    if score is not None and (best is None or abs(score) > abs(best[0])):
                        best = (score, reference)
                if best is not None and best[0] <= FINAL_ASSET_INVERSION_THRESHOLD:
                    failures.append(
                        f"Figure slide {index} source {candidate.name} reverses the grayscale "
                        f"of its PDF-rendered reference (correlation {best[0]:.3f})."
                    )
        checked += 1

    return {"ok": not failures, "checked_assets": checked, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Extraction manifest or extracted directory")
    parser.add_argument("--spec", type=Path, help="Also inspect final figure provenance")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = audit_extraction(args.manifest)
    if args.spec and report["ok"]:
        final = audit_final_assets(args.spec, report)
        report["final_assets"] = final
        report["failures"].extend(final["failures"])
        report["ok"] = not report["failures"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "Image polarity QA: "
            f"{report.get('checked_figures', 0)} PDF images checked, "
            f"{report.get('unsafe_raw_streams', 0)} inverted raw stream(s), "
            f"{report.get('corrected_rendered_figures', 0)} correctly rendered figure(s)."
        )
        for failure in report["failures"]:
            print(f"[FAIL] {failure}")
        for warning in report["warnings"]:
            print(f"[WARN] {warning}")
        print("Image polarity QA passed." if report["ok"] else "Image polarity QA failed.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
