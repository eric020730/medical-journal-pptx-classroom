#!/usr/bin/env python3
"""Compare extracted medical-journal images with their rendered PDF appearance."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import pymupdf
from PIL import Image

import vector_table
import article_asset_map


SAMPLE_SIZE = 96
MIN_STANDARD_DEVIATION = 8.0
MATCH_THRESHOLD = 0.55
FINAL_ASSET_INVERSION_THRESHOLD = -0.72
POSTPROCESS_SUFFIX = ".postprocess.json"
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
EXTRACTION_MANIFEST_SCHEMA = "medical-journal-extraction-manifest/v1"
PANEL_SEAM_REVIEW_SCHEMA = "medical-journal-panel-seam-review/v1"
SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


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


def _failure_report(manifest_path: Path, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "manifest": str(manifest_path),
        "failures": [message],
        "warnings": [],
        "figures": [],
        "verified_raster_terminals": [],
        "verified_references": [],
        "known_raw_paths": [],
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_asset_path(root: Path, value: Any) -> Path | None:
    """Resolve a manifest artifact only when it is a relative child of root."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return None
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _valid_page_bbox(value: Any) -> bool:
    if not isinstance(value, dict) or set(("x0", "y0", "x1", "y1")) - set(value):
        return False
    try:
        x0, y0, x1, y1 = (float(value[key]) for key in ("x0", "y0", "x1", "y1"))
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(v) for v in (x0, y0, x1, y1)) and x1 > x0 and y1 > y0


def _valid_list_bbox(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(v) for v in (x0, y0, x1, y1)) and x1 > x0 and y1 > y0


def _bbox_within_page(value: Any, page: pymupdf.Page, *, tolerance: float = 0.25) -> bool:
    if isinstance(value, dict) and _valid_page_bbox(value):
        values = [value[key] for key in ("x0", "y0", "x1", "y1")]
    elif _valid_list_bbox(value):
        values = value
    else:
        return False
    x0, y0, x1, y1 = (float(item) for item in values)
    rectangle = page.rect
    return (
        x0 >= rectangle.x0 - tolerance
        and y0 >= rectangle.y0 - tolerance
        and x1 <= rectangle.x1 + tolerance
        and y1 <= rectangle.y1 + tolerance
    )


def _visual_mae(candidate: Image.Image, reference: Image.Image) -> float:
    """Return normalized RGB mean absolute error after deterministic resizing."""
    actual = np.asarray(
        candidate.convert("RGB").resize((SAMPLE_SIZE, SAMPLE_SIZE), Image.Resampling.BILINEAR),
        dtype=np.float64,
    )
    expected = np.asarray(
        reference.convert("RGB").resize((SAMPLE_SIZE, SAMPLE_SIZE), Image.Resampling.BILINEAR),
        dtype=np.float64,
    )
    return float(np.mean(np.abs(actual - expected)))


def _is_fully_opaque(image: Image.Image) -> bool:
    if "A" in image.getbands() or "transparency" in image.info:
        alpha = image.convert("RGBA").getchannel("A")
        return alpha.getextrema() == (255, 255)
    return True


