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
            caption_pattern = re.compile(
                rf"^{kind}\s*{re.escape(number)}(?:\s*[.:\u2013\u2014-]|\b)", re.IGNORECASE
            )
            if caption_pattern.search(actual_caption) is None:
                failures.append(
                    f"{prefix} caption does not begin with {kind.title()} {number}."
                )

        bindings = entry.get("source_bindings")
        if not isinstance(bindings, list) or not bindings:
            failures.append(f"{prefix} requires source_bindings.")
            bindings = []
        resolved_bindings: list[Path] = []
        bound_names: list[str] = []
        for binding_index, binding in enumerate(bindings, start=1):
            if not isinstance(binding, dict):
                failures.append(f"{prefix} source binding {binding_index} must be an object.")
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
        if method in deterministic_methods:
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
