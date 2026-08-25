#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recompose_panels_banded.py — lay out multi-panel figure crops into one image
with a reserved BACKGROUND BAND below each row, and emit per-panel label-anchor
geometry. The band leaves room so that A/B/C/D can be stamped LATER as native
slide text (see add_panel_labels.py) at a fixed point size — giving every label
the SAME actual size on screen regardless of how each figure is scaled, plus
precise control of the gap above (to its own panel) and below (to the next row).

This script never paints, masks, inpaints, or burns labels into medical image
pixels. Source labels embedded in image content remain intact; separate labels
in a verified exterior margin can be cropped safely before native slide labels
are added.

Usage
-----
  python recompose_panels_banded.py OUT.png \
      --inputs A.png B.png C.png D.png --labels A,B,C,D \
      --geometry geometry.json \
      --gap-above-in 0.06 --gap-below-in 0.12 --label-pt 18

Key options
-----------
  --inputs            panel image files in reading order (pre-cropped)
  --cols              optional manual column count; by default compare every
                      valid grid and maximize the smallest displayed panel
  --labels            comma-separated labels in reading order (e.g. A,B,C,D)
  --geometry          JSON file to write/update; keyed by OUT basename
  --gap-above-in      on-screen gap from a label's TOP to its own panel bottom
  --gap-below-in      on-screen gap from a label's BOTTOM to the next row's panel top
  --label-pt          label font size in points (must match add_panel_labels.py)
  --glyph-ratio       cap-glyph-height / em (renderer dependent; default 0.62 ~
                      LibreOffice/PowerPoint Calibri/Carlito at 18pt -> 0.155 in)
  --center-offset-in  box-center -> needed label-box center placement fudge so the
                      glyph TOP lands exactly gap-above below the panel. Calibrated
                      default 0.0525 in for 18pt. Re-calibrate with
                      measure_label_gaps.py if you change font/size/renderer.
  --slide-box-w-in / --slide-box-h-in   the deck's figure image box (default the
                      bundled medical-journal builder's 12.10 x 4.85 in)
  --bg                band / gutter color, match the slide background (#061428)
  --gap               inter-panel gutter in px (default 16)
  --source-label-policy  auto, preserve, or crop-safe-margin
  --max-edge-px       maximum removable white/gray rim depth per side (default 4)
  --max-boundary-shift-px  maximum source-row seam adjustment for a split
                      embedded label frame (default 24)
  --no-trim           skip bounded white/gray edge cleanup of each panel

Notes
-----
* The band height is held constant in ON-SCREEN inches across every figure by
  solving against each figure's fit-scale into the slide image box. Because the
  label is later drawn at a fixed point size, both the label size and the two
  gaps come out identical on every figure/slide.
* Pair this with add_panel_labels.py AFTER you build the .pptx.
"""
import argparse, json, os
from pathlib import Path

import numpy as np
from PIL import Image


def source_metadata(path):
    """Read optional panel annotations without weakening source-sidecar QA."""
    sidecar = Path(str(path) + ".postprocess.json")
    if not sidecar.is_file():
        return {}
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def label_details(metadata):
    """Accept either structured or flat placement data from any paper extractor."""
    nested = metadata.get("source_panel_label")
    nested = nested if isinstance(nested, dict) else {}
    placement = str(
        nested.get("placement")
        or metadata.get("source_label_placement")
        or metadata.get("label_placement")
        or ("embedded" if metadata.get("embedded_label") else "")
    ).strip().lower().replace("_", "-")
    if metadata.get("source_label_policy") == "preserve":
        placement = "embedded"
    box = (
        nested.get("box_px")
        or nested.get("bbox")
        or metadata.get("source_label_box_px")
        or metadata.get("label_box_px")
    )
    return placement, box


def overwritten_source_pixels(image, metadata):
    """Catch solid corner masks when a panel claims to be an exact source crop."""
    source = metadata.get("source")
    box = metadata.get("crop_box_px")
    if not isinstance(source, str) or not isinstance(box, (list, tuple)) or len(box) != 4:
        return 0
    try:
        original = Image.open(source).convert("RGB").crop(tuple(int(value) for value in box))
    except (OSError, TypeError, ValueError):
        return 0
    if original.size != image.size:
        return 0

    expected = np.asarray(original)
    actual = np.asarray(image.convert("RGB"))
    changed = np.any(expected != actual, axis=2)
    positions = np.argwhere(changed)
    if not len(positions):
        return 0
    y0, x0 = positions.min(axis=0)
    y1, x1 = positions.max(axis=0) + 1
    height, width = changed.shape
    region_width, region_height = int(x1 - x0), int(y1 - y0)
    if region_width < 8 or region_height < 8:
        return 0
    if region_width > width * 0.40 or region_height > height * 0.40:
        return 0
    if not ((x0 == 0 or x1 == width) and (y0 == 0 or y1 == height)):
        return 0

    difference_density = float(np.mean(changed[y0:y1, x0:x1]))
    region = actual[y0:y1, x0:x1].reshape((-1, 3))
    _, counts = np.unique(region, axis=0, return_counts=True)
    solid_fraction = float(counts.max() / len(region))
    if difference_density >= 0.80 and solid_fraction >= 0.98:
        return int(np.count_nonzero(changed[y0:y1, x0:x1]))
    return 0


def edge_line(array, side, depth):
    if side == "top":
        return array[depth, :, :]
    if side == "bottom":
        return array[-depth - 1, :, :]
    if side == "left":
        return array[:, depth, :]
    return array[:, -depth - 1, :]


def is_disposable_rim(line):
    """Classify an achromatic near-white/gray seam, never a colorful scale bar."""
    values = line.astype(np.int16)
    luminance = values.mean(axis=1)
    saturation = values.max(axis=1) - values.min(axis=1)
    if float(np.mean(saturation > 24)) > 0.20:
        return False

    near_white = float(np.mean(values.min(axis=1) >= 210))
    buckets = (values // 24).astype(np.uint8)
    colors, counts = np.unique(buckets, axis=0, return_counts=True)
    winner = int(np.argmax(counts))
    dominant_fraction = float(counts[winner] / len(values))
    dominant_luminance = float(np.mean(colors[winner].astype(np.float64) * 24 + 12))

    if near_white >= 0.70:
        return True
    if dominant_fraction >= 0.50 and dominant_luminance >= 30:
        return True
    return float(luminance.std()) <= 32 and float(luminance.mean()) >= 70


def clean_panel_edges(image, max_edge_px=4):
    """Remove only proven thin achromatic seams, never more than the hard cap."""
    if not 0 <= max_edge_px <= 12:
        raise ValueError("max_edge_px must be between 0 and 12")
    pixels = np.asarray(image.convert("RGB"))
    height, width = pixels.shape[:2]
    trim_px = {side: 0 for side in ("top", "bottom", "left", "right")}
    if not max_edge_px or min(height, width) < max_edge_px + 2:
        return image, trim_px

    for side in trim_px:
        depth_limit = min(max_edge_px, (height if side in ("top", "bottom") else width) - 2)
        removable = 0
        while removable <= depth_limit and is_disposable_rim(edge_line(pixels, side, removable)):
            removable += 1

        # A bright/gray region extending beyond the inspection budget could be
        # real anatomy or a legitimate light image background. Leave it intact.
        if removable <= depth_limit:
            trim_px[side] = removable

    if trim_px["left"] + trim_px["right"] >= width:
        trim_px["left"] = trim_px["right"] = 0
    if trim_px["top"] + trim_px["bottom"] >= height:
        trim_px["top"] = trim_px["bottom"] = 0
    return image.crop((
        trim_px["left"],
        trim_px["top"],
        width - trim_px["right"],
        height - trim_px["bottom"],
    )), trim_px


def _bright_runs(line):
    """Yield contiguous achromatic frame strokes without requiring OpenCV."""
    transitions = np.diff(np.r_[False, line, False].astype(np.int8))
    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)
    return zip(starts.tolist(), ends.tolist())


def boxed_label_bottom(source_pixels, crop_box, boundary, max_shift_px):
    """Find a real rectangular corner label that straddles a rough row seam.

    Anatomy alone is not enough: a candidate needs long parallel top/bottom
    strokes and two vertical strokes, unless the outer stroke is genuinely
    clipped by the source image edge. This conservative shape check prevents
    arrows, bone edges, scale bars, and isolated letters from moving a seam.
    """
    x0, y0, x1, _ = crop_box
    width = x1 - x0
    if width < 45 or max_shift_px <= 0:
        return None

    inspect_width = min(width, max(96, min(192, int(round(width * 0.34)))))
    regions = [(x0, x0 + inspect_width, "left")]
    if inspect_width * 2 < width:
        regions.append((x1 - inspect_width, x1, "right"))
    y_start = max(y0 + 20, boundary - max_shift_px)
    y_stop = min(source_pixels.shape[0], boundary + max_shift_px)
    candidates = []

    for rx0, rx1, corner in regions:
        region = source_pixels[:, rx0:rx1, :].astype(np.int16)
        bright = (
            (region.min(axis=2) >= 115)
            & ((region.max(axis=2) - region.min(axis=2)) <= 30)
        )
        min_frame_width = max(20, min(28, width // 5))
        max_frame_width = min(160, max(min_frame_width, int(round(width * 0.55))))

        for bottom in range(y_start, y_stop):
            for start, end in _bright_runs(bright[bottom]):
                frame_width = end - start
                if not min_frame_width <= frame_width <= max_frame_width:
                    continue
                distance_to_edge = start if corner == "left" else bright.shape[1] - end
                if distance_to_edge > min(80, max(16, int(round(width * 0.12)))):
                    continue

                top_start = max(y0, bottom - int(round(frame_width * 1.75)))
                top_stop = bottom - max(18, int(round(frame_width * 0.58)))
                for top in range(top_start, top_stop):
                    horizontal = float(np.mean(bright[top, start:end]))
                    if horizontal < 0.72:
                        continue
                    left_columns = bright[
                        top:bottom,
                        max(0, start - 4):min(bright.shape[1], start + 5),
                    ]
                    right_columns = bright[
                        top:bottom,
                        max(0, end - 5):min(bright.shape[1], end + 4),
                    ]
                    left_support = float(np.mean(left_columns.any(axis=1)))
                    right_support = float(np.mean(right_columns.any(axis=1)))
                    fully_framed = min(left_support, right_support) >= 0.52
                    clipped_outer_stroke = (
                        distance_to_edge <= 10
                        and (right_support if corner == "left" else left_support) >= 0.70
                    )
                    if fully_framed or clipped_outer_stroke:
                        candidates.append({
                            "bottom": bottom,
                            "top": top,
                            "box_px": [rx0 + start, top, rx0 + end, bottom + 1],
                        })
                        break

    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["bottom"], item["box_px"][2] - item["box_px"][0]))


def _contains_clinical_color(strip):
    """Refuse a seam move that would discard a narrow colored scale/overlay."""
    if strip.size == 0:
        return False
    values = strip.astype(np.int16)
    colored = (
        ((values.max(axis=2) - values.min(axis=2)) >= 45)
        & (values.max(axis=2) >= 70)
    )
    min_height = min(strip.shape[0], max(2, int(np.ceil(strip.shape[0] * 0.45))))
    columns = np.sum(colored, axis=0) >= min_height
    return any(end - start >= 3 for start, end in _bright_runs(columns))


def reconcile_panel_boundaries(images, metadata, max_shift_px=24):
    """Recrop trusted neighboring panels when a seam splits an embedded label.

    Panels must be exact crops of the same audited source. Adjoining crop boxes
    form independent overlap components: a 2x2 source can adjust only A/C,
    while a full-width lower panel links both upper panels to one shared seam.
    No pixels are painted, erased, inpainted, or copied from another image.
    """
    if not 0 <= max_shift_px <= 64:
        raise ValueError("max_boundary_shift_px must be between 0 and 64")
    decisions = [[] for _ in images]
    if not max_shift_px:
        return images, decisions

    sources = {}
    groups = {}
    boxes = {}
    for index, (image, entry) in enumerate(zip(images, metadata)):
        placement, _ = label_details(entry)
        if placement not in {"embedded", "overlay", "overlap"}:
            continue
        source = entry.get("source")
        box = entry.get("crop_box_px")
        if not isinstance(source, str) or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            resolved = str(Path(source).expanduser().resolve(strict=True))
            normalized = tuple(int(value) for value in box)
            if resolved not in sources:
                sources[resolved] = Image.open(resolved).convert("RGB")
            expected = sources[resolved].crop(normalized)
        except (OSError, TypeError, ValueError):
            continue
        if expected.size != image.size or expected.tobytes() != image.convert("RGB").tobytes():
            continue
        boxes[index] = list(normalized)
        groups.setdefault(resolved, []).append(index)

    for source, indexes in groups.items():
        if len(indexes) < 2:
            continue
        pixels = np.asarray(sources[source])
        seams = {}
        for upper in indexes:
            ux0, _, ux1, uy1 = boxes[upper]
            for lower in indexes:
                if upper == lower:
                    continue
                lx0, ly0, lx1, _ = boxes[lower]
                overlap = min(ux1, lx1) - max(ux0, lx0)
                if uy1 == ly0 and overlap >= 16:
                    seams.setdefault(uy1, []).append((upper, lower))

        for boundary, links in seams.items():
            pending = set(range(len(links)))
            while pending:
                first = pending.pop()
                component = {links[first][0], links[first][1]}
                changed = True
                while changed:
                    changed = False
                    for link_index in list(pending):
                        upper, lower = links[link_index]
                        if upper in component or lower in component:
                            component.update((upper, lower))
                            pending.remove(link_index)
                            changed = True

                upper_panels = {upper for upper, lower in links if upper in component and lower in component}
                lower_panels = {lower for upper, lower in links if upper in component and lower in component}
                findings = []
                for upper in upper_panels:
                    finding = boxed_label_bottom(pixels, boxes[upper], boundary, max_shift_px)
                    if finding and finding["bottom"] >= boundary:
                        findings.append((upper, finding))
                if not findings:
                    continue

                adjusted = max(finding["bottom"] + 2 for _, finding in findings)
                if adjusted - boundary > max_shift_px:
                    continue
                if any(
                    adjusted >= boxes[lower][3]
                    or _contains_clinical_color(
                        pixels[boundary:adjusted, boxes[lower][0]:boxes[lower][2], :]
                    )
                    for lower in lower_panels
                ):
                    continue

                frames = [finding["box_px"] for _, finding in findings]
                for index, side in [
                    *((upper, "bottom") for upper in upper_panels),
                    *((lower, "top") for lower in lower_panels),
                ]:
                    original_box = list(boxes[index])
                    boxes[index][3 if side == "bottom" else 1] = adjusted
                    decisions[index].append({
                        "axis": "y",
                        "side": side,
                        "original_boundary_px": boundary,
                        "adjusted_boundary_px": adjusted,
                        "shift_px": adjusted - boundary,
                        "reason": "preserve-complete-embedded-label-frame",
                        "detected_label_boxes_px": frames,
                        "source_crop_box_px": original_box,
                        "effective_crop_box_px": list(boxes[index]),
                    })

    repaired = list(images)
    for index, changes in enumerate(decisions):
        if changes:
            source = str(Path(metadata[index]["source"]).expanduser().resolve())
            repaired[index] = sources[source].crop(tuple(boxes[index]))
    return repaired, decisions


def crop_safe_label_margin(image, box):
    """Crop a full exterior label band only when its remaining pixels are flat."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (int(value) for value in box)
    except (TypeError, ValueError):
        return None
    width, height = image.size
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        return None

    sides = {
        "left": x0 / width,
        "right": (width - x1) / width,
        "top": y0 / height,
        "bottom": (height - y1) / height,
    }
    side = min(sides, key=sides.get)
    pad = 2
    if side == "bottom":
        boundary = max(0, y0 - pad)
        region = (0, boundary, width, height)
        retained = (0, 0, width, boundary)
    elif side == "top":
        boundary = min(height, y1 + pad)
        region = (0, 0, width, boundary)
        retained = (0, boundary, width, height)
    elif side == "right":
        boundary = max(0, x0 - pad)
        region = (boundary, 0, width, height)
        retained = (0, 0, boundary, height)
    else:
        boundary = min(width, x1 + pad)
        region = (0, 0, boundary, height)
        retained = (boundary, 0, width, height)

    rx0, ry0, rx1, ry1 = region
    band_depth = ry1 - ry0 if side in ("top", "bottom") else rx1 - rx0
    dimension = height if side in ("top", "bottom") else width
    if band_depth <= 0 or band_depth > 0.30 * dimension:
        return None

    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    band = pixels[ry0:ry1, rx0:rx1]
    outside_label = np.ones(band.shape[:2], dtype=bool)
    bx0, bx1 = max(0, x0 - rx0 - pad), min(band.shape[1], x1 - rx0 + pad)
    by0, by1 = max(0, y0 - ry0 - pad), min(band.shape[0], y1 - ry0 + pad)
    outside_label[by0:by1, bx0:bx1] = False
    samples = band[outside_label]
    if len(samples) < 32:
        return None
    background = np.median(samples, axis=0)
    uniform_fraction = float(np.mean(np.max(np.abs(samples - background), axis=1) <= 18))
    if uniform_fraction < 0.985:
        return None
    return image.crop(retained), {"side": side, "pixels": band_depth}


def resolve_source_labels(images, metadata, requested_policy):
    """Make one conservative, figure-wide decision to avoid mixed/duplicate labels."""
    details = [label_details(entry) for entry in metadata]
    embedded = any(placement in {"embedded", "overlay", "overlap"} for placement, _ in details)
    exterior = [index for index, (placement, _) in enumerate(details)
                if placement in {"external-margin", "exterior-margin", "margin"}]

    if requested_policy == "preserve" or embedded:
        if requested_policy == "crop-safe-margin" and embedded:
            raise ValueError("embedded image labels cannot be safely cropped from an exterior margin")
        return images, "preserve", [{} for _ in images]

    if requested_policy == "crop-safe-margin" and len(exterior) != len(images):
        raise ValueError("crop-safe-margin requires an exterior-margin placement and label box for every panel")

    if exterior:
        cleaned = list(images)
        decisions = [{} for _ in images]
        for index in exterior:
            result = crop_safe_label_margin(cleaned[index], details[index][1])
            if result is None:
                if requested_policy == "crop-safe-margin":
                    raise ValueError("source-label margin contains image content or lacks a verified label box")
                return images, "preserve", [{} for _ in images]
            cleaned[index], decisions[index] = result
        return cleaned, "crop-safe-margin", decisions

    return images, "native", [{} for _ in images]


def layout_dimensions(panels, cols, band, gap):
    """Calculate exact row geometry without repeatedly rendering candidate grids."""
    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    gutter = max(8, gap if gap else int(max(sum(p.width for p in row) for row in rows) * 0.018))
    normalized_rows = []
    for row in rows:
        height = min(panel.height for panel in row)
        normalized_rows.append([
            (max(1, int(panel.width * height / panel.height)), height)
            for panel in row
        ])

    target_width = max(
        sum(width for width, _ in row) + gutter * (len(row) - 1)
        for row in normalized_rows
    )
    final_rows = []
    for row in normalized_rows:
        current_width = sum(width for width, _ in row) + gutter * (len(row) - 1)
        scale = target_width / current_width
        final_rows.append([
            (max(1, int(width * scale)), max(1, int(height * scale)))
            for width, height in row
        ])

    row_heights = [max(height for _, height in row) for row in final_rows]
    total_height = sum(row_heights) + band * len(final_rows)
    return target_width, total_height, final_rows, row_heights, gutter


def layout(panels, cols, band, bg, gap):
    """Compose a grid and return right/bottom anchors in source reading order."""
    target_width, total_height, final_rows, row_heights, gutter = layout_dimensions(
        panels, cols, band, gap
    )
    canvas = Image.new("RGB", (target_width, total_height), bg)
    rects = []; y = 0
    panel_index = 0
    for row_index, row in enumerate(final_rows):
        x = 0
        for width, height in row:
            panel = panels[panel_index].resize((width, height), Image.LANCZOS)
            canvas.paste(panel, (x, y))
            rects.append((x + width, y + row_heights[row_index]))
            x += width + gutter
            panel_index += 1
        y += row_heights[row_index] + band
    return canvas, rects


def evaluate_layout(panels, cols, band_in, box_width_in, box_height_in, gap):
    """Score a candidate using the actual slide-fit and fixed-size label bands."""
    band = 2 if band_in > 0 else 0
    for _ in range(12):
        width, height, _, _, _ = layout_dimensions(panels, cols, band, gap)
        fit = min(box_width_in / width, box_height_in / height)
        next_band = max(2, int(round(band_in / fit))) if band_in > 0 else 0
        if next_band == band:
            break
        band = next_band

    width, height, rows, _, gutter = layout_dimensions(panels, cols, band, gap)
    fit = min(box_width_in / width, box_height_in / height)
    displayed = [
        (panel_width * fit, panel_height * fit)
        for row in rows for panel_width, panel_height in row
    ]
    areas = [panel_width * panel_height for panel_width, panel_height in displayed]
    short_edges = [min(panel_width, panel_height) for panel_width, panel_height in displayed]
    empty_cells = len(rows) * cols - len(panels)

    return {
        "cols": cols,
        "rows": len(rows),
        "band_px": band,
        "gutter_px": gutter,
        "composite_width_px": width,
        "composite_height_px": height,
        "fit_in_per_px": fit,
        "min_panel_area_sq_in": min(areas),
        "min_panel_short_edge_in": min(short_edges),
        "total_panel_area_sq_in": sum(areas),
        "utilization_fraction": sum(areas) / (box_width_in * box_height_in),
        "empty_cells": empty_cells,
        "displayed_panel_sizes_in": [
            {"width": panel_width, "height": panel_height}
            for panel_width, panel_height in displayed
        ],
    }


def layout_score(candidate):
    """Protect the least-legible panel before comparing overall utilization."""
    return (
        candidate["min_panel_area_sq_in"],
        candidate["min_panel_short_edge_in"],
        candidate["total_panel_area_sq_in"],
        -candidate["empty_cells"],
        -candidate["rows"],
    )


def hexrgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--cols", type=int, default=None,
                    help="manual column count; omit to choose the most readable grid")
    ap.add_argument("--labels", default="")
    ap.add_argument("--geometry", default="panel_geometry.json")
    ap.add_argument("--gap-above-in", type=float, default=0.06)
    ap.add_argument("--gap-below-in", type=float, default=0.12)
    ap.add_argument("--label-pt", type=float, default=18.0)
    ap.add_argument("--glyph-ratio", type=float, default=0.62)
    ap.add_argument("--center-offset-in", type=float, default=0.0525)
    ap.add_argument("--slide-box-w-in", type=float, default=12.10)
    ap.add_argument("--slide-box-h-in", type=float, default=4.85)
    ap.add_argument("--bg", default="#061428")
    ap.add_argument("--gap", type=int, default=16)
    ap.add_argument("--source-label-policy", choices=("auto", "preserve", "crop-safe-margin"),
                    default="auto", help="preserve embedded labels; crop only verified exterior margins")
    ap.add_argument("--max-edge-px", type=int, default=4,
                    help="maximum removable white/gray rim depth on each side (default: 4)")
    ap.add_argument("--max-boundary-shift-px", type=int, default=24,
                    help="maximum safe source-row seam adjustment for a split label frame")
    ap.add_argument("--no-trim", action="store_true")
    a = ap.parse_args()

    if a.cols is not None and not 1 <= a.cols <= len(a.inputs):
        ap.error("--cols must be between 1 and the number of input panels")
    if a.slide_box_w_in <= 0 or a.slide_box_h_in <= 0:
        ap.error("slide-box dimensions must be positive")
    if not 0 <= a.max_edge_px <= 12:
        ap.error("--max-edge-px must be between 0 and 12")
    if not 0 <= a.max_boundary_shift_px <= 64:
        ap.error("--max-boundary-shift-px must be between 0 and 64")

    bg = hexrgb(a.bg)
    labels = [s for s in a.labels.split(",") if s] if a.labels else []
    panel_metadata = [source_metadata(path) for path in a.inputs]
    panels = [Image.open(p).convert("RGB") for p in a.inputs]
    for path, panel, metadata in zip(a.inputs, panels, panel_metadata):
        overwritten = overwritten_source_pixels(panel, metadata)
        if overwritten:
            ap.error(
                f"panel {path} contains a solid-color corner overwrite affecting "
                f"{overwritten} source-image pixels; preserve embedded labels instead of masking them"
            )
    try:
        panels, boundary_adjustments = reconcile_panel_boundaries(
            panels, panel_metadata, a.max_boundary_shift_px
        )
    except ValueError as error:
        ap.error(str(error))
    try:
        panels, label_policy, label_margins = resolve_source_labels(
            panels, panel_metadata, a.source_label_policy
        )
    except ValueError as error:
        ap.error(str(error))
    cleanup = []
    if not a.no_trim:
        prepared = []
        for panel in panels:
            cleaned, edges = clean_panel_edges(panel, a.max_edge_px)
            prepared.append(cleaned)
            cleanup.append(edges)
        panels = prepared
    else:
        cleanup = [{side: 0 for side in ("top", "bottom", "left", "right")} for _ in panels]

    glyph_h = a.label_pt / 72.0 * a.glyph_ratio          # on-screen label height (in)
    native_labels = label_policy != "preserve"
    band_in = a.gap_above_in + glyph_h + a.gap_below_in if native_labels else 0
    drop_in = a.gap_above_in + a.center_offset_in         # panel bottom -> label box center

    candidate_columns = [a.cols] if a.cols is not None else range(1, len(panels) + 1)
    candidates = [
        evaluate_layout(panels, columns, band_in,
                        a.slide_box_w_in, a.slide_box_h_in, a.gap)
        for columns in candidate_columns
    ]
    selected = max(candidates, key=layout_score)
    cols = selected["cols"]
    band = selected["band_px"]
    comp, rects = layout(panels, cols, band, bg, a.gap)
    comp.save(a.output)
    W, H = comp.size
    fit = min(a.slide_box_w_in / W, a.slide_box_h_in / H)
    drop_px = drop_in / fit

    name = os.path.splitext(os.path.basename(a.output))[0]
    geom = {}
    if os.path.exists(a.geometry):
        geom = json.load(open(a.geometry))
    geom[name] = ([{"label": labels[i] if i < len(labels) else "",
                    "fx_right": rects[i][0] / W,
                    "fy_center": (rects[i][1] + drop_px) / H}
                   for i in range(len(rects))] if native_labels else [])
    json.dump(geom, open(a.geometry, "w"), indent=1)

    # postprocess sidecar (so the bundled build_deck.py asset gate passes)
    json.dump({"command": "recompose-panels-banded", "asset_type": "figure",
               "labels": labels, "native_labels": native_labels,
               "source_label_policy": label_policy,
               "embedded_labels": labels if not native_labels else [],
               "max_edge_px": a.max_edge_px,
               "max_boundary_shift_px": a.max_boundary_shift_px,
               "panel_cleanup": [
                   {"source": os.path.abspath(path),
                    "label": labels[index] if index < len(labels) else "",
                    "edge_trim_px": cleanup[index],
                    "label_margin_crop": label_margins[index],
                    "label_action": ("preserved" if not native_labels else
                                     "cropped-exterior-margin" if label_margins[index] else
                                     "already-absent"),
                    "label_overwritten_pixels": 0,
                    "boundary_adjustments": boundary_adjustments[index]}
                   for index, path in enumerate(a.inputs)
               ],
               "source_inputs": [os.path.abspath(path) for path in a.inputs],
               "layout_mode": "manual" if a.cols is not None else "auto",
               "cols": cols, "rows": selected["rows"],
               "slide_box_w_in": a.slide_box_w_in,
               "slide_box_h_in": a.slide_box_h_in,
               "layout_candidates": candidates,
               "gap_above_in": a.gap_above_in, "gap_below_in": a.gap_below_in,
               "label_pt": a.label_pt},
              open(a.output + ".postprocess.json", "w"))
    print(f"{name}: {W}x{H}px layout={selected['rows']}x{cols} "
          f"min-panel={selected['min_panel_area_sq_in']:.2f}sq.in "
          f"labels={label_policy} band={band}px fit={fit:.5f} "
          f"-> geometry[{name}] x{len(rects)} written to {a.geometry}")


if __name__ == "__main__":
    main()