def _render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _render_list_bbox(page: pymupdf.Page, bbox: list[Any], dpi: int) -> Image.Image:
    rectangle = pymupdf.Rect(*(float(item) for item in bbox))
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0), clip=rectangle, alpha=False
    )
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def audit_extraction(manifest_path: Path, *, persist: bool = True) -> dict[str, Any]:
    """Audit raw streams and safe rendered figures against the original PDF."""
    manifest_path = manifest_path.expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path /= "manifest.json"
    if not manifest_path.is_file():
        return _failure_report(manifest_path, f"Extraction manifest not found: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return _failure_report(manifest_path, f"Extraction manifest is unreadable: {error}")

    if not isinstance(manifest, dict):
        return _failure_report(manifest_path, "Extraction manifest top level must be a JSON object.")
    if manifest.get("schema") != EXTRACTION_MANIFEST_SCHEMA:
        return _failure_report(
            manifest_path,
            f"Extraction manifest has unsupported schema {manifest.get('schema')!r}.",
        )
    for key in ("pages", "images", "figures", "unique_figures", "tables"):
        if not isinstance(manifest.get(key), list):
            return _failure_report(manifest_path, f"Extraction manifest field {key!r} must be a list.")

    extracted = manifest_path.parent
    pdf_value = manifest.get("pdf")
    if not isinstance(pdf_value, str) or not pdf_value.strip():
        return _failure_report(manifest_path, "Extraction manifest pdf must be a non-empty path.")
    source_pdf = _resolve_path(pdf_value, extracted)
    if not source_pdf.is_file():
        return _failure_report(
            manifest_path, f"Original PDF is unavailable for image comparison: {source_pdf}"
        )
    expected_pdf_hash = manifest.get("pdf_sha256")
    if not _valid_sha256(expected_pdf_hash) or _sha256_file(source_pdf) != expected_pdf_hash:
        return _failure_report(manifest_path, "Original PDF SHA-256 does not match extraction manifest.")

    failures: list[str] = []
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []
    verified: set[Path] = set()
    references: list[dict[str, Any]] = []
    known_raw: set[Path] = set()
    sources: dict[str, dict[str, Any]] = {}

    try:
        document_context = pymupdf.open(source_pdf)
    except Exception as error:
        return _failure_report(manifest_path, f"Original PDF cannot be opened: {error}")

    with document_context as document:
        page_count = manifest.get("page_count")
        render_dpi = manifest.get("render_dpi")
        table_dpi = manifest.get("table_dpi")
        if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count != len(document):
            failures.append(
                f"Extraction manifest page_count={page_count!r} does not match PDF page count {len(document)}."
            )
        if not isinstance(render_dpi, int) or isinstance(render_dpi, bool) or not 36 <= render_dpi <= 1200:
            failures.append("Extraction manifest render_dpi must be an integer from 36 to 1200.")
            render_dpi = 200
        if not isinstance(table_dpi, int) or isinstance(table_dpi, bool) or not 72 <= table_dpi <= 1200:
            failures.append("Extraction manifest table_dpi must be an integer from 72 to 1200.")
            table_dpi = 600

        page_numbers: list[int] = []
        for entry in manifest["pages"]:
            if not isinstance(entry, dict):
                failures.append("Extraction manifest pages entries must be objects.")
                continue
            number = entry.get("page")
            path = _manifest_asset_path(extracted, entry.get("render"))
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(document):
                failures.append(f"Extraction page entry has invalid page number: {number!r}.")
                continue
            page_numbers.append(number)
            if path is None or not path.is_file():
                failures.append(f"Extraction page {number} has missing or out-of-root render path.")
                continue
            if not _valid_sha256(entry.get("sha256")) or _sha256_file(path) != entry.get("sha256"):
                failures.append(f"Extraction page {number} render SHA-256 mismatch.")
                continue
            try:
                with Image.open(path) as candidate:
                    if not _is_fully_opaque(candidate):
                        failures.append(f"Extraction page {number} render contains transparency.")
                        continue
                    candidate_rgb = candidate.convert("RGB")
                fresh = _render_page(document[number - 1], render_dpi)
                if candidate_rgb.size != fresh.size or candidate_rgb.tobytes() != fresh.tobytes():
                    failures.append(
                        f"Extraction page {number} render is not an authentic fresh render of the source PDF."
                    )
                    continue
                if entry.get("width") != candidate_rgb.width or entry.get("height") != candidate_rgb.height:
                    failures.append(f"Extraction page {number} dimensions do not match its render.")
                    continue
            except (OSError, ValueError) as error:
                failures.append(f"Extraction page {number} render is unreadable: {error}.")
                continue
            verified.add(path)
            references.append({"path": str(path), "kind": "page", "page": number})
        if sorted(page_numbers) != list(range(1, len(document) + 1)):
            failures.append("Extraction pages must enumerate every PDF page exactly once in 1-based order.")

        for entry in manifest["images"]:
            if not isinstance(entry, dict):
                failures.append("Extraction manifest images entries must be objects.")
                continue
            name = entry.get("file")
            path = _manifest_asset_path(extracted, name)
            number = entry.get("page")
            if (
                not isinstance(name, str)
                or path is None
                or not path.is_file()
                or not isinstance(number, int)
                or isinstance(number, bool)
                or not 1 <= number <= len(document)
                or not _valid_sha256(entry.get("sha256"))
                or _sha256_file(path) != entry.get("sha256")
            ):
                failures.append(f"Extraction raw-image entry is invalid or has a SHA-256 mismatch: {name!r}.")
                continue
            sources[name] = entry
            known_raw.add(path)

        verified_figures: dict[Path, dict[str, Any]] = {}
        for figure in manifest["figures"]:
            if not isinstance(figure, dict):
                failures.append("Extraction manifest figures entries must be objects.")
                continue
            source_name = figure.get("source")
            if not isinstance(source_name, str):
                failures.append("Extraction figure source must be a string.")
                continue
            source = sources.get(source_name, {})
            page_number = figure.get("page", source.get("page"))
            if (
                not isinstance(page_number, int)
                or isinstance(page_number, bool)
                or not 1 <= page_number <= len(document)
            ):
                failures.append(f"Cannot compare figure with invalid page: {source_name}")
                continue

            raw_path = _manifest_asset_path(extracted, source_name)
            rendered_path = _manifest_asset_path(extracted, figure.get("file"))
            raw_bbox = source.get("bbox_pt")
            rendered_bbox = figure.get("bbox_pt")
            if raw_path is None or rendered_path is None:
                failures.append(f"Figure has missing or out-of-root paths: {source_name}")
                continue
            if not raw_path.is_file() or not rendered_path.is_file():
                failures.append(
                    f"Image grayscale audit is missing a source or rendered figure: {source_name}"
                )
                continue
            if not _valid_sha256(figure.get("sha256")) or _sha256_file(rendered_path) != figure.get("sha256"):
                failures.append(f"Rendered figure {rendered_path.name} SHA-256 mismatch.")
                continue
            page = document[page_number - 1]
            if (
                not _valid_page_bbox(raw_bbox)
                or not _valid_page_bbox(rendered_bbox)
                or not _bbox_within_page(raw_bbox, page)
                or not _bbox_within_page(rendered_bbox, page)
            ):
                failures.append(
                    f"Rendered figure {rendered_path.name} has an invalid or out-of-page PDF rectangle."
                )
                continue
            try:
                raw_reference = _render_reference(page, raw_bbox)
                rendered_reference = _render_reference(page, rendered_bbox)
                with Image.open(raw_path) as raw:
                    raw_result = compare_polarity(raw, raw_reference)
                with Image.open(rendered_path) as rendered:
                    if not _is_fully_opaque(rendered):
                        failures.append(f"Rendered figure {rendered_path.name} contains transparency.")
                        continue
                    rendered_rgb = rendered.convert("RGB")
                    rendered_result = compare_polarity(rendered, rendered_reference)
                    visual_mae = _visual_mae(rendered, rendered_reference)
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append(f"Figure {rendered_path.name} cannot be authenticated: {error}.")
                continue

            try:
                import extract_from_pdf

                with tempfile.TemporaryDirectory() as temporary:
                    regenerated_path = Path(temporary) / "figure.png"
                    regenerated_bbox, regenerated_width, regenerated_height, _ = (
                        extract_from_pdf._save_verified_figure_clip(
                            page,
                            pymupdf.Matrix(render_dpi / 72.0, render_dpi / 72.0),
                            raw_bbox,
                            regenerated_path,
                        )
                    )
                    with Image.open(regenerated_path) as regenerated:
                        regenerated_rgb = regenerated.convert("RGB")
                bbox_matches = all(
                    abs(float(regenerated_bbox[key]) - float(rendered_bbox[key])) <= 0.05
                    for key in ("x0", "y0", "x1", "y1")
                )
                rendered_authentic = (
                    bbox_matches
                    and rendered_rgb.size == regenerated_rgb.size
                    and rendered_rgb.tobytes() == regenerated_rgb.tobytes()
                    and figure.get("width") == regenerated_width
                    and figure.get("height") == regenerated_height
                )
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append(f"Rendered figure {rendered_path.name} cannot be regenerated: {error}.")
                continue
            if not rendered_authentic:
                failures.append(
                    f"Rendered figure {rendered_path.name} is not byte-for-pixel identical "
                    "to a fresh deterministic extraction of its declared PDF placement."
                )

            finding = {
                "page": page_number,
                "source": source_name,
                "source_path": str(raw_path),
                "rendered": str(figure.get("file", "")),
                "rendered_path": str(rendered_path),
                "raw": raw_result,
                "rendered_polarity": rendered_result,
                "visual_mae": round(visual_mae, 3),
                "authenticated": rendered_authentic,
            }
            findings.append(finding)
            figure["polarity"] = {
                "raw": raw_result,
                "rendered": rendered_result,
            }
            if rendered_authentic:
                verified.add(rendered_path)
                verified_figures[rendered_path] = finding
                references.append(
                    {"path": str(rendered_path), "kind": "figure", "page": page_number}
                )

        for entry in manifest["unique_figures"]:
            if not isinstance(entry, dict):
                failures.append("Extraction manifest unique_figures entries must be objects.")
                continue
            original = _manifest_asset_path(extracted, entry.get("file"))
            unique = _manifest_asset_path(extracted, entry.get("unique_path"))
            if original not in verified_figures or unique is None or not unique.is_file():
                failures.append("Unique figure does not point to an authenticated rendered figure.")
                continue
            if (
                not _valid_sha256(entry.get("unique_sha256"))
                or _sha256_file(unique) != entry.get("unique_sha256")
                or unique.read_bytes() != original.read_bytes()
            ):
                failures.append(f"Unique figure {unique.name} is not a byte-identical authenticated alias.")
                continue
            verified.add(unique)
            references.append(
                {"path": str(unique), "kind": "figure", "page": verified_figures[original]["page"]}
            )

        for entry in manifest["tables"]:
            if not isinstance(entry, dict):
                failures.append("Extraction manifest tables entries must be objects.")
                continue
            path = _manifest_asset_path(extracted, entry.get("file"))
            page_number = entry.get("page")
            bbox = entry.get("bbox")
            if (
                path is None
                or not path.is_file()
                or not isinstance(page_number, int)
                or isinstance(page_number, bool)
                or not 1 <= page_number <= len(document)
                or not _valid_list_bbox(bbox)
                or not _valid_sha256(entry.get("sha256"))
                or _sha256_file(path) != entry.get("sha256")
            ):
                failures.append(f"Extraction table entry is invalid or has a SHA-256 mismatch: {entry.get('file')!r}.")
                continue
            try:
                reference_image = _render_list_bbox(document[page_number - 1], bbox, table_dpi)
                with Image.open(path) as candidate:
                    if not _is_fully_opaque(candidate):
                        failures.append(f"Extraction table {path.name} contains transparency.")
                        continue
                    candidate_rgb = candidate.convert("RGB")
                    polarity = compare_polarity(candidate, reference_image)
                    visual_mae = _visual_mae(candidate, reference_image)
            except (OSError, ValueError) as error:
                failures.append(f"Extraction table {path.name} is unreadable: {error}.")
                continue
            original_bbox = entry.get("original_bbox")
            page = document[page_number - 1]
            if (
                not _bbox_within_page(bbox, page)
                or not _valid_list_bbox(original_bbox)
                or not _bbox_within_page(original_bbox, page)
            ):
                failures.append(
                    f"Extraction table {path.name} has an invalid or out-of-page bbox/original_bbox."
                )
                continue
            try:
                import extract_from_pdf
                import pdfplumber

                with tempfile.TemporaryDirectory() as temporary, pdfplumber.open(source_pdf) as pdf:
                    regenerated_path = Path(temporary) / "table.png"
                    regenerated_bbox, _ = extract_from_pdf._save_verified_table_crop(
                        pdf.pages[page_number - 1],
                        tuple(float(value) for value in original_bbox),
                        regenerated_path,
                        table_dpi=table_dpi,
                    )
                    with Image.open(regenerated_path) as regenerated:
                        regenerated_rgb = regenerated.convert("RGB")
                bbox_matches = all(
                    abs(float(left) - float(right)) <= 0.11
                    for left, right in zip(regenerated_bbox, bbox)
                )
                table_authentic = (
                    bbox_matches
                    and candidate_rgb.size == regenerated_rgb.size
                    and candidate_rgb.tobytes() == regenerated_rgb.tobytes()
                )
            except (OSError, ValueError, TypeError, IndexError) as error:
                failures.append(f"Extraction table {path.name} cannot be regenerated: {error}.")
                continue
            if not table_authentic:
                failures.append(
                    f"Extraction table {path.name} is not byte-for-pixel identical to a fresh "
                    "deterministic extraction of its declared PDF crop."
                )
                continue
            verified.add(path)
            references.append(
                {"path": str(path), "kind": "table", "page": page_number, "bbox": bbox}
            )

    unsafe_sources = [
        finding for finding in findings if finding["raw"]["status"] == "inverted"
    ]
    report = {
        "ok": not failures,
        "manifest": str(manifest_path),
        "source_pdf": str(source_pdf),
        "source_pdf_sha256": expected_pdf_hash,
        "checked_figures": len(findings),
        "unsafe_raw_streams": len(unsafe_sources),
        "corrected_rendered_figures": sum(
            finding["rendered_polarity"]["status"] == "correct"
            for finding in findings
        ),
        "failures": failures,
        "warnings": warnings,
        "figures": findings,
        "verified_raster_terminals": sorted(str(path) for path in verified),
        "verified_references": references,
        "known_raw_paths": sorted(str(path) for path in known_raw),
    }

    if persist:
        try:
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
        except OSError as error:
            report["failures"].append(f"Cannot persist polarity audit: {error}")
            report["ok"] = False

    return report


def _trusted_terminal_sources(report: dict[str, Any]) -> set[Path]:
    """Use the immutable, freshly authenticated terminal inventory in the report."""
    values = report.get("verified_raster_terminals")
    if isinstance(values, list):
        return {
            Path(value).expanduser().resolve()
            for value in values
            if isinstance(value, str) and value
        }

    # Compatibility for direct unit-level callers that construct a report
    # without going through audit_extraction(). QA never uses this fallback.
    return {
        Path(finding["rendered_path"]).expanduser().resolve()
        for finding in report.get("figures", [])
        if isinstance(finding, dict)
        and isinstance(finding.get("rendered_path"), str)
        and finding.get("rendered_polarity", {}).get("status") == "correct"
    }


def _trusted_document_sources(report: dict[str, Any]) -> set[Path]:
    """Return audited source documents, which are not raster terminals by default."""
    source_pdf = report.get("source_pdf")
    if isinstance(source_pdf, str) and source_pdf:
        return {Path(source_pdf).expanduser().resolve()}
    return set()


def _provenance_paths(
    sidecar: dict[str, Any],
    asset: Path,
    *,
    trusted: set[Path],
    known_raw: set[Path],
    trusted_documents: set[Path] | None = None,
    allow_document_terminal: bool = False,
    active: tuple[Path, ...] | None = None,
    validated: set[Path] | None = None,
) -> tuple[list[Path], list[str]]:
    """Return the complete provenance graph and fail closed on unsafe terminals.

    ``active`` is the current recursion stack, while ``validated`` contains
    nodes already checked on another branch.  Keeping the two sets separate is
    important: a shared source in a valid DAG is not a cycle, but a source that
    points back to any active ancestor is.
    """
    asset = asset.expanduser().resolve()
    active = (asset,) if active is None else active
    validated = set() if validated is None else validated
    trusted_documents = set() if trusted_documents is None else trusted_documents
    failures: list[str] = []
    values: list[str] = []
    source = sidecar.get("source")
    if isinstance(source, str) and source.strip():
        values.append(source)
    elif source is not None:
        failures.append(f"Asset {asset.name} has an invalid provenance source.")
    inputs = sidecar.get("source_inputs")
    if isinstance(inputs, list):
        invalid = [value for value in inputs if not isinstance(value, str) or not value.strip()]
        if invalid:
            failures.append(f"Asset {asset.name} has invalid source_inputs provenance.")
        values.extend(value for value in inputs if isinstance(value, str) and value.strip())
    elif inputs is not None:
        failures.append(f"Asset {asset.name} has invalid source_inputs provenance.")
    if not values:
        failures.append(
            f"Asset {asset.name} has no provenance source or source_inputs linking it "
            "to the audited extraction manifest."
        )
    paths: list[Path] = []
    for value in values:
        path = _resolve_path(value, asset.parent)
        paths.append(path)
        if path in active:
            cycle = " -> ".join(node.name for node in (*active, path))
            failures.append(f"Asset {asset.name} has cyclic provenance: {cycle}.")
            continue
        if not path.is_file():
            failures.append(f"Asset {asset.name} references a missing provenance source: {path.name}.")
            continue
        if path in known_raw:
            failures.append(
                f"Asset {asset.name} reaches raw PDF image stream {path.name}; raw streams "
                "are not trusted terminals because PDF Decode/colorspace transforms may be missing."
            )
            continue
        if path in trusted_documents:
            if allow_document_terminal:
                validated.add(path)
            else:
                failures.append(
                    f"Asset {asset.name} reaches source PDF {path.name} directly; "
                    "a raster figure/table must terminate at a manifest-enumerated "
                    "page, table crop, or PDF-rendered figure instead."
                )
            continue
        if path in trusted:
            validated.add(path)
            continue
        if path in validated:
            continue
        parent_sidecar = path.with_suffix(path.suffix + POSTPROCESS_SUFFIX)
        if not parent_sidecar.is_file():
            failures.append(
                f"Intermediate image {path.name} has no provenance sidecar; "
                "every crop or panel must trace to an audited PDF-rendered source."
            )
            continue
        try:
            parent = json.loads(parent_sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            failures.append(f"Intermediate image {path.name} has an unreadable provenance sidecar.")
            continue
        if isinstance(parent, dict):
            nested, errors = _provenance_paths(
                parent,
                path,
                trusted=trusted,
                known_raw=known_raw,
                trusted_documents=trusted_documents,
                allow_document_terminal=allow_document_terminal,
                active=(*active, path),
                validated=validated,
            )
            paths.extend(nested)
            failures.extend(errors)
            if not errors:
                validated.add(path)
        else:
            failures.append(f"Intermediate image {path.name} has an invalid provenance sidecar.")
    return paths, failures


def _rendered_references_for(
    candidate: Path,
    *,
    trusted: set[Path],
    known_raw: set[Path],
    reference_by_path: dict[Path, dict[str, Any]],
    trusted_documents: set[Path] | None = None,
    allow_document_terminal: bool = False,
) -> tuple[list[Path], list[str]]:
    """Resolve only the PDF-rendered references reachable from ``candidate``."""
    sidecar_path = candidate.with_suffix(candidate.suffix + POSTPROCESS_SUFFIX)
    if not sidecar_path.is_file():
        return [], [f"Intermediate image {candidate.name} has no provenance sidecar."]
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], [f"Intermediate image {candidate.name} has an unreadable provenance sidecar."]
    if not isinstance(sidecar, dict):
        return [], [f"Intermediate image {candidate.name} has an invalid provenance sidecar."]
    provenance, failures = _provenance_paths(
        sidecar,
        candidate,
        trusted=trusted,
        known_raw=known_raw,
        trusted_documents=trusted_documents,
        allow_document_terminal=allow_document_terminal,
    )
    references = list(dict.fromkeys(path for path in provenance if path in reference_by_path))
    return references, failures


def _flowchart_evidence(sidecar: dict[str, Any], asset: Path, report: dict[str, Any]) -> list[str]:
    """Authenticate the one supported direct-PDF raster path for vector diagrams."""
    prefix = f"Flowchart {asset.name}"
    failures: list[str] = []
    source_pdf = report.get("source_pdf")
    if sidecar.get("command") != "crop-vector-figure":
        return [f"{prefix} may reach a PDF directly only through command='crop-vector-figure'."]
    if not isinstance(source_pdf, str) or not source_pdf:
        return [f"{prefix} has no audited source PDF."]
    source = sidecar.get("source")
    if not isinstance(source, str) or _resolve_path(source, asset.parent) != Path(source_pdf).resolve():
        return [f"{prefix} source does not equal the audited source PDF."]
    page_number = sidecar.get("page")
    dpi = sidecar.get("dpi")
    bbox = sidecar.get("effective_bbox_pt") or sidecar.get("detected_bbox_pt")
    crop_margin = sidecar.get("pdf_crop_margin_pt")
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
        failures.append(f"{prefix} page must be a positive integer.")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 72 <= dpi <= 1200:
        failures.append(f"{prefix} dpi must be an integer from 72 to 1200.")
    if not _valid_list_bbox(bbox):
        failures.append(f"{prefix} detected_bbox_pt must be four finite increasing numbers.")
    if not isinstance(crop_margin, (int, float)) or isinstance(crop_margin, bool) or not math.isfinite(float(crop_margin)) or crop_margin < 0:
        failures.append(f"{prefix} pdf_crop_margin_pt must be a finite non-negative number.")
    if failures:
        return failures
    try:
        with pymupdf.open(source_pdf) as document:
            if page_number > len(document):
                return [f"{prefix} page {page_number} is outside the audited PDF."]
            x0, y0, x1, y1 = (float(value) for value in bbox)
            expanded = (
                [x0, y0, x1, y1]
                if sidecar.get("effective_bbox_pt")
                else [x0 - float(crop_margin), y0 - float(crop_margin), x1 + float(crop_margin), y1 + float(crop_margin)]
            )
            page = document[page_number - 1]
            if not _bbox_within_page(expanded, page):
                return [f"{prefix} effective PDF crop is outside the audited page."]
            reference = _render_list_bbox(page, expanded, dpi)
        with Image.open(asset) as image:
            if not _is_fully_opaque(image):
                return [f"{prefix} contains transparency."]
            candidate = image.convert("RGB")
        safety = sidecar.get("safety_margin_px")
        if isinstance(safety, int) and not isinstance(safety, bool) and safety > 0:
            if candidate.width <= 2 * safety or candidate.height <= 2 * safety:
                return [f"{prefix} is smaller than its declared safety canvas."]
            candidate = candidate.crop(
                (safety, safety, candidate.width - safety, candidate.height - safety)
            )
        inner_margin = sidecar.get("white_margin_px") if sidecar.get("outer_frame_stripped") else 0
        if isinstance(inner_margin, int) and inner_margin > 0:
            if candidate.width > 2 * inner_margin and candidate.height > 2 * inner_margin:
                candidate = candidate.crop(
                    (inner_margin, inner_margin, candidate.width - inner_margin, candidate.height - inner_margin)
                )
        polarity = compare_polarity(candidate, reference)
        mae = _visual_mae(candidate, reference)
    except (OSError, ValueError, TypeError) as error:
        return [f"{prefix} evidence cannot be recomputed: {error}."]
    if polarity["status"] != "correct" or mae > 18.0:
        failures.append(
            f"{prefix} does not match its recomputed PDF crop "
            f"(polarity={polarity['status']}, RGB MAE={mae:.2f})."
        )
    return failures


def _visual_match(candidate: Image.Image, reference: Image.Image) -> tuple[bool, dict[str, Any]]:
    polarity = compare_polarity(candidate, reference)
    mae = _visual_mae(candidate, reference)
    actual = np.asarray(candidate.convert("RGB"), dtype=np.int16)
    expected = np.asarray(
        reference.convert("RGB").resize(candidate.size, Image.Resampling.LANCZOS),
        dtype=np.int16,
    )
    changed_fraction = float(np.mean(np.max(np.abs(actual - expected), axis=2) > 35))
    accepted = (
        polarity["status"] != "inverted"
        and mae <= 18.0
        and changed_fraction <= 0.02
    )
    return accepted, {
        **polarity,
        "rgb_mae": round(mae, 3),
        "changed_fraction": round(changed_fraction, 5),
    }


def _decoded_rgb_equal(left: Path, right: Path) -> bool:
    with Image.open(left) as left_image, Image.open(right) as right_image:
        if not _is_fully_opaque(left_image) or not _is_fully_opaque(right_image):
            return False
        left_rgb = left_image.convert("RGB")
        right_rgb = right_image.convert("RGB")
        return left_rgb.size == right_rgb.size and left_rgb.tobytes() == right_rgb.tobytes()


def _deterministic_helper_evidence(asset: Path, sidecar: dict[str, Any]) -> tuple[bool, list[str]]:
    """Re-run supported single-source raster helpers and require exact decoded pixels."""
    command = sidecar.get("command")
    if command not in {
        "trim", "labels", "panel-crop", "same-width", "split-table", "recompose-panels",
        "recompose-panels-aligned", "recompose-panels-banded", "crop-vector-figure",
    }:
        return False, []
    source_value = sidecar.get("source")
    source: Path | None = None
    if isinstance(source_value, str):
        source = _resolve_path(source_value, asset.parent)
    elif not (
        command in {
            "recompose-panels", "recompose-panels-aligned", "recompose-panels-banded"
        }
        and (
            sidecar.get("input_mode") == "inputs"
            or command in {"recompose-panels-aligned", "recompose-panels-banded"}
        )
    ):
        return True, [f"Asset {asset.name} helper evidence requires one source path."]
    if source is not None and not source.is_file():
        return True, [f"Asset {asset.name} helper source is missing."]
    try:
        with tempfile.TemporaryDirectory() as temporary:
            regenerated = Path(temporary) / f"regenerated{asset.suffix.lower()}"
            if command in {"trim", "labels"}:
                import postprocess_assets

                assert source is not None

                margin = sidecar.get("margin")
                threshold = sidecar.get("threshold")
                cut_bottom = sidecar.get("cut_bottom_px")
                asset_type = sidecar.get("asset_type")
                bg_aware = sidecar.get("bg_aware", "auto")
                bg_tol = sidecar.get("bg_tol", 26)
                max_edge = sidecar.get("max_edge_px", 4)
                if not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in (margin, threshold, cut_bottom, bg_tol, max_edge)
                ) or asset_type not in {"clinical-image", "figure", "table", "flowchart"} or bg_aware not in {"auto", "on", "off"}:
                    return True, [f"Asset {asset.name} has malformed deterministic {command} parameters."]
                postprocess_assets.trim_image(
                    source,
                    regenerated,
                    margin,
                    threshold,
                    cut_bottom,
                    command == "labels",
                    bg_aware=bg_aware,
                    bg_tol=bg_tol,
                    asset_type=asset_type,
                    max_edge_px=max_edge,
                )
            elif command == "panel-crop":
                assert source is not None
                crop_box = sidecar.get("crop_box_px")
                source_size = sidecar.get("source_size_px")
                output_size = sidecar.get("output_size_px")
                if (
                    not isinstance(crop_box, list)
                    or len(crop_box) != 4
                    or not all(
                        isinstance(value, int) and not isinstance(value, bool)
                        for value in crop_box
                    )
                    or not isinstance(source_size, list)
                    or len(source_size) != 2
                    or not all(
                        isinstance(value, int) and not isinstance(value, bool) and value > 0
                        for value in source_size
                    )
                    or not isinstance(output_size, list)
                    or len(output_size) != 2
                    or not all(
                        isinstance(value, int) and not isinstance(value, bool) and value > 0
                        for value in output_size
                    )
                    or sidecar.get("asset_type") != "figure"
                    or sidecar.get("intermediate") is not True
                    or sidecar.get("label_overwritten_pixels") != 0
                ):
                    return True, [f"Asset {asset.name} has malformed panel-crop parameters."]
                verified_trim = sidecar.get("verified_edge_trim_px")
                verified_reason = sidecar.get("verified_edge_trim_reason")
                if verified_trim is not None or verified_reason is not None:
                    valid_verified = (
                        isinstance(verified_trim, dict)
                        and set(verified_trim) == {"top", "bottom", "left", "right"}
                        and all(
                            isinstance(value, int)
                            and not isinstance(value, bool)
                            and 0 <= value <= 12
                            for value in verified_trim.values()
                        )
                        and any(verified_trim.values())
                        and verified_reason in {
                            "verified-pdf-exterior-band",
                            "verified-image-box-correction",
                            "manual-visual-review",
                        }
                    )
                    if not valid_verified:
                        return True, [
                            f"Asset {asset.name} has malformed verified edge-trim evidence."
                        ]
                with Image.open(source) as opened:
                    source_rgb = opened.convert("RGB")
                if list(source_rgb.size) != source_size:
                    return True, [f"Asset {asset.name} panel-crop source size has changed."]
                x0, y0, x1, y1 = crop_box
                if not (
                    0 <= x0 < x1 <= source_rgb.width
                    and 0 <= y0 < y1 <= source_rgb.height
                ):
                    return True, [f"Asset {asset.name} panel-crop box is outside its source."]
                expected_size = [x1 - x0, y1 - y0]
                if output_size != expected_size:
                    return True, [f"Asset {asset.name} panel-crop output size is inconsistent."]
                seam_evidence = sidecar.get("seam_review")
                seam_evidence_by_edge = sidecar.get("seam_reviews")
                required_seam_edges = sidecar.get("required_seam_edges")
                if seam_evidence is not None and seam_evidence_by_edge is not None:
                    return True, [
                        f"Asset {asset.name} mixes legacy and multi-seam review evidence."
                    ]
                if seam_evidence_by_edge is None and required_seam_edges is not None:
                    return True, [
                        f"Asset {asset.name} declares required seam edges without multi-seam evidence."
                    ]
                if seam_evidence_by_edge is not None:
                    valid_edges = {"left", "right", "top", "bottom"}
                    if (
                        not isinstance(seam_evidence_by_edge, dict)
                        or not seam_evidence_by_edge
                        or not set(seam_evidence_by_edge).issubset(valid_edges)
                        or not isinstance(required_seam_edges, list)
                        or len(required_seam_edges) != len(set(required_seam_edges))
                        or set(required_seam_edges) != set(seam_evidence_by_edge)
                    ):
                        return True, [
                            f"Asset {asset.name} has malformed multi-seam review evidence."
                        ]
                    for evidence_edge, evidence in seam_evidence_by_edge.items():
                        if not isinstance(evidence, dict) or evidence.get("edge") != evidence_edge:
                            return True, [
                                f"Asset {asset.name} has a mismatched multi-seam edge binding."
                            ]
                        legacy_sidecar = dict(sidecar)
                        legacy_sidecar.pop("seam_reviews", None)
                        legacy_sidecar.pop("required_seam_edges", None)
                        legacy_sidecar["seam_review"] = evidence
                        handled, seam_failures = _deterministic_helper_evidence(
                            asset, legacy_sidecar
                        )
                        if not handled or seam_failures:
                            return True, seam_failures or [
                                f"Asset {asset.name} multi-seam review could not be replayed."
                            ]
                    seam_evidence = None
                if seam_evidence is not None:
                    if not isinstance(seam_evidence, dict):
                        return True, [f"Asset {asset.name} has malformed seam-review evidence."]
                    report_value = seam_evidence.get("report")
                    report_hash = seam_evidence.get("report_sha256")
                    edge = seam_evidence.get("edge")
                    if (
                        seam_evidence.get("schema") != PANEL_SEAM_REVIEW_SCHEMA
                        or not isinstance(report_value, str)
                        or not isinstance(report_hash, str)
                        or not SHA256_RE.fullmatch(report_hash)
                        or edge not in {"left", "right", "top", "bottom"}
                    ):
                        return True, [f"Asset {asset.name} has malformed seam-review evidence."]
                    report_path = _resolve_path(report_value, asset.parent)
                    if not report_path.is_file() or _sha256_file(report_path) != report_hash:
                        return True, [f"Asset {asset.name} seam-review report is missing or changed."]
                    try:
                        report = json.loads(report_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        return True, [f"Asset {asset.name} seam-review report is unreadable."]
                    axis = report.get("axis")
                    band = report.get("band_px")
                    search = report.get("search_px")
                    selected = report.get("selected_px")
                    best = report.get("best_px")
                    tolerance = report.get("tolerance_px")
                    overlay_value = report.get("overlay")
                    overlay_hash = report.get("overlay_sha256")
                    if (
                        report.get("schema") != PANEL_SEAM_REVIEW_SCHEMA
                        or report.get("status") != "pass"
                        or report.get("source_sha256") != _sha256_file(source)
                        or report.get("source_size_px") != source_size
                        or axis not in {"x", "y"}
                        or not isinstance(selected, int)
                        or isinstance(selected, bool)
                        or not isinstance(best, int)
                        or isinstance(best, bool)
                        or not isinstance(tolerance, int)
                        or isinstance(tolerance, bool)
                        or not 0 <= tolerance <= 4
                        or not isinstance(band, list)
                        or len(band) != 2
                        or not all(isinstance(value, int) and not isinstance(value, bool) for value in band)
                        or not isinstance(search, list)
                        or len(search) != 2
                        or not all(isinstance(value, int) and not isinstance(value, bool) for value in search)
                        or abs(selected - best) > tolerance
                    ):
                        return True, [f"Asset {asset.name} seam-review report is inconsistent."]
                    overlay_path = (
                        _resolve_path(overlay_value, report_path.parent)
                        if isinstance(overlay_value, str) else None
                    )
                    if (
                        overlay_path is None
                        or not overlay_path.is_file()
                        or not isinstance(overlay_hash, str)
                        or not SHA256_RE.fullmatch(overlay_hash)
                        or _sha256_file(overlay_path) != overlay_hash
                    ):
                        return True, [f"Asset {asset.name} seam-review overlay is missing or changed."]
                    dimension = source_rgb.width if axis == "x" else source_rgb.height
                    perpendicular = source_rgb.height if axis == "x" else source_rgb.width
                    if (
                        not 0 <= band[0] < band[1] <= perpendicular
                        or not 1 <= search[0] <= selected <= search[1] < dimension
                    ):
                        return True, [f"Asset {asset.name} seam-review search geometry is invalid."]
                    pixels = np.asarray(source_rgb, dtype=np.float32)
                    scores: list[tuple[int, float]] = []
                    for candidate in range(search[0], search[1] + 1):
                        if axis == "x":
                            delta = np.abs(
                                pixels[band[0]:band[1], candidate, :]
                                - pixels[band[0]:band[1], candidate - 1, :]
                            )
                        else:
                            delta = np.abs(
                                pixels[candidate, band[0]:band[1], :]
                                - pixels[candidate - 1, band[0]:band[1], :]
                            )
                        scores.append((candidate, float(delta.mean())))
                    recomputed_best = sorted(scores, key=lambda item: (-item[1], item[0]))[0][0]
                    if best != recomputed_best:
                        return True, [f"Asset {asset.name} seam-review transition no longer replays."]
                    if axis == "x":
                        crop_coordinate = x0 if edge == "left" else x1 if edge == "right" else None
                        perpendicular_span = [y0, y1]
                    else:
                        crop_coordinate = y0 if edge == "top" else y1 if edge == "bottom" else None
                        perpendicular_span = [x0, x1]
                    if (
                        crop_coordinate != selected
                        or not band[0] <= perpendicular_span[0] < perpendicular_span[1] <= band[1]
                        or seam_evidence.get("axis") != axis
                        or seam_evidence.get("band_px") != band
                        or seam_evidence.get("selected_px") != selected
                    ):
                        return True, [f"Asset {asset.name} crop does not match its seam review."]
                source_rgb.crop((x0, y0, x1, y1)).save(regenerated)
            elif command == "same-width":
                assert source is not None
                width = sidecar.get("output_width")
                if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
                    return True, [f"Asset {asset.name} has invalid same-width output_width."]
                with Image.open(source) as opened:
                    source_rgb = opened.convert("RGB")
                if width < source_rgb.width:
                    return True, [f"Asset {asset.name} same-width output is narrower than its source."]
                canvas = Image.new("RGB", (width, source_rgb.height), "white")
                canvas.paste(source_rgb, ((width - source_rgb.width) // 2, 0))
                canvas.save(regenerated, quality=95)
            elif command == "crop-vector-figure":
                assert source is not None
                page_number = sidecar.get("page")
                dpi = sidecar.get("dpi")
                safety = sidecar.get("safety_margin_px")
                stripped = sidecar.get("outer_frame_stripped", False)
                detected = sidecar.get("detected_bbox_pt")
                effective = sidecar.get("effective_bbox_pt")
                crop_margin = sidecar.get("pdf_crop_margin_pt")
                white_margin = sidecar.get("white_margin_px", 0)
                if (
                    not isinstance(page_number, int)
                    or isinstance(page_number, bool)
                    or page_number < 1
                    or not isinstance(dpi, int)
                    or isinstance(dpi, bool)
                    or not 72 <= dpi <= 1200
                    or not isinstance(safety, int)
                    or isinstance(safety, bool)
                    or safety < 0
                    or not isinstance(stripped, bool)
                    or not isinstance(white_margin, int)
                    or isinstance(white_margin, bool)
                    or white_margin < 0
                    or not _valid_list_bbox(detected)
                    or not isinstance(crop_margin, (int, float))
                    or isinstance(crop_margin, bool)
                    or not math.isfinite(float(crop_margin))
                    or float(crop_margin) < 0
                ):
                    return True, [f"Asset {asset.name} has malformed crop-vector-figure parameters."]
                if stripped:
                    if not _valid_list_bbox(effective):
                        return True, [f"Asset {asset.name} stripped flowchart lacks effective_bbox_pt."]
                    replay_bbox = effective
                elif _valid_list_bbox(effective):
                    replay_bbox = effective
                else:
                    x0, y0, x1, y1 = (float(value) for value in detected)
                    margin_value = float(crop_margin)
                    replay_bbox = [
                        x0 - margin_value, y0 - margin_value,
                        x1 + margin_value, y1 + margin_value,
                    ]
                with pymupdf.open(source) as document:
                    if page_number > len(document):
                        return True, [f"Asset {asset.name} flowchart page is outside its PDF."]
                    page = document[page_number - 1]
                    if not _bbox_within_page(replay_bbox, page):
                        return True, [f"Asset {asset.name} flowchart bbox is outside its PDF page."]
                    core = _render_list_bbox(page, replay_bbox, dpi)
                if stripped:
                    grayscale = np.asarray(core.convert("L"), dtype=np.uint8)
                    ink = grayscale < 245
                    rows = np.where(ink.any(axis=1))[0]
                    columns = np.where(ink.any(axis=0))[0]
                    if not len(rows) or not len(columns):
                        return True, [f"Asset {asset.name} stripped flowchart contains no replayable ink."]
                    core = core.crop((
                        int(columns.min()), int(rows.min()),
                        int(columns.max()) + 1, int(rows.max()) + 1,
                    ))
                    white = Image.new(
                        "RGB",
                        (core.width + 2 * white_margin, core.height + 2 * white_margin),
                        "white",
                    )
                    white.paste(core, (white_margin, white_margin))
                    core = white
                canvas = Image.new(
                    "RGB", (core.width + 2 * safety, core.height + 2 * safety), "white"
                )
                canvas.paste(core, (safety, safety))
                canvas.save(regenerated)
            elif command == "recompose-panels":
                import postprocess_assets

                integer_names = (
                    "rows", "cols", "gap", "margin", "panel_width", "panel_height",
                    "inset", "edge_white_thr", "edge_light_thr", "panel_frame", "threshold",
                )
                integer_values = {name: sidecar.get(name) for name in integer_names}
                fraction_names = ("edge_white_frac", "edge_light_frac")
                fraction_values = {name: sidecar.get(name) for name in fraction_names}
                input_mode = sidecar.get("input_mode")
                source_inputs = sidecar.get("source_inputs")
                if (
                    not all(
                        isinstance(value, int) and not isinstance(value, bool)
                        for value in integer_values.values()
                    )
                    or not all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(float(value))
                        for value in fraction_values.values()
                    )
                    or sidecar.get("fit") not in {"pad", "fill", "stretch"}
                    or not isinstance(sidecar.get("bg"), str)
                    or not isinstance(sidecar.get("panel_frame_color"), str)
                    or input_mode not in {"composite", "inputs"}
                ):
                    return True, [f"Asset {asset.name} has malformed recompose-panels parameters."]
                if input_mode == "composite":
                    assert source is not None
                    composite_path: Path | None = source
                    input_paths: list[str] = []
                else:
                    if not isinstance(source_inputs, list) or not source_inputs or not all(
                        isinstance(value, str) and value.strip() for value in source_inputs
                    ):
                        return True, [f"Asset {asset.name} has malformed recompose input sources."]
                    composite_path = None
                    input_paths = [
                        str(_resolve_path(value, asset.parent)) for value in source_inputs
                    ]
                    if not all(Path(value).is_file() for value in input_paths):
                        return True, [f"Asset {asset.name} recompose input source is missing."]
                replay_args = argparse.Namespace(
                    output=str(regenerated),
                    inputs=input_paths,
                    composite=str(composite_path) if composite_path is not None else None,
                    fit=sidecar["fit"],
                    bg=sidecar["bg"],
                    panel_frame_color=sidecar["panel_frame_color"],
                    **integer_values,
                    **fraction_values,
                )
                # The compositor's normal CLI progress message must never leak
                # into callers that promised machine-readable JSON on stdout.
                with redirect_stdout(io.StringIO()):
                    postprocess_assets.recompose_panels_command(replay_args)
            elif command in {"recompose-panels-aligned", "recompose-panels-banded"}:
                source_inputs = sidecar.get("source_inputs")
                labels = sidecar.get("labels")
                if not isinstance(source_inputs, list) or not source_inputs or not all(
                    isinstance(value, str) and value.strip() for value in source_inputs
                ) or not isinstance(labels, list) or not all(
                    isinstance(value, str) for value in labels
                ):
                    return True, [f"Asset {asset.name} has malformed compositor sources/labels."]
                resolved_inputs = [
                    str(_resolve_path(value, asset.parent)) for value in source_inputs
                ]
                if not all(Path(value).is_file() for value in resolved_inputs):
                    return True, [f"Asset {asset.name} compositor source is missing."]
                script = Path(__file__).with_name(
                    "recompose_panels_aligned.py"
                    if command == "recompose-panels-aligned"
                    else "recompose_panels_banded.py"
                )
                invocation = [
                    sys.executable, str(script), str(regenerated),
                    "--inputs", *resolved_inputs,
                ]
                if labels:
                    invocation.extend(("--labels", ",".join(labels)))
                if command == "recompose-panels-aligned":
                    required_integers = (
                        "cols", "font_size", "gap", "edge_white_thr",
                        "panel_frame", "safety_margin_px",
                    )
                    required_numbers = (
                        "slide_box_w_in", "slide_box_h_in", "edge_white_frac",
                    )
                    if not all(
                        isinstance(sidecar.get(name), int)
                        and not isinstance(sidecar.get(name), bool)
                        for name in required_integers
                    ) or not all(
                        isinstance(sidecar.get(name), (int, float))
                        and not isinstance(sidecar.get(name), bool)
                        and math.isfinite(float(sidecar[name]))
                        for name in required_numbers
                    ) or sidecar.get("row_height") not in {"min", "median"} or not all(
                        isinstance(sidecar.get(name), bool)
                        for name in ("equal_row_width", "label_bold")
                    ) or not all(
                        isinstance(sidecar.get(name), str)
                        for name in ("label_color", "bg")
                    ):
                        return True, [f"Asset {asset.name} has malformed aligned-compositor parameters."]
                    target_label = sidecar.get("label_screen_height_in")
                    if target_label is not None and (
                        not isinstance(target_label, (int, float))
                        or isinstance(target_label, bool)
                        or not math.isfinite(float(target_label))
                    ):
                        return True, [f"Asset {asset.name} has invalid label_screen_height_in."]
                    invocation.extend((
                        "--cols", str(sidecar["cols"]),
                        "--font-size", str(sidecar["font_size"]),
                        "--slide-box-w-in", str(sidecar["slide_box_w_in"]),
                        "--slide-box-h-in", str(sidecar["slide_box_h_in"]),
                        "--label-color", sidecar["label_color"],
                        "--bg", sidecar["bg"],
                        "--gap", str(sidecar["gap"]),
                        "--row-height", sidecar["row_height"],
                        "--edge-white-thr", str(sidecar["edge_white_thr"]),
                        "--edge-white-frac", str(sidecar["edge_white_frac"]),
                        "--panel-frame", str(sidecar["panel_frame"]),
                        "--safety-margin-px", str(sidecar["safety_margin_px"]),
                    ))
                    if target_label is not None:
                        invocation.extend(("--label-screen-height-in", str(target_label)))
                    if not sidecar["equal_row_width"]:
                        invocation.append("--no-equal-row-width")
                    if sidecar["label_bold"]:
                        invocation.append("--label-bold")
                    frame_color = sidecar.get("panel_frame_color")
                    if frame_color is not None:
                        if not isinstance(frame_color, str):
                            return True, [f"Asset {asset.name} has invalid panel_frame_color."]
                        invocation.extend(("--panel-frame-color", frame_color))
                else:
                    required_integers = (
                        "gap", "safety_margin_px", "max_edge_px", "max_boundary_shift_px",
                    )
                    required_numbers = (
                        "gap_above_in", "gap_below_in", "label_pt", "glyph_ratio",
                        "center_offset_in", "slide_box_w_in", "slide_box_h_in",
                    )
                    if not all(
                        isinstance(sidecar.get(name), int)
                        and not isinstance(sidecar.get(name), bool)
                        for name in required_integers
                    ) or not all(
                        isinstance(sidecar.get(name), (int, float))
                        and not isinstance(sidecar.get(name), bool)
                        and math.isfinite(float(sidecar[name]))
                        for name in required_numbers
                    ) or sidecar.get("requested_source_label_policy") not in {
                        "auto", "preserve", "crop-safe-margin"
                    } or sidecar.get("asset_type") not in {
                        "clinical-image", "figure"
                    } or not isinstance(sidecar.get("no_trim"), bool) or not isinstance(
                        sidecar.get("padding_background"), str
                    ):
                        return True, [f"Asset {asset.name} has malformed banded-compositor parameters."]
                    geometry = Path(temporary) / "geometry.json"
                    invocation.extend((
                        "--asset-type", str(sidecar.get("asset_type", "figure")),
                        "--layout-template", str(sidecar.get("layout_template", "grid")),
                        "--geometry", str(geometry),
                        "--gap-above-in", str(sidecar["gap_above_in"]),
                        "--gap-below-in", str(sidecar["gap_below_in"]),
                        "--label-pt", str(sidecar["label_pt"]),
                        "--glyph-ratio", str(sidecar["glyph_ratio"]),
                        "--center-offset-in", str(sidecar["center_offset_in"]),
                        "--slide-box-w-in", str(sidecar["slide_box_w_in"]),
                        "--slide-box-h-in", str(sidecar["slide_box_h_in"]),
                        "--bg", sidecar["padding_background"],
                        "--gap", str(sidecar["gap"]),
                        "--safety-margin-px", str(sidecar["safety_margin_px"]),
                        "--source-label-policy", sidecar["requested_source_label_policy"],
                        "--max-edge-px", str(sidecar["max_edge_px"]),
                        "--max-boundary-shift-px", str(sidecar["max_boundary_shift_px"]),
                    ))
                    requested_cols = sidecar.get("requested_cols")
                    if requested_cols is not None:
                        if not isinstance(requested_cols, int) or isinstance(requested_cols, bool):
                            return True, [f"Asset {asset.name} has invalid requested_cols."]
                        invocation.extend(("--cols", str(requested_cols)))
                    if sidecar["no_trim"]:
                        invocation.append("--no-trim")
                subprocess.run(invocation, check=True, capture_output=True, text=True)
            else:
                import postprocess_assets

                assert source is not None

                values = {
                    key: sidecar.get(key)
                    for key in (
                        "split_y", "repeat_header_y", "crop_left", "crop_top",
                        "crop_right", "crop_bottom", "threshold", "margin",
                    )
                }
                if not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in values.values()
                ) or sidecar.get("part") not in {"top", "bottom"}:
                    return True, [f"Asset {asset.name} has malformed split-table parameters."]
                with Image.open(source) as opened:
                    image = opened.convert("RGB")
                x0, y0 = max(0, values["crop_left"]), max(0, values["crop_top"])
                x1 = image.width - max(0, values["crop_right"])
                y1 = image.height - max(0, values["crop_bottom"])
                image = image.crop((x0, y0, x1, y1))
                split_y = values["split_y"] - y0
                header_y = values["repeat_header_y"] - y0
                header = image.crop((0, 0, image.width, header_y))
                top = image.crop((0, 0, image.width, split_y))
                bottom_body = image.crop((0, split_y, image.width, image.height))
                bottom = Image.new("RGB", (image.width, header.height + bottom_body.height), "white")
                bottom.paste(header, (0, 0))
                bottom.paste(bottom_body, (0, header.height))
                cores = [
                    part.crop(postprocess_assets.content_bbox(part, values["threshold"]))
                    for part in (top, bottom)
                ]
                max_width = max(core.width for core in cores)
                core = cores[0 if sidecar["part"] == "top" else 1]
                margin = values["margin"]
                canvas = Image.new(
                    "RGB", (max_width + 2 * margin, core.height + 2 * margin), "white"
                )
                canvas.paste(core, (margin + (max_width - core.width) // 2, margin))
                canvas.save(regenerated, quality=95)
            matches = _decoded_rgb_equal(asset, regenerated)
    except (
        OSError, ValueError, TypeError, KeyError, SystemExit,
        subprocess.CalledProcessError,
    ) as error:
        return True, [f"Asset {asset.name} deterministic helper replay failed: {error}."]
    return True, [] if matches else [
        f"Asset {asset.name} pixels do not match a deterministic replay of helper {command!r}."
    ]


def _composite_evidence(asset: Path, sidecar: dict[str, Any]) -> list[str]:
    """Verify that every declared input is visibly present in its recorded panel box."""
    failures: list[str] = []
    sources = sidecar.get("source_inputs")
    boxes = sidecar.get("panel_boxes_px") or sidecar.get("panel_boxes")
    if not isinstance(sources, list) or len(sources) < 2:
        return [f"Composite {asset.name} must declare at least two source_inputs."]
    if not isinstance(boxes, list) or len(boxes) != len(sources):
        return [
            f"Composite {asset.name} requires one panel_boxes_px entry per source input "
            "for content authentication."
        ]
    try:
        with Image.open(asset) as opened:
            if not _is_fully_opaque(opened):
                return [f"Composite {asset.name} contains transparency."]
            composite = opened.convert("RGB")
    except OSError as error:
        return [f"Composite {asset.name} is unreadable: {error}."]
    for panel_index, (source_value, box) in enumerate(zip(sources, boxes), start=1):
        if not isinstance(source_value, str) or not isinstance(box, dict):
            failures.append(f"Composite {asset.name} panel {panel_index} evidence is malformed.")
            continue
        try:
            x = int(box["x"])
            y = int(box["y"])
            width = int(box["w"])
            height = int(box["h"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"Composite {asset.name} panel {panel_index} box is malformed.")
            continue
        if (
            width <= 0 or height <= 0 or x < 0 or y < 0
            or x + width > composite.width or y + height > composite.height
        ):
            failures.append(f"Composite {asset.name} panel {panel_index} box is outside the raster.")
            continue
        source = _resolve_path(source_value, asset.parent)
        if not source.is_file() or source.suffix.lower() not in RASTER_SUFFIXES:
            failures.append(f"Composite {asset.name} panel {panel_index} source is unavailable.")
            continue
        try:
            with Image.open(source) as source_image:
                if not _is_fully_opaque(source_image):
                    failures.append(
                        f"Composite {asset.name} panel {panel_index} source contains transparency."
                    )
                    continue
                reference = source_image.convert("RGB")
            candidate = composite.crop((x, y, x + width, y + height))
            accepted, result = _visual_match(candidate, reference)
        except (OSError, ValueError) as error:
            failures.append(f"Composite {asset.name} panel {panel_index} cannot be compared: {error}.")
            continue
        if not accepted:
            failures.append(
                f"Composite {asset.name} panel {panel_index} does not match its declared source "
                f"(polarity={result['status']}, RGB MAE={result['rgb_mae']:.2f})."
            )
    return failures


def audit_final_assets(spec_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Reject final figures that descend from known inverted embedded streams."""
    if not isinstance(report, dict):
        return {"ok": False, "checked_assets": 0, "failures": ["Polarity report must be an object."]}
    figure_values = report.get("figures", [])
    if not isinstance(figure_values, list):
        return {"ok": False, "checked_assets": 0, "failures": ["Polarity report figures must be a list."]}
    report_figures = [finding for finding in figure_values if isinstance(finding, dict)]
    spec_path = spec_path.expanduser().resolve()
    if not spec_path.is_file():
        return {"ok": False, "failures": [f"Deck specification not found: {spec_path}"]}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return {"ok": False, "checked_assets": 0, "failures": [f"Deck specification is unreadable: {error}"]}
    if not isinstance(spec, dict) or not isinstance(spec.get("slides"), list):
        return {"ok": False, "checked_assets": 0, "failures": ["Deck specification must contain a slides list."]}
    failures: list[str] = []
    checked = 0
    map_context: dict[str, Any] | None = None
    map_usage: dict[str, list[int]] = {}
    asset_map_path = article_asset_map.map_path_from_spec(spec_path, spec)
    if asset_map_path is not None:
        candidate_context = article_asset_map.validate_map(asset_map_path)
        failures.extend(candidate_context.get("failures", []))
        if candidate_context.get("ok") is True:
            map_context = candidate_context
            audited_pdf = report.get("source_pdf")
            if (
                isinstance(audited_pdf, str)
                and Path(audited_pdf).expanduser().resolve()
                != candidate_context["source_pdf"]
            ):
                failures.append(
                    "Article asset map source PDF differs from the freshly audited extraction PDF."
                )
    unsafe = {
        Path(finding["source_path"]).resolve(): finding
        for finding in report_figures
        if finding.get("raw", {}).get("status") == "inverted"
    }
    known_raw = {
        Path(finding["source_path"]).resolve()
        for finding in report_figures
        if isinstance(finding.get("source_path"), str)
    }
    raw_values = report.get("known_raw_paths")
    if isinstance(raw_values, list):
        known_raw.update(
            Path(value).expanduser().resolve()
            for value in raw_values
            if isinstance(value, str) and value
        )
    trusted = _trusted_terminal_sources(report)
    trusted_documents = _trusted_document_sources(report)
    reference_by_path = {
        Path(finding["rendered_path"]).expanduser().resolve(): finding
        for finding in report_figures
        if isinstance(finding.get("rendered_path"), str)
        and finding.get("rendered_polarity", {}).get("status") == "correct"
    }
    verified_references = report.get("verified_references")
    authenticated_pages: set[int] = set()
    if isinstance(verified_references, list):
        for entry in verified_references:
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                reference_by_path[Path(entry["path"]).expanduser().resolve()] = entry
            if (
                isinstance(entry, dict)
                and entry.get("kind") == "page"
                and isinstance(entry.get("page"), int)
                and not isinstance(entry.get("page"), bool)
            ):
                authenticated_pages.add(entry["page"])

    for index, slide in enumerate(spec.get("slides", []), start=1):
        if not isinstance(slide, dict) or not slide.get("image"):
            continue
        asset = _resolve_path(str(slide["image"]), spec_path.parent)
        sidecar_path = asset.with_suffix(asset.suffix + POSTPROCESS_SUFFIX)
        if not asset.is_file():
            failures.append(f"Slide {index}: final image asset is missing: {asset}.")
            continue
        suffix = asset.suffix.lower()
        if suffix not in RASTER_SUFFIXES | vector_table.VECTOR_SUFFIXES:
            failures.append(
                f"Slide {index}: unsupported slide-image format {asset.suffix!r}; "
                "use an authenticated raster or vector-table EMF."
            )
            continue
        if not sidecar_path.is_file():
            failures.append(
                f"Slide {index}: final image {asset.name} has no provenance sidecar "
                f"({sidecar_path.name})."
            )
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            failures.append(f"Slide {index}: final image {asset.name} has an unreadable sidecar: {error}.")
            continue
        if not isinstance(sidecar, dict):
            failures.append(f"Slide {index}: final image {asset.name} has an invalid sidecar.")
            continue
        mapped_entry: dict[str, Any] | None = None
        if map_context is not None:
            source_asset_id = slide.get("source_asset_id")
            caption_value = " ".join(
                str(value) for value in (slide.get("caption"), slide.get("title")) if value
            )
            caption_match = re.search(
                r"\b(Figure|Table)\s*([1-9][0-9]*)\b", caption_value, re.IGNORECASE
            )
            if caption_match is not None and not (
                isinstance(source_asset_id, str) and source_asset_id.strip()
            ):
                failures.append(
                    f"Slide {index}: paper {caption_match.group(1)} {caption_match.group(2)} "
                    "requires source_asset_id from the article asset map."
                )
            if isinstance(source_asset_id, str) and source_asset_id.strip():
                source_asset_id = source_asset_id.strip()
                mapped_entry = map_context["assets"].get(source_asset_id)
                if mapped_entry is None:
                    failures.append(
                        f"Slide {index}: source_asset_id {source_asset_id!r} is absent from "
                        "the article asset map."
                    )
                else:
                    map_usage.setdefault(source_asset_id, []).append(index)
                    if caption_match is None:
                        failures.append(
                            f"Slide {index}: mapped source {source_asset_id} lacks a matching "
                            "Figure/Table caption or title."
                        )
                    else:
                        caption_id = (
                            f"{caption_match.group(1).lower()}:{int(caption_match.group(2))}"
                        )
                        if caption_id != source_asset_id:
                            failures.append(
                                f"Slide {index}: caption identifies {caption_id}, but "
                                f"source_asset_id is {source_asset_id}."
                            )
        if suffix in vector_table.VECTOR_SUFFIXES:
            source_pdf = report.get("source_pdf")
            source_pdf_sha256 = report.get("source_pdf_sha256")
            if report.get("ok") is not True:
                failures.append(
                    f"Slide {index}: vector table {asset.name} requires a successful "
                    "fresh extraction audit."
                )
            if not isinstance(source_pdf, str) or not source_pdf:
                failures.append(
                    f"Slide {index}: vector table {asset.name} has no audited source PDF."
                )
            elif (
                not isinstance(source_pdf_sha256, str)
                or SHA256_RE.fullmatch(source_pdf_sha256) is None
            ):
                failures.append(
                    f"Slide {index}: vector table {asset.name} has no authenticated PDF SHA-256."
                )
            else:
                vector_failures = vector_table.replay_vector_table(
                    asset,
                    sidecar,
                    audited_pdf=Path(source_pdf),
                    audited_pdf_sha256=source_pdf_sha256,
                    authenticated_pages=authenticated_pages,
                )
                failures.extend(
                    f"Slide {index}: {failure}" for failure in vector_failures
                )
            checked += 1
            continue
        asset_type = str(sidecar.get("asset_type", "figure")).lower()
        helper_handled, helper_failures = _deterministic_helper_evidence(asset, sidecar)
        failures.extend(f"Slide {index}: {failure}" for failure in helper_failures)
        sidecar_sources: list[str] = []
        if isinstance(sidecar.get("source"), str):
            sidecar_sources.append(sidecar["source"])
        if isinstance(sidecar.get("source_inputs"), list):
            sidecar_sources.extend(
                value for value in sidecar["source_inputs"] if isinstance(value, str)
            )
        reaches_pdf_directly = any(
            _resolve_path(value, asset.parent) in trusted_documents for value in sidecar_sources
        )
        allow_direct_pdf = False
        if asset_type == "flowchart" and reaches_pdf_directly:
            flowchart_failures = _flowchart_evidence(sidecar, asset, report)
            failures.extend(f"Slide {index}: {failure}" for failure in flowchart_failures)
            allow_direct_pdf = not flowchart_failures
        provenance, provenance_failures = _provenance_paths(
            sidecar,
            asset,
            trusted=trusted,
            known_raw=known_raw,
            trusted_documents=trusted_documents,
            allow_document_terminal=allow_direct_pdf,
        )
        failures.extend(f"Slide {index}: {failure}" for failure in provenance_failures)
        if mapped_entry is not None:
            expected_terminals = set(mapped_entry.get("resolved_source_bindings", []))
            actual_terminals = {path for path in provenance if path in trusted}
            if actual_terminals != expected_terminals:
                expected_names = ", ".join(sorted(path.name for path in expected_terminals))
                actual_names = ", ".join(sorted(path.name for path in actual_terminals))
                failures.append(
                    f"Slide {index}: {mapped_entry['asset_id']} provenance terminates at "
                    f"[{actual_names}], expected caption-bound source [{expected_names}]."
                )

        # Unsafe raw streams must be rejected for every asset type, including
        # tables and flowcharts, before any correlation exemptions are applied.
        for candidate in dict.fromkeys(provenance):
            finding = unsafe.get(candidate)
            if finding is not None:
                failures.append(
                    f"Slide {index} uses inverted raw PDF image {candidate.name} "
                    f"from page {finding['page']}; rebuild it from "
                    f"{finding['rendered']} instead."
                )

        source_inputs = sidecar.get("source_inputs")
        panel_count = sidecar.get("panels", 1)
        composite = (
            isinstance(source_inputs, list) and len(source_inputs) > 1
        ) or (
            isinstance(panel_count, int) and panel_count > 1
        )
        if composite:
            supported_compositors = {
                "recompose-panels",
                "recompose-panels-aligned",
                "recompose-panels-banded",
            }
            if sidecar.get("command") not in supported_compositors:
                failures.append(
                    f"Slide {index}: final composite {asset.name} uses unsupported "
                    f"command {sidecar.get('command')!r}."
                )
            # Exact compositor replay authenticates the complete raster and all
            # of its transforms. Unknown legacy compositors must instead prove
            # each declared panel box against its source.
            if not helper_handled:
                composite_failures = _composite_evidence(asset, sidecar)
                failures.extend(f"Slide {index}: {failure}" for failure in composite_failures)
        elif not helper_handled and not allow_direct_pdf:
            failures.append(
                f"Slide {index}: final raster {asset.name} uses unsupported or "
                f"non-replayable command {sidecar.get('command')!r}."
            )
        candidates = (
            provenance
            if composite or helper_handled or allow_direct_pdf
            else [asset, *provenance]
        )
        for candidate in dict.fromkeys(candidates):
            if candidate in unsafe or candidate in reference_by_path or candidate in trusted:
                continue

            if not candidate.is_file() or candidate.suffix.lower() not in RASTER_SUFFIXES:
                continue
            candidate_sidecar_path = candidate.with_suffix(
                candidate.suffix + POSTPROCESS_SUFFIX
            )
            if candidate_sidecar_path.is_file():
                try:
                    candidate_sidecar = json.loads(
                        candidate_sidecar_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    candidate_sidecar = None
                if isinstance(candidate_sidecar, dict):
                    replayed, replay_failures = _deterministic_helper_evidence(
                        candidate, candidate_sidecar
                    )
                    failures.extend(
                        f"Slide {index}: {failure}" for failure in replay_failures
                    )
                    if replayed:
                        continue
            corresponding, reference_failures = _rendered_references_for(
                candidate,
                trusted=trusted,
                known_raw=known_raw,
                trusted_documents=trusted_documents,
                allow_document_terminal=allow_direct_pdf,
                reference_by_path=reference_by_path,
            )
            failures.extend(f"Slide {index}: {failure}" for failure in reference_failures)
            if not corresponding:
                if not (allow_direct_pdf and candidate == asset):
                    failures.append(
                        f"Slide {index} source {candidate.name} has no comparable authenticated "
                        "PDF-rendered reference."
                    )
                continue
            try:
                with Image.open(candidate) as actual:
                    if not _is_fully_opaque(actual):
                        failures.append(f"Slide {index} source {candidate.name} contains transparency.")
                        continue
                    accepted_results: list[dict[str, Any]] = []
                    attempted: list[dict[str, Any]] = []
                    for reference_path in corresponding:
                        if not reference_path.is_file():
                            continue
                        with Image.open(reference_path) as expected:
                            accepted, result = _visual_match(actual, expected)
                        attempted.append(result)
                        if accepted:
                            accepted_results.append(result)
                    if not accepted_results:
                        detail = attempted[0] if attempted else {"status": "unavailable", "rgb_mae": float("inf")}
                        failures.append(
                            f"Slide {index} source {candidate.name} does not match its authenticated "
                            f"PDF-rendered reference (polarity={detail['status']}, "
                            f"RGB MAE={detail['rgb_mae']:.2f})."
                        )
            except (OSError, ValueError) as error:
                failures.append(
                    f"Slide {index} source {candidate.name} is not a readable raster image: {error}."
                )
        checked += 1

    if map_context is not None:
        for asset_id, entry in map_context["assets"].items():
            slides = map_usage.get(asset_id, [])
            if entry.get("kind") == "figure" and len(slides) != 1:
                failures.append(
                    f"Article asset map {asset_id} must appear on exactly one slide; "
                    f"found {len(slides)}."
                )
            elif entry.get("kind") == "table" and not slides:
                failures.append(
                    f"Article asset map {asset_id} is not used by any table slide."
                )

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
