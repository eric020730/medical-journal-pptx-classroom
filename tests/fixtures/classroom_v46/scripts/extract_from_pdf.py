#!/usr/bin/env python3
"""Extract text, images, tables, and full-page renders from a journal PDF.

Usage:
    python extract_from_pdf.py <pdf-path> --out <out-dir>
    python extract_from_pdf.py <pdf-path> --out <out-dir> --dedup-threshold 5

Produces:
    <out-dir>/text.md                 — extracted text, one section per heading
    <out-dir>/page_<N>.png            — 200 DPI full-page renders
    <out-dir>/image_<page>_<idx>.png  — embedded raster images
    <out-dir>/figures/Figure_<N>.png  — filtered likely content figures
    <out-dir>/unique/Figure_<N>.png   — deduplicated figure representatives
    <out-dir>/tables/Table_<N>_page_<P>.png — cropped table images
    <out-dir>/manifest.json           — { images, figures, unique_figures, ... }

Why both page renders and embedded images?
- Many journal figures are VECTOR art (PDF drawing commands), not raster
  images. Those won't show up in the embedded-image extraction. To get them,
  you crop a region of the page render.
- Tables in PDFs are usually rendered as text, not images. To capture them,
  crop the page region that contains the table.
- Embedded raster images (via /XObject) give the cleanest grab when available.

The figure/table logic is shared with Eric's personal medical wiki ingestion:
- likely figures are copied from embedded raster images, filtering tiny
  icons/logos;
- tables are located with pdfplumber.find_tables();
- when table detection misses a text/vector table, a caption-based fallback
  crops from the "Table..." label until the first large vertical gap;
- cropped tables are normalized by trimming edge whitespace / outer dark
  frames and adding a stable white margin.
- filtered figures are deduplicated with average-hash (aHash) so repeated
  logos, headers, or duplicate thumbnails do not become repeated figure slides.

Fallback: the model still has access to page renders, then can manually crop
vector figures that are not embedded raster images.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
from pathlib import Path
import re


MIN_FIGURE_SIDE_PX = 200
CROP_QA_EDGE_STRIP_PX = 8
CROP_QA_DARK_THRESHOLD = 245
CROP_QA_EDGE_DENSITY_THRESHOLD = 0.015


def flattened_pixels(image):
    """Use Pillow's current API while remaining compatible with Pillow 10/11."""
    getter = getattr(image, "get_flattened_data", None)
    return list(getter() if getter is not None else image.getdata())


def ahash(path: Path | str, size: int = 8) -> int:
    """Compute an average-hash of an image; returns a 64-bit integer."""
    try:
        from PIL import Image
    except ImportError as e:
        raise SystemExit("Pillow required: pip install Pillow") from e
    img = Image.open(path).convert("L").resize((size, size), Image.BILINEAR)
    pixels = flattened_pixels(img)
    avg = sum(pixels) / len(pixels) if pixels else 0
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel >= avg else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def group_by_similarity(items: list[tuple[str, int]], threshold: int = 5):
    """Greedy aHash grouping. First image in a group is the representative."""
    groups = []
    for key, image_hash in items:
        for group in groups:
            _, representative_hash = group[0]
            if hamming(image_hash, representative_hash) <= threshold:
                group.append((key, image_hash))
                break
        else:
            groups.append([(key, image_hash)])
    return groups


