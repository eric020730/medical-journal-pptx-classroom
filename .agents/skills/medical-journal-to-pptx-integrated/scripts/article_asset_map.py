#!/usr/bin/env python3
"""Validate article Figure/Table numbers against authenticated PDF assets.

The extraction manifest numbers files in PDF object order.  This module binds
article identifiers such as ``figure:4`` to the actual manifest entry adjacent
to the article caption, then lets deck QA compare that binding with recursive
final-image provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any

import pymupdf


SCHEMA = "medical-journal-article-asset-map/v1"
EXTRACTION_SCHEMA = "medical-journal-extraction-manifest/v1"
NORMALIZER = "caption-nfkc-whitespace-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CROP_BINDING = "reviewed-pdf-crop-plan-v1"
CROP_ASSOCIATION = "caption-in-reviewed-table-header-v1"
ASSET_ID_RE = re.compile(r"^(figure|table):([1-9][0-9]*)$", re.IGNORECASE)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_caption(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def caption_sha256(value: str) -> str:
    return hashlib.sha256(normalize_caption(value).encode("utf-8")).hexdigest()


def _resolved(value: str, base: Path) -> Path:
    candidate = Path(value).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _bbox(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict):
        value = [value.get(name) for name in ("x0", "y0", "x1", "y1")]
    if not (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
    ):
        return None
    box = tuple(float(item) for item in value)
    return box if box[0] < box[2] and box[1] < box[3] else None


def _horizontal_overlap_fraction(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    denominator = min(left[2] - left[0], right[2] - right[0])
    return overlap / denominator if denominator > 0 else 0.0


def _manifest_entry_by_file(manifest: dict[str, Any], collection: str, name: str):
    values = manifest.get(collection)
    if not isinstance(values, list):
        return None
    matches = [
        entry for entry in values
        if isinstance(entry, dict) and entry.get("file") == name
    ]
    return matches[0] if len(matches) == 1 else None


def _nearest_spatial_binding(
    manifest: dict[str, Any],
    collection: str,
    page: int,
    caption_box: tuple[float, float, float, float],
    method: str,
) -> str | None:
    candidates: list[tuple[float, float, str]] = []
    for entry in manifest.get(collection, []):
        if not isinstance(entry, dict) or entry.get("page") != page:
            continue
        asset_box = _bbox(entry.get("bbox_pt"))
        name = entry.get("file")
        if asset_box is None or not isinstance(name, str):
            continue
        overlap = _horizontal_overlap_fraction(asset_box, caption_box)
        if overlap < 0.20:
            continue
        if method == "nearest-preceding-x-overlap-v1" and asset_box[3] <= caption_box[1] + 2:
            gap = max(0.0, caption_box[1] - asset_box[3])
        elif method == "nearest-following-x-overlap-v1" and asset_box[1] >= caption_box[3] - 2:
            gap = max(0.0, asset_box[1] - caption_box[3])
        else:
            continue
        candidates.append((gap, -overlap, name))
    return min(candidates)[2] if candidates else None


def map_path_from_spec(spec_path: Path, specification: dict[str, Any]) -> Path | None:
    meta = specification.get("meta")
    value = meta.get("article_asset_map") if isinstance(meta, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    return _resolved(value, spec_path.parent)


def _reviewed_table_crop(binding, *, base, source_pdf, source_hash,
                         document, caption_page, caption_box, caption_text, number):
    """Authenticate a reviewed table independently of extraction detection.

    A PDF/page hash is not table identity. Bind the reviewed asset object and
    renderer settings, and replay the table title inside its own top header.
    """
    from source_crops import region

    if not isinstance(binding.get("plan"), str) or not binding["plan"].strip():
        raise ValueError("reviewed crop requires a plan path")
    plan_path = _resolved(binding["plan"], base)
    if (not isinstance(binding.get("plan_sha256"), str)
            or SHA256_RE.fullmatch(binding["plan_sha256"]) is None
            or sha256_path(plan_path) != binding["plan_sha256"]):
        raise ValueError("reviewed crop plan SHA-256 differs from the reviewed binding")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if (not isinstance(plan, dict) or not isinstance(plan.get("pdf"), str)
            or _resolved(plan["pdf"], plan_path.parent) != source_pdf
            or plan.get("source_sha256") != source_hash):
        raise ValueError("reviewed crop plan must use the authenticated source PDF/hash")
    assets = plan.get("assets")
    expected = plan.get("expected_assets")
    if (not isinstance(assets, list) or not assets
            or not all(isinstance(a, dict) and isinstance(a.get("id"), str) for a in assets)):
        raise ValueError("reviewed crop plan has malformed asset inventory")
    ids = [a["id"] for a in assets]
    if (len(ids) != len(set(ids)) or not isinstance(expected, list)
            or not all(isinstance(a, str) for a in expected) or sorted(ids) != sorted(expected)):
        raise ValueError("reviewed crop plan asset inventory is duplicate or incomplete")
    selected = [a for a in assets if a["id"] == binding.get("asset_id")]
    if len(selected) != 1 or selected[0].get("type") != "table":
        raise ValueError("reviewed crop binding must select exactly one table plan asset")
    asset = selected[0]
    page_number = binding.get("page")
    if (type(page_number) is not int or page_number != asset.get("page")
            or page_number != caption_page or document is None
            or not 1 <= page_number <= len(document)):
        raise ValueError("reviewed crop page differs from the table/caption page")
    bbox = _bbox(binding.get("bbox_pt"))
    header = _bbox(binding.get("header_bbox_pt"))
    if bbox is None or bbox != _bbox(asset.get("bbox")) or header is None:
        raise ValueError("reviewed crop bbox differs from plan or header bbox is invalid")
    if (not pymupdf.Rect(bbox).contains(pymupdf.Rect(header))
            or header[:3] != bbox[:3]
            or caption_box is None or not pymupdf.Rect(header).contains(pymupdf.Rect(caption_box))):
        raise ValueError("caption must lie inside the full-width top header of the reviewed crop")
    if asset.get("splits") and header[3] > asset.get("header_bottom", float('-inf')):
        raise ValueError("caption header exceeds the repeated split-table header")
    anchors = asset.get("expected_text")
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("reviewed table crop requires nonempty text anchors")
    page = document[page_number - 1]
    region(page, list(bbox), anchors)
    # Read in page coordinates, not PDF object order. The header must begin
    # with the replayed caption, not a body-text mention of another table.
    header_text = normalize_caption(page.get_text("text", clip=pymupdf.Rect(header), sort=True))
    if not caption_text or not header_text.startswith(caption_text):
        raise ValueError("reviewed table header must begin with the authenticated caption")
    crop_text = page.get_text("text", clip=pymupdf.Rect(bbox), sort=True)
    labels = re.findall(r"(?i)\btable\s+([1-9][0-9]*)\b", crop_text)
    if not labels or set(labels) != {number}:
        raise ValueError("reviewed crop contains another table title or no table title")
    dpi = plan.get("dpi", 300)
    if (isinstance(dpi, bool) or not isinstance(dpi, (int, float))
            or not math.isfinite(dpi) or not 72 <= dpi <= 600):
        raise ValueError("reviewed crop plan dpi must be finite within 72..600")
    return {"plan_path": plan_path, "plan_sha256": binding["plan_sha256"],
            "asset_id": asset["id"], "asset": asset, "page": page_number,
            "bbox_pt": list(bbox), "dpi": dpi, "source_pdf": source_pdf,
            "source_sha256": source_hash}


def validate_map(map_path: Path) -> dict[str, Any]:
    """Return validated map context and fail closed on stale caption/source evidence."""
    map_path = map_path.expanduser().resolve()
    failures: list[str] = []
    try:
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"ok": False, "failures": [f"Article asset map is unreadable: {error}"]}
    if not isinstance(mapping, dict):
        return {"ok": False, "failures": ["Article asset map must be a JSON object."]}
    if mapping.get("schema") != SCHEMA:
        failures.append(f"Unsupported article asset map schema: {mapping.get('schema')!r}.")

    source_value = mapping.get("source_pdf")
    manifest_value = mapping.get("extraction_manifest")
    if not isinstance(source_value, str) or not source_value.strip():
        failures.append("Article asset map requires source_pdf.")
        source_pdf = map_path
    else:
        source_pdf = _resolved(source_value, map_path.parent)
    if not isinstance(manifest_value, str) or not manifest_value.strip():
        failures.append("Article asset map requires extraction_manifest.")
        manifest_path = map_path
    else:
        manifest_path = _resolved(manifest_value, map_path.parent)

    try:
        source_hash = sha256_path(source_pdf)
    except OSError as error:
        failures.append(f"Article asset map source PDF is unavailable: {error}.")
        source_hash = ""
    if mapping.get("source_pdf_sha256") != source_hash:
        failures.append("Article asset map source_pdf_sha256 does not match the PDF.")
    try:
        manifest_bytes_hash = sha256_path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"Article asset map extraction manifest is unavailable: {error}.")
        manifest = {}
        manifest_bytes_hash = ""
    if mapping.get("extraction_manifest_sha256") != manifest_bytes_hash:
        failures.append(
            "Article asset map extraction_manifest_sha256 does not match the manifest."
        )
    if not isinstance(manifest, dict):
        failures.append("Article asset map extraction manifest must be an object.")
        manifest = {}
    if manifest.get("schema") != EXTRACTION_SCHEMA:
        failures.append("Article asset map references an unsupported extraction manifest.")
    if source_hash and manifest.get("pdf_sha256") != source_hash:
        failures.append("Article asset map PDF does not match the extraction manifest PDF.")

    try:
        document = pymupdf.open(source_pdf)
    except Exception as error:
        failures.append(f"Article asset map source PDF cannot be opened: {error}.")
        document = None

    values = mapping.get("assets")
    if not isinstance(values, list) or not values:
        failures.append("Article asset map requires a non-empty assets list.")
        values = []
    index: dict[str, dict[str, Any]] = {}
    used_figure_sources: dict[str, str] = {}
    for position, entry in enumerate(values, start=1):
        prefix = f"Article asset map item {position}"
        if not isinstance(entry, dict):
            failures.append(f"{prefix} must be an object.")
            continue
        asset_id = entry.get("asset_id")
        match = ASSET_ID_RE.fullmatch(asset_id) if isinstance(asset_id, str) else None
        if match is None:
            failures.append(f"{prefix} has invalid asset_id={asset_id!r}.")
            continue
        canonical_id = f"{match.group(1).lower()}:{int(match.group(2))}"
        if canonical_id != asset_id:
            failures.append(f"{prefix} asset_id must use canonical lowercase form {canonical_id!r}.")
        if canonical_id in index:
            failures.append(f"Article asset map duplicates {canonical_id}.")
            continue
        kind = match.group(1).lower()
        number = str(int(match.group(2)))
        if entry.get("kind") != kind or str(entry.get("number")) != number:
            failures.append(f"{prefix} kind/number do not match {canonical_id}.")

        caption = entry.get("caption_evidence")
        if not isinstance(caption, dict):
            failures.append(f"{prefix} lacks caption_evidence.")
            continue
        page = caption.get("page")
        caption_box = _bbox(caption.get("bbox_pt"))
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            failures.append(f"{prefix} caption page must be a positive integer.")
        if caption_box is None:
            failures.append(f"{prefix} caption bbox_pt is invalid.")
        if caption.get("normalizer") != NORMALIZER:
            failures.append(f"{prefix} caption normalizer must be {NORMALIZER}.")
        declared_text = caption.get("normalized_text")
        declared_digest = caption.get("normalized_text_sha256")
        if not isinstance(declared_text, str) or not declared_text.strip():
            failures.append(f"{prefix} caption normalized_text is empty.")
        elif normalize_caption(declared_text) != declared_text:
            failures.append(f"{prefix} caption normalized_text is not canonical.")
        if not isinstance(declared_digest, str) or SHA256_RE.fullmatch(declared_digest) is None:
            failures.append(f"{prefix} caption normalized_text_sha256 is invalid.")
        elif isinstance(declared_text, str) and caption_sha256(declared_text) != declared_digest:
            failures.append(f"{prefix} caption text hash is inconsistent.")

        actual_caption = ""
        if (
            document is not None
            and isinstance(page, int)
            and not isinstance(page, bool)
            and 1 <= page <= len(document)
            and caption_box is not None
        ):
            actual_caption = normalize_caption(
                document[page - 1].get_text("text", clip=pymupdf.Rect(*caption_box), sort=True)
            )
            if actual_caption != declared_text:
                failures.append(f"{prefix} caption evidence does not replay from the PDF.")
            caption_label = r"(?:figure|fig\.?)" if kind == "figure" else "table"
            caption_pattern = re.compile(
                rf"^{caption_label}\s*{re.escape(number)}(?:\s*[.:\u2013\u2014-]|\b)",
                re.IGNORECASE,
            )
            if caption_pattern.search(actual_caption) is None:
                failures.append(
                    f"{prefix} caption does not begin with {kind.title()} {number}."
                )

        bindings = entry.get("source_bindings")
        if not isinstance(bindings, list) or not bindings:
            failures.append(f"{prefix} requires source_bindings.")
            bindings = []
        resolved_crop_bindings: list[dict[str, Any]] = []
        crop_bindings_declared = False
        resolved_bindings: list[Path] = []
        bound_names: list[str] = []
        for binding_index, binding in enumerate(bindings, start=1):
            if not isinstance(binding, dict):
                failures.append(f"{prefix} source binding {binding_index} must be an object.")
                continue
            if binding.get("type") == CROP_BINDING:
                crop_bindings_declared = True
                if kind != "table" or len(bindings) != 1:
                    failures.append(f"{prefix} reviewed crop requires exactly one table binding; no mixed roots.")
                    continue
                if any(key in binding for key in ("manifest_collection", "manifest_file")):
                    failures.append(f"{prefix} reviewed crop cannot also declare a manifest root.")
                try:
                    resolved_crop_bindings.append(_reviewed_table_crop(
                        binding, base=map_path.parent, source_pdf=source_pdf,
                        source_hash=source_hash, document=document, caption_page=page,
                        caption_box=caption_box, caption_text=actual_caption, number=number,
                    ))
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                    failures.append(f"{prefix} reviewed crop binding is invalid: {error}.")
                continue
            if "type" in binding:
                failures.append(f"{prefix} unsupported source binding type {binding.get('type')!r}.")
                continue
            collection = binding.get("manifest_collection")
            name = binding.get("manifest_file")
            expected_collection = "figures" if kind == "figure" else "tables"
            if collection != expected_collection or not isinstance(name, str):
                failures.append(
                    f"{prefix} source binding {binding_index} must target {expected_collection}."
                )
                continue
            manifest_entry = _manifest_entry_by_file(manifest, collection, name)
            if manifest_entry is None:
                failures.append(
                    f"{prefix} source binding {binding_index} is not unique in the manifest."
                )
                continue
            if binding.get("sha256") != manifest_entry.get("sha256"):
                failures.append(f"{prefix} source binding hash differs from the manifest.")
            if binding.get("page") != manifest_entry.get("page"):
                failures.append(f"{prefix} source binding page differs from the manifest.")
            path = _resolved(name, manifest_path.parent)
            try:
                if sha256_path(path) != manifest_entry.get("sha256"):
                    failures.append(f"{prefix} bound source bytes differ from the manifest.")
            except OSError as error:
                failures.append(f"{prefix} bound source is unavailable: {error}.")
            resolved_bindings.append(path)
            bound_names.append(name)

        association = entry.get("association")
        method = association.get("method") if isinstance(association, dict) else None
        deterministic_methods = {
            "nearest-preceding-x-overlap-v1",
            "nearest-following-x-overlap-v1",
        }
        if crop_bindings_declared:
            note = association.get("review_note") if isinstance(association, dict) else None
            if method != CROP_ASSOCIATION:
                failures.append(f"{prefix} reviewed crop requires association {CROP_ASSOCIATION}.")
            if not isinstance(note, str) or len(note.strip()) < 16:
                failures.append(f"{prefix} reviewed crop requires a substantive review_note.")
        elif method in deterministic_methods:
            collection = "figures" if kind == "figure" else "tables"
            selected = (
                _nearest_spatial_binding(manifest, collection, page, caption_box, method)
                if isinstance(page, int) and caption_box is not None
                else None
            )
            if len(bound_names) != 1 or selected != bound_names[0]:
                failures.append(
                    f"{prefix} source binding is not the deterministic {method} caption neighbor."
                )
        elif method == "reviewed-source-binding-v1":
            note = association.get("review_note") if isinstance(association, dict) else None
            if not isinstance(note, str) or len(note.strip()) < 16:
                failures.append(f"{prefix} reviewed binding requires a substantive review_note.")
        else:
            failures.append(f"{prefix} has unsupported association method {method!r}.")

        if kind == "figure":
            for name in bound_names:
                prior = used_figure_sources.get(name)
                if prior is not None and prior != canonical_id:
                    failures.append(
                        f"Figure source {name} is bound to both {prior} and {canonical_id}."
                    )
                used_figure_sources[name] = canonical_id
        index[canonical_id] = {
            **entry,
            "asset_id": canonical_id,
            "resolved_source_bindings": resolved_bindings,
            "resolved_crop_bindings": resolved_crop_bindings,
        }

    if document is not None:
        document.close()
    return {
        "ok": not failures,
        "failures": failures,
        "mapping": mapping,
        "assets": index,
        "source_pdf": source_pdf,
        "extraction_manifest": manifest_path,
        "map_path": map_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path)
    args = parser.parse_args(argv)
    result = validate_map(args.map)
    print(json.dumps({
        "ok": result["ok"],
        "map": str(args.map.expanduser().resolve()),
        "assets": sorted(result.get("assets", {})),
        "failures": result["failures"],
    }, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
