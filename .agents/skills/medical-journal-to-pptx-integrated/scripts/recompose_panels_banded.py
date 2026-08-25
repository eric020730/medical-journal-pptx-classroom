#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recompose_panels_banded.py — lay out multi-panel figure crops into one image
with a reserved BACKGROUND BAND below each row, and emit per-panel label-anchor
geometry. The band leaves room so that A/B/C/D can be stamped LATER as native
slide text (see add_panel_labels.py) at a fixed point size — giving every label
the SAME actual size on screen regardless of how each figure is scaled, plus
precise control of the gap above (to its own panel) and below (to the next row).

This script does NOT burn labels into the image; it only reserves the band and
records where each label should go.

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
  --no-trim           skip near-white edge trim of each panel

Notes
-----
* The band height is held constant in ON-SCREEN inches across every figure by
  solving against each figure's fit-scale into the slide image box. Because the
  label is later drawn at a fixed point size, both the label size and the two
  gaps come out identical on every figure/slide.
* Pair this with add_panel_labels.py AFTER you build the .pptx.
"""
import argparse, json, os
from PIL import Image


def trim(img, thr=238, frac=0.72, maxcut=0.25):
    px = img.load(); w, h = img.size
    rw = lambda y: sum(1 for x in range(w) if min(px[x, y]) >= thr) / w >= frac
    cw = lambda x: sum(1 for y in range(h) if min(px[x, y]) >= thr) / h >= frac
    t, b, l, r = 0, h - 1, 0, w - 1
    while t < h * maxcut and rw(t): t += 1
    while b > h * (1 - maxcut) and rw(b): b -= 1
    while l < w * maxcut and cw(l): l += 1
    while r > w * (1 - maxcut) and cw(r): r -= 1
    return img.crop((l, t, r + 1, b + 1)) if r > l and b > t else img


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
    band = 2
    for _ in range(12):
        width, height, _, _, _ = layout_dimensions(panels, cols, band, gap)
        fit = min(box_width_in / width, box_height_in / height)
        next_band = max(2, int(round(band_in / fit)))
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
    ap.add_argument("--no-trim", action="store_true")
    a = ap.parse_args()

    if a.cols is not None and not 1 <= a.cols <= len(a.inputs):
        ap.error("--cols must be between 1 and the number of input panels")
    if a.slide_box_w_in <= 0 or a.slide_box_h_in <= 0:
        ap.error("slide-box dimensions must be positive")

    bg = hexrgb(a.bg)
    labels = [s for s in a.labels.split(",") if s] if a.labels else []
    panels = [Image.open(p).convert("RGB") for p in a.inputs]
    if not a.no_trim:
        panels = [trim(p) for p in panels]

    glyph_h = a.label_pt / 72.0 * a.glyph_ratio          # on-screen label height (in)
    band_in = a.gap_above_in + glyph_h + a.gap_below_in   # on-screen band per row
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
    geom[name] = [{"label": labels[i] if i < len(labels) else "",
                   "fx_right": rects[i][0] / W,
                   "fy_center": (rects[i][1] + drop_px) / H}
                  for i in range(len(rects))]
    json.dump(geom, open(a.geometry, "w"), indent=1)

    # postprocess sidecar (so the bundled build_deck.py asset gate passes)
    json.dump({"command": "recompose-panels-banded", "asset_type": "figure",
               "labels": labels, "native_labels": True,
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
          f"band={band}px fit={fit:.5f} "
          f"-> geometry[{name}] x{len(rects)} written to {a.geometry}")


if __name__ == "__main__":
    main()