def extract(pdf_path: str, out_dir: str, dpi: int = 200, dedup_threshold: int = 5, table_dpi: int = 600) -> dict:
    try:
        import pymupdf as fitz
    except ImportError as e:
        raise SystemExit(
            "PyMuPDF is required. Install with: pip install pymupdf"
        ) from e

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    figures_dir = out / "figures"
    unique_dir = out / "unique"
    tables_dir = out / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    unique_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Keep repeated runs idempotent. Root-level page/image files are overwritten
    # below; generated content assets should not accumulate stale leftovers.
    for stale in (
        list(figures_dir.glob("*.png"))
        + list(unique_dir.glob("*.png"))
        + list(tables_dir.glob("*.png"))
    ):
        stale.unlink()

    doc = fitz.open(pdf_path)
    manifest = {
        "pdf": str(pdf_path),
        "page_count": len(doc),
        "pages": [],
        "images": [],
        "figures": [],
        "unique_figures": [],
        "duplicates": {},
        "dedup_threshold": dedup_threshold,
        "ignored_images": [],
        "tables": [],
    }

    text_parts = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for i, page in enumerate(doc):
        page_num = i + 1

        # Full page render
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        page_png = out / f"page_{page_num:02d}.png"
        pix.save(str(page_png))

        # Page text
        page_text = page.get_text("text")
        text_parts.append(f"\n\n=== Page {page_num} ===\n\n{page_text}")

        manifest["pages"].append({
            "page": page_num,
            "render": page_png.name,
            "width": pix.width,
            "height": pix.height,
            "text_chars": len(page_text),
        })

        # Embedded images. Preserve the legacy root-level image files, but also
        # create a filtered figures/ set that skips likely icons/logos.
        for idx, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue
            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            name = f"image_p{page_num:02d}_{idx:02d}.{ext}"
            img_path = out / name
            img_path.write_bytes(img_bytes)
            width = base_image.get("width") or 0
            height = base_image.get("height") or 0

            # Try to find the image placement on the page
            rects = [r for r in page.get_image_rects(xref)] if hasattr(page, "get_image_rects") else []
            bbox = None
            if rects:
                r = rects[0]
                bbox = {"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1}

            manifest["images"].append({
                "page": page_num,
                "file": name,
                "ext": ext,
                "width": width,
                "height": height,
                "bbox_pt": bbox,
            })

            if width and height and (width < MIN_FIGURE_SIDE_PX or height < MIN_FIGURE_SIDE_PX):
                manifest["ignored_images"].append({
                    "page": page_num,
                    "file": name,
                    "width": width,
                    "height": height,
                    "reason": f"smaller than {MIN_FIGURE_SIDE_PX} px on one side",
                })
                continue

            figure_index = len(manifest["figures"]) + 1
            figure_name = f"Figure_{figure_index:02d}.png"
            figure_path = figures_dir / figure_name
            figure_method = "embedded_image_filtered"

            # Directly extracted PDF image streams may omit page-level Decode
            # or colorspace transforms. This is common in radiology PDFs and
            # can turn CT panels into inverted negatives. When the image
            # placement bbox is available, render that page region instead;
            # PyMuPDF applies the same transforms a PDF viewer would.
            if bbox:
                bbox, figure_width, figure_height, figure_qa = _save_verified_figure_clip(
                    page, matrix, bbox, figure_path
                )
                figure_method = "page_clip_rendered_from_image_bbox"
            else:
                shutil.copy2(img_path, figure_path)
                figure_width = width
                figure_height = height
                figure_qa = _qa_image_edges(figure_path)
            manifest["figures"].append({
                "page": page_num,
                "file": str(Path("figures") / figure_name),
                "source": name,
                "width": figure_width,
                "height": figure_height,
                "bbox_pt": bbox,
                "method": figure_method,
                "crop_qa": figure_qa,
            })

    deduplicate_figures(out, unique_dir, manifest, dedup_threshold)
    manifest["tables"] = extract_tables(pdf_path, tables_dir, table_dpi=table_dpi)

    (out / "text.md").write_text("".join(text_parts), encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def deduplicate_figures(out_dir: Path, unique_dir: Path, manifest: dict, threshold: int) -> None:
    """Populate manifest unique_figures/duplicates from filtered figure assets."""
    hashable: list[tuple[str, int]] = []
    figure_by_file = {entry["file"]: entry for entry in manifest["figures"]}

    for entry in manifest["figures"]:
        rel = entry["file"]
        try:
            image_hash = ahash(out_dir / rel)
        except Exception:
            image_hash = None
        entry["ahash"] = f"{image_hash:016x}" if image_hash is not None else None
        if image_hash is not None:
            hashable.append((rel, image_hash))

    groups = group_by_similarity(hashable, threshold=threshold)
    represented = set()

    for group in groups:
        representative = group[0][0]
        entry = figure_by_file[representative]
        src = out_dir / representative
        dst = unique_dir / Path(representative).name
        shutil.copy2(src, dst)

        duplicates = [name for name, _ in group[1:]]
        if duplicates:
            manifest["duplicates"][representative] = duplicates

        unique_entry = dict(entry)
        unique_entry["unique_path"] = str(Path("unique") / dst.name)
        unique_entry["duplicate_count"] = len(duplicates)
        manifest["unique_figures"].append(unique_entry)
        represented.update(name for name, _ in group)

    # Safety fallback for images that could not be hashed.
    for entry in manifest["figures"]:
        if entry["file"] in represented:
            continue
        src = out_dir / entry["file"]
        dst = unique_dir / Path(entry["file"]).name
        shutil.copy2(src, dst)
        unique_entry = dict(entry)
        unique_entry["unique_path"] = str(Path("unique") / dst.name)
        unique_entry["duplicate_count"] = 0
        manifest["unique_figures"].append(unique_entry)


def extract_tables(pdf_path: str, tables_dir: Path, table_dpi: int = 600) -> list[dict]:
    """Detect text/vector tables and save cropped normalized PNGs."""
    try:
        import pdfplumber
    except ImportError:
        return []

    tables: list[dict] = []
    table_index = 1

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_table_count = 0
            used_bboxes: list[tuple[float, float, float, float]] = []
            words = page.extract_words(x_tolerance=1, y_tolerance=3) or []

            # Caption-based crops are usually more reliable for journal PDFs:
            # ruled tables are often split into multiple small boxes by
            # pdfplumber, especially when they sit in one column or use shaded
            # rows. Prefer explicit "TABLE N:" headings, then use structural
            # detection only for tables that do not overlap those crops.
            for fallback in _caption_fallback_bboxes(page, words):
                out_path = tables_dir / f"Table_{table_index:02d}_page_{page_index}.png"
                final_bbox, crop_qa = _save_verified_table_crop(page, fallback, out_path, table_dpi=table_dpi)
                tables.append({
                    "file": str(Path("tables") / out_path.name),
                    "page": page_index,
                    "bbox": [round(v, 1) for v in final_bbox],
                    "original_bbox": [round(v, 1) for v in fallback],
                    "method": "caption_fallback_crop",
                    "crop_qa": crop_qa,
                })
                used_bboxes.append(final_bbox)
                table_index += 1
                page_table_count += 1

            try:
                detected_tables = page.find_tables()
            except Exception:
                detected_tables = []

            for table in detected_tables:
                x0, top, x1, bottom = table.bbox

                has_table_caption = any(
                    w.get("text", "").lower().startswith("table")
                    and (x0 - 25) <= w.get("x0", 0) <= (x1 + 25)
                    and (top - 45) <= w.get("top", page.height) <= (top + 20)
                    for w in words
                )

                structured_table = False
                try:
                    rows = table.extract() or []
                    row_count = len(rows)
                    col_count = max((len(row) for row in rows if row), default=0)
                    page_area = page.width * page.height
                    table_area = (x1 - x0) * (bottom - top)
                    cell_text = " ".join(
                        str(cell or "")
                        for row in rows
                        for cell in (row or [])
                    )
                    alpha_count = sum(1 for ch in cell_text if ch.isalpha())
                    structured_table = (
                        row_count >= 2
                        and col_count >= 2
                        and 0.03 <= (table_area / page_area) <= 0.45
                        and alpha_count >= 80
                    )
                except Exception:
                    structured_table = False

                if not has_table_caption and not structured_table:
                    continue

                padded = _pad_table_bbox(page, words, x0, top, x1, bottom)
                if not padded:
                    continue
                if any(_bbox_overlap_ratio(padded, used) > 0.10 for used in used_bboxes):
                    continue

                out_path = tables_dir / f"Table_{table_index:02d}_page_{page_index}.png"
                final_bbox, crop_qa = _save_verified_table_crop(page, padded, out_path, table_dpi=table_dpi)
                tables.append({
                    "file": str(Path("tables") / out_path.name),
                    "page": page_index,
                    "bbox": [round(v, 1) for v in final_bbox],
                    "original_bbox": [round(v, 1) for v in padded],
                    "method": "pdfplumber.find_tables",
                    "crop_qa": crop_qa,
                })
                used_bboxes.append(final_bbox)
                table_index += 1
                page_table_count += 1

    return tables


def _pad_table_bbox(page, words: list[dict], x0: float, top: float, x1: float, bottom: float):
    pad = 8
    original_top = top
    detected_x0 = x0
    detected_x1 = x1
    x0 = max(0, x0 - pad)
    title_words = [
        w for w in words
        if (original_top - 45) <= w.get("top", page.height) < original_top
        and (x0 - 15) <= w.get("x0", 0) <= (x1 + 15)
    ]
    if title_words:
        top = min(w["top"] for w in title_words)
    top = max(0, top - pad)
    row_words = [
        w for w in words
        if (top - 8) <= w.get("top", page.height) <= (bottom + 8)
        and w.get("x0", 0) > 20
        and (w.get("x1", 0) - w.get("x0", 0)) > 2
    ]
    if row_words:
        x0 = min(x0, max(0, min(w["x0"] for w in row_words) - pad))
        x1 = max(x1, min(page.width, max(w["x1"] for w in row_words) + pad))
    x1 = min(page.width, x1 + pad)
    footnote_words = [
        w for w in words
        if bottom < w.get("top", 0) < bottom + 55
        and x0 <= w.get("x0", 0) <= x1
    ]
    if footnote_words:
        footnote_lines: list[dict] = []
        for word in sorted(footnote_words, key=lambda w: (w["top"], w["x0"])):
            for line in footnote_lines:
                if abs(line["top"] - word["top"]) < 3:
                    line["words"].append(word)
                    line["top"] = min(line["top"], word["top"])
                    line["bottom"] = max(line["bottom"], word["bottom"])
                    break
            else:
                footnote_lines.append({"top": word["top"], "bottom": word["bottom"], "words": [word]})
        included_bottoms = []
        for line in footnote_lines:
            line_text = " ".join(w.get("text", "") for w in sorted(line["words"], key=lambda w: w["x0"]))
            if re.match(r"^([a-z]\b|note\b)", line_text, re.IGNORECASE):
                included_bottoms.append(line["bottom"])
        if included_bottoms:
            bottom = max(bottom, max(included_bottoms))
    bottom = min(page.height, bottom + pad)
    if (x1 - x0) < 150 or (bottom - top) < 80:
        return None
    return (x0, top, x1, bottom)


def _caption_fallback_bbox(page, words: list[dict]):
    bboxes = _caption_fallback_bboxes(page, words)
    return bboxes[0] if bboxes else None


def _caption_fallback_bboxes(page, words: list[dict]) -> list[tuple[float, float, float, float]]:
    all_lines: list[dict] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for line in all_lines:
            if abs(line["top"] - word["top"]) < 3:
                line["words"].append(word)
                line["top"] = min(line["top"], word["top"])
                line["bottom"] = max(line["bottom"], word["bottom"])
                break
        else:
            all_lines.append({
                "top": word["top"],
                "bottom": word["bottom"],
                "words": [word],
            })

    caption_tops = []
    for line in all_lines:
        line_text = " ".join(w.get("text", "") for w in sorted(line["words"], key=lambda w: w["x0"]))
        if re.match(r"^(?:[A-Z]{1,3}\s+)?table\s*\d+\b", line_text, re.IGNORECASE):
            caption_tops.append(round(line["top"], 1))
    caption_tops = sorted(set(caption_tops))
    if not caption_tops:
        return []
    bboxes: list[tuple[float, float, float, float]] = []

    for idx, caption_top in enumerate(caption_tops):
        next_caption_top = caption_tops[idx + 1] if idx + 1 < len(caption_tops) else page.height - 55
        table_rects = []
        for rect in getattr(page, "rects", []) or []:
            rect_top = rect.get("top", rect.get("y0", 0))
            rect_bottom = rect.get("bottom", rect.get("y1", rect_top))
            rect_width = rect.get("x1", 0) - rect.get("x0", 0)
            rect_height = rect_bottom - rect_top
            if (
                caption_top <= rect_top < next_caption_top
                and rect_width > 20
                and rect_height > 8
            ):
                table_rects.append(rect)
        rect_x0 = min((r["x0"] for r in table_rects), default=None)
        rect_x1 = max((r["x1"] for r in table_rects), default=None)
        rect_bottom = max((r.get("bottom", r.get("y1", 0)) for r in table_rects), default=None)

        candidate_words = [
            w for w in words
            if w["top"] >= caption_top
            and w["top"] < next_caption_top - 4
            and w["bottom"] < page.height - 55
            and (
                rect_x0 is None
                or (rect_x0 - 12) <= w.get("x0", 0) <= (rect_x1 + 12)
                or (rect_x0 - 12) <= w.get("x1", 0) <= (rect_x1 + 12)
            )
        ]

        lines: list[dict] = []
        for word in sorted(candidate_words, key=lambda w: (w["top"], w["x0"])):
            for line in lines:
                if abs(line["top"] - word["top"]) < 3:
                    line["words"].append(word)
                    line["top"] = min(line["top"], word["top"])
                    line["bottom"] = max(line["bottom"], word["bottom"])
                    break
            else:
                lines.append({
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "words": [word],
                })

        table_lines = []
        previous = None
        for line in sorted(lines, key=lambda l: l["top"]):
            if previous:
                gap = line["top"] - previous["bottom"]
                if gap > 18 and previous["top"] > caption_top + 45:
                    break
            table_lines.append(line)
            previous = line

        body_words = [word for line in table_lines for word in line["words"]]
        body_words = [
            word for word in body_words
            if word.get("x0", 0) > 20
            and (word.get("x1", 0) - word.get("x0", 0)) > 2
        ]
        if not body_words:
            continue

        x0 = max(0, min(w["x0"] for w in body_words) - 8)
        top = max(0, caption_top - 8)
        x1 = min(page.width, max(w["x1"] for w in body_words) + 8)
        bottom = min(page.height, max(w["bottom"] for w in body_words) + 8)
        if rect_x0 is not None and rect_x1 is not None:
            x0 = max(0, min(x0, rect_x0 - 8))
            x1 = min(page.width, max(x1, rect_x1 + 8))
        if rect_bottom is not None:
            bottom = max(bottom, min(page.height, rect_bottom + 8))
        horizontal_rules = []
        for edge in getattr(page, "lines", []) or []:
            edge_top = edge.get("top", edge.get("y0", 0))
            edge_bottom = edge.get("bottom", edge.get("y1", edge_top))
            edge_width = edge.get("x1", 0) - edge.get("x0", 0)
            if abs(edge_bottom - edge_top) < 2 and edge_width > page.width * 0.4:
                y = min(edge_top, edge_bottom)
                if caption_top + 25 < y < next_caption_top:
                    horizontal_rules.append(y)
        if horizontal_rules:
            bottom = min(bottom, max(horizontal_rules) + 8)
        note_words = [
            w for w in words
            if bottom - 10 < w.get("top", 0) < bottom + 45
            and x0 <= w.get("x0", 0) <= x1
        ]
        note_lines: list[dict] = []
        for word in sorted(note_words, key=lambda w: (w["top"], w["x0"])):
            for line in note_lines:
                if abs(line["top"] - word["top"]) < 3:
                    line["words"].append(word)
                    line["top"] = min(line["top"], word["top"])
                    line["bottom"] = max(line["bottom"], word["bottom"])
                    break
            else:
                note_lines.append({"top": word["top"], "bottom": word["bottom"], "words": [word]})
        for line in note_lines:
            line_text = " ".join(w.get("text", "") for w in sorted(line["words"], key=lambda w: w["x0"]))
            if re.match(r"^note\b", line_text, re.IGNORECASE):
                bottom = max(bottom, line["bottom"] + 8)

        if (x1 - x0) < 150 or (bottom - top) < 80:
            continue
        bboxes.append((x0, top, x1, bottom))
    return bboxes


def _bbox_overlap_ratio(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    return intersection / area


def _save_verified_table_crop(
    page,
    bbox: tuple[float, float, float, float],
    out_path: Path,
    max_attempts: int = 3,
    table_dpi: int = 600,
) -> tuple[tuple[float, float, float, float], dict]:
    """Save a table crop, expanding tight edges before final normalization."""
    current = bbox
    last_qa: dict | None = None
    for attempt in range(1, max_attempts + 1):
        _save_table_crop(page, current, out_path, normalize=False, table_dpi=table_dpi)
        qa = _qa_image_edges(out_path)
        qa["attempt"] = attempt
        last_qa = qa
        if qa["status"] == "pass" or attempt == max_attempts:
            break
        current = _expand_bbox(page, current, x_pad=18, y_pad=12)

    border_cleanup = safe_normalize_crop(
        out_path,
        asset_type="table",
        allow_outer_border_removal=True,
    )
    final_qa = _qa_image_edges(out_path)
    final_qa["border_cleanup"] = border_cleanup
    final_qa["attempts"] = last_qa.get("attempt", 1) if last_qa else 1
    final_qa["pre_normalize_status"] = last_qa.get("status") if last_qa else "unknown"
    final_qa["pre_normalize_issues"] = last_qa.get("issues", []) if last_qa else []
    final_qa["auto_expanded"] = final_qa["attempts"] > 1
    if final_qa["pre_normalize_status"] == "warning" or border_cleanup.get("manual_review_required"):
        final_qa["status"] = "warning"
    return current, final_qa


def _save_table_crop(
    page,
    bbox: tuple[float, float, float, float],
    out_path: Path,
    normalize: bool = True,
    table_dpi: int = 600,
) -> None:
    cropped = page.crop(bbox)
    image = cropped.to_image(resolution=table_dpi)
    image.save(str(out_path), format="PNG")
    if normalize:
        safe_normalize_crop(out_path, asset_type="table", allow_outer_border_removal=True)


def _save_verified_figure_clip(page, matrix, bbox: dict, out_path: Path, max_attempts: int = 2):
    try:
        import pymupdf as fitz
    except ImportError as e:
        raise SystemExit("PyMuPDF is required. Install with: pip install pymupdf") from e

    current = (bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
    last_qa: dict | None = None
    pix = None
    for attempt in range(1, max_attempts + 1):
        clip = fitz.Rect(*current)
        pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        pix.save(str(out_path))
        qa = _qa_image_edges(out_path)
        qa["attempt"] = attempt
        last_qa = qa
        if qa["status"] == "pass" or attempt == max_attempts:
            break
        current = _expand_bbox(page, current, x_pad=8, y_pad=6)

    final_bbox = {"x0": current[0], "y0": current[1], "x1": current[2], "y1": current[3]}
    crop_qa = last_qa or {"status": "unknown", "issues": ["qa_failed"]}
    crop_qa["attempts"] = crop_qa.get("attempt", 1)
    crop_qa["auto_expanded"] = crop_qa["attempts"] > 1
    return final_bbox, pix.width if pix else 0, pix.height if pix else 0, crop_qa


def _expand_bbox(page, bbox: tuple[float, float, float, float], x_pad: float, y_pad: float):
    x0, top, x1, bottom = bbox
    page_width, page_height = _page_size(page)
    return (
        max(0, x0 - x_pad),
        max(0, top - y_pad),
        min(page_width, x1 + x_pad),
        min(page_height, bottom + y_pad),
    )


def _page_size(page) -> tuple[float, float]:
    if hasattr(page, "width") and hasattr(page, "height"):
        return page.width, page.height
    if hasattr(page, "rect"):
        return page.rect.width, page.rect.height
    raise AttributeError("page object does not expose width/height")


def _qa_image_edges(image_path: Path) -> dict:
    """Flag crops whose non-white content is still touching an image edge."""
    try:
        from PIL import Image
    except ImportError:
        return {"status": "unknown", "issues": ["pillow_missing"]}

    img = Image.open(image_path).convert("L")
    width, height = img.size
    if width == 0 or height == 0:
        return {"status": "warning", "issues": ["empty_image"]}

    strip = min(CROP_QA_EDGE_STRIP_PX, max(1, width // 8), max(1, height // 8))
    regions = {
        "left_edge_content": (0, 0, strip, height),
        "right_edge_content": (width - strip, 0, width, height),
        "top_edge_content": (0, 0, width, strip),
        "bottom_edge_content": (0, height - strip, width, height),
    }

    densities = {}
    issues = []
    for issue, box in regions.items():
        crop = img.crop(box)
        pixels = flattened_pixels(crop)
        density = sum(1 for value in pixels if value < CROP_QA_DARK_THRESHOLD) / max(1, len(pixels))
        densities[issue] = round(density, 4)
        if density >= CROP_QA_EDGE_DENSITY_THRESHOLD:
            issues.append(issue)

    return {
        "status": "warning" if issues else "pass",
        "issues": issues,
        "edge_dark_pixel_density": densities,
    }


def classify_crop_asset(label: str | None, method: str | None, caption: str | None = None) -> str:
    """Classify crop type for conservative post-processing decisions."""
    text = " ".join(part or "" for part in (label, method, caption)).lower()
    if "table" in text:
        return "table"
    if "flowchart" in text or "flow chart" in text or "study population" in text:
        return "flowchart"
    if "figure" in text or "fig" in text:
        return "figure"
    return "unknown"


def normalize_table_image(image_path: Path, margin: int = 24) -> None:
    """Backward-compatible table normalizer."""
    safe_normalize_crop(image_path, margin=margin, asset_type="table", allow_outer_border_removal=True)


def safe_normalize_crop(
    image_path: Path,
    margin: int = 24,
    asset_type: str = "unknown",
    allow_outer_border_removal: bool = False,
) -> dict:
    """Trim whitespace and only remove decorative outer frames when safe."""
    try:
        from PIL import Image
    except ImportError:
        return {
            "status": "skipped",
            "asset_type": asset_type,
            "action": "none",
            "reason": "pillow_missing",
            "manual_review_required": True,
        }

    img = Image.open(image_path).convert("RGB")
    gray = img.convert("L")
    width, height = gray.size
    cleanup = {
        "status": "skipped",
        "asset_type": asset_type,
        "action": "pad_only",
        "reason": "whitespace_trim_only",
        "manual_review_required": False,
        "before_size": [width, height],
        "after_size": [width, height],
    }
    pixels = gray.load()

    xs = []
    ys = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] < 245:
                xs.append(x)
                ys.append(y)

    if not xs or not ys:
        cleanup["reason"] = "blank_image"
        return cleanup

    crop_box = (
        max(0, min(xs) - 2),
        max(0, min(ys) - 2),
        min(width, max(xs) + 3),
        min(height, max(ys) + 3),
    )
    cropped = img.crop(crop_box)
    pre_border_size = [cropped.width, cropped.height]

    gray_crop = cropped.convert("L")
    left = 0
    top = 0
    right = cropped.width
    bottom = cropped.height

    def dark_row_ratio(y: int) -> float:
        row = [gray_crop.getpixel((x, y)) for x in range(left, right)]
        return sum(1 for value in row if value < 80) / max(1, len(row))

    def dark_col_ratio(x: int) -> float:
        col = [gray_crop.getpixel((x, y)) for y in range(top, bottom)]
        return sum(1 for value in col if value < 80) / max(1, len(col))

    def row_band_dark_ratio(y0: int, y1: int) -> float:
        values = [
            gray_crop.getpixel((x, y))
            for y in range(max(0, y0), min(cropped.height, y1))
            for x in range(left, right)
        ]
        return sum(1 for value in values if value < 120) / max(1, len(values))

    def col_band_dark_ratio(x0: int, x1: int) -> float:
        values = [
            gray_crop.getpixel((x, y))
            for x in range(max(0, x0), min(cropped.width, x1))
            for y in range(top, bottom)
        ]
        return sum(1 for value in values if value < 120) / max(1, len(values))

    def safe_outer_line(side: str) -> bool:
        # Require a dark edge line plus a mostly quiet band just inside it.
        # This avoids eating text, arrows, panel letters, axes, or flowchart boxes.
        if side == "top":
            return dark_row_ratio(top) > 0.65 and row_band_dark_ratio(top + 3, top + 14) < 0.04
        if side == "bottom":
            return dark_row_ratio(bottom - 1) > 0.65 and row_band_dark_ratio(bottom - 14, bottom - 3) < 0.04
        if side == "left":
            return dark_col_ratio(left) > 0.65 and col_band_dark_ratio(left + 3, left + 14) < 0.04
        if side == "right":
            return dark_col_ratio(right - 1) > 0.65 and col_band_dark_ratio(right - 14, right - 3) < 0.04
        return False

    can_remove_border = allow_outer_border_removal and asset_type in {"table", "flowchart"}
    if can_remove_border:
        removed = {"top": 0, "bottom": 0, "left": 0, "right": 0}
        max_remove = 20 if asset_type == "table" else 8
        while top < bottom - 1 and removed["top"] < max_remove and safe_outer_line("top"):
            top += 1
            removed["top"] += 1
        while bottom > top + 1 and removed["bottom"] < max_remove and safe_outer_line("bottom"):
            bottom -= 1
            removed["bottom"] += 1
        while left < right - 1 and removed["left"] < max_remove and safe_outer_line("left"):
            left += 1
            removed["left"] += 1
        while right > left + 1 and removed["right"] < max_remove and safe_outer_line("right"):
            right -= 1
            removed["right"] += 1

        if any(removed.values()):
            cleanup["status"] = "applied"
            cleanup["action"] = "remove_outer_frame"
            cleanup["reason"] = f"safe_{asset_type}_outer_frame"
            cleanup["removed_px"] = removed
    else:
        cleanup["reason"] = f"{asset_type}_border_removal_skipped"

    if left or top or right != cropped.width or bottom != cropped.height:
        cropped = cropped.crop((left, top, right, bottom))

    canvas = Image.new("RGB", (cropped.width + margin * 2, cropped.height + margin * 2), "white")
    canvas.paste(cropped, (margin, margin))
    canvas.save(image_path)
    cleanup["after_size"] = [canvas.width, canvas.height]
    cleanup["content_before_border_size"] = pre_border_size
    cleanup["content_after_border_size"] = [cropped.width, cropped.height]
    shrink_w = 1 - (cropped.width / max(1, pre_border_size[0]))
    shrink_h = 1 - (cropped.height / max(1, pre_border_size[1]))
    if shrink_w > 0.08 or shrink_h > 0.08:
        cleanup["status"] = "warning"
        cleanup["manual_review_required"] = True
        cleanup["reason"] += "_large_size_change"
    return cleanup


def crop_region(page_png: str, out_path: str, x0: float, y0: float, x1: float, y1: float):
    """Crop a region from a page render. Coordinates in pixels."""
    try:
        from PIL import Image
    except ImportError as e:
        raise SystemExit("Pillow required: pip install Pillow") from e
    img = Image.open(page_png)
    img.crop((x0, y0, x1, y1)).save(out_path)


def build_crop_review_artifacts(
    out_dir: str | Path,
    manifest: dict,
    cols: int = 4,
    thumb_width: int = 360,
) -> dict:
    """Create a contact sheet and markdown review summary for extracted crops."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {
            "status": "skipped",
            "reason": "Pillow missing",
            "contact_sheet": None,
            "crop_review": None,
        }

    out = Path(out_dir)
    candidates = []
    for kind, entries in (("figure", manifest.get("figures", [])), ("table", manifest.get("tables", []))):
        for entry in entries:
            rel = entry.get("file")
            if not rel:
                continue
            path = out / rel
            if not path.exists():
                continue
            qa = entry.get("crop_qa", {}) or {}
            candidates.append({
                "kind": kind,
                "path": path,
                "rel": rel,
                "page": entry.get("page"),
                "method": entry.get("method", "unknown"),
                "status": qa.get("status", "unknown"),
                "issues": qa.get("issues") or qa.get("pre_normalize_issues") or [],
                "auto_expanded": bool(qa.get("auto_expanded")),
                "border_cleanup": qa.get("border_cleanup") or {},
            })

    warning_count = sum(1 for item in candidates if item["status"] == "warning")
    auto_expanded_count = sum(1 for item in candidates if item["auto_expanded"])

    contact_sheet = out / "contact_sheet.png"
    if candidates:
        cols = max(1, cols)
        label_height = 58
        pad = 16
        cell_w = thumb_width + pad * 2
        cell_h = int(thumb_width * 0.78) + label_height + pad * 2
        rows = (len(candidates) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("Arial.ttf", 14)
        except Exception:
            font = ImageFont.load_default()

        for idx, item in enumerate(candidates):
            row, col = divmod(idx, cols)
            x = col * cell_w + pad
            y = row * cell_h + pad
            img = Image.open(item["path"]).convert("RGB")
            img.thumbnail((thumb_width, int(thumb_width * 0.78)))
            bg = "#fff3cd" if item["status"] == "warning" else "#f8f9fa"
            draw.rectangle(
                [col * cell_w + 4, row * cell_h + 4, (col + 1) * cell_w - 4, (row + 1) * cell_h - 4],
                fill=bg,
                outline="#cc0000" if item["status"] == "warning" else "#bbbbbb",
                width=3 if item["status"] == "warning" else 1,
            )
            sheet.paste(img, (x + (thumb_width - img.width) // 2, y))
            label_y = row * cell_h + pad + int(thumb_width * 0.78) + 8
            label = f"{idx + 1}. {item['kind']} p{item['page']} {Path(item['rel']).name}"
            status = f"QA: {item['status']} | {item['method']}"
            if item["auto_expanded"]:
                status += " | auto-expanded"
            border = item.get("border_cleanup") or {}
            if border:
                status += f" | border: {border.get('action', 'none')}"
                if border.get("manual_review_required"):
                    status += " | review"
            draw.text((x, label_y), label[:64], fill="#111111", font=font)
            draw.text(
                (x, label_y + 20),
                status[:72],
                fill="#cc0000" if item["status"] == "warning" else "#333333",
                font=font,
            )
        sheet.save(contact_sheet)
    else:
        contact_sheet = None

    review_path = out / "crop_review.md"
    lines = [
        "# Crop Review",
        "",
        f"Candidates: {len(candidates)}",
        f"Warnings: {warning_count}",
        f"Auto-expanded crops: {auto_expanded_count}",
        f"Ignored small images: {len(manifest.get('ignored_images', []))}",
        f"Duplicate groups: {len(manifest.get('duplicate_groups', []))}",
        "",
        "## Required Manual Checks",
        "",
        "- Confirm every paper Figure/Table number appears in the final asset list.",
        "- Confirm multi-panel figures are complete and not split incorrectly.",
        "- Confirm table first/last columns, footnotes, abbreviations, and captions are present.",
        "- Confirm automatic border cleanup did not remove content, labels, axes, or semantic boxes.",
        "- Confirm crops do not include unrelated body text, page numbers, watermarks, or running footers.",
        "- Re-crop from full-page renders when any warning or visual mismatch remains.",
        "",
        "## Warning Crops",
        "",
    ]
    warnings = [item for item in candidates if item["status"] == "warning"]
    if warnings:
        for item in warnings:
            issue_text = ", ".join(item["issues"]) if item["issues"] else "unspecified"
            lines.append(f"- `{item['rel']}` page {item['page']}: {issue_text}")
    else:
        lines.append("- None")

    lines.extend(["", "## Border Cleanup Review", ""])
    border_items = [item for item in candidates if item.get("border_cleanup")]
    if border_items:
        for item in border_items:
            border = item["border_cleanup"]
            review = " review" if border.get("manual_review_required") else ""
            lines.append(
                f"- `{item['rel']}` page {item['page']}: "
                f"{border.get('status', 'unknown')} / {border.get('action', 'none')}"
                f" ({border.get('asset_type', 'unknown')}){review} — "
                f"{border.get('reason', '')}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Ignored Small Images", ""])
    ignored = manifest.get("ignored_images", [])
    if ignored:
        for item in ignored:
            lines.append(
                f"- page {item.get('page')}: `{item.get('file')}` "
                f"{item.get('width')}x{item.get('height')} — {item.get('reason')}"
            )
    else:
        lines.append("- None")

    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "status": "created",
        "contact_sheet": contact_sheet.name if contact_sheet else None,
        "crop_review": review_path.name,
        "candidate_count": len(candidates),
        "warning_count": warning_count,
        "auto_expanded_count": auto_expanded_count,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Path to the source PDF")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--dpi", type=int, default=200, help="Page render DPI (default 200)")
    ap.add_argument("--table-dpi", type=int, default=600, help="Table crop render DPI (default 600; tables are dense text and need more than photo figures)")
    ap.add_argument(
        "--no-contact-sheet",
        action="store_true",
        help="Skip contact_sheet.png and crop_review.md generation",
    )
    ap.add_argument(
        "--contact-sheet-cols",
        type=int,
        default=4,
        help="Number of columns in contact_sheet.png (default 4)",
    )
    ap.add_argument(
        "--dedup-threshold",
        type=int,
        default=5,
        help="aHash Hamming threshold for grouping duplicate figures (default 5)",
    )
    args = ap.parse_args()

    manifest = extract(args.pdf, args.out, dpi=args.dpi, dedup_threshold=args.dedup_threshold, table_dpi=args.table_dpi)
    if not args.no_contact_sheet:
        crop_review = build_crop_review_artifacts(
            args.out,
            manifest,
            cols=args.contact_sheet_cols,
        )
        manifest["crop_review"] = crop_review
        Path(args.out, "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"Extracted {manifest['page_count']} pages, "
          f"{len(manifest['images'])} embedded images → {args.out}")
    print(f"Filtered figures: {len(manifest['figures'])}; "
          f"unique figures: {len(manifest['unique_figures'])}; "
          f"ignored small images: {len(manifest['ignored_images'])}; "
          f"cropped tables: {len(manifest['tables'])}")
    crop_warnings = sum(
        1
        for entry in manifest["figures"] + manifest["tables"]
        if entry.get("crop_qa", {}).get("status") == "warning"
    )
    auto_expanded = sum(
        1
        for entry in manifest["figures"] + manifest["tables"]
        if entry.get("crop_qa", {}).get("auto_expanded")
    )
    print(f"Crop QA: {crop_warnings} warnings; {auto_expanded} auto-expanded crops")
    if manifest.get("crop_review"):
        review = manifest["crop_review"]
        print(f"Contact sheet: {os.path.join(args.out, review.get('contact_sheet') or '')}")
        print(f"Crop review: {os.path.join(args.out, review.get('crop_review') or '')}")
    print(f"Manifest: {os.path.join(args.out, 'manifest.json')}")


if __name__ == "__main__":
    main()
