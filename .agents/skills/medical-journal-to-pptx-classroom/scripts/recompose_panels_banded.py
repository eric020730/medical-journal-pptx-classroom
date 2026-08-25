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
      --inputs A.png B.png C.png D.png --cols 2 --labels A,B,C,D \
      --geometry geometry.json \
      --gap-above-in 0.06 --gap-below-in 0.12 --label-pt 18

Key options
-----------
  --inputs            panel image files in reading order (pre-cropped)
  --cols              columns in the grid (default = number of inputs => 1 row)
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


def layout(panels, cols, band, bg, gap):
    """Compose grid (row-height align + equal-row-width) with a `band`-px gap
    below every row. Returns (image, [(panel_right_px, panel_bottom_px), ...])."""
    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    g = max(8, gap if gap else int(max(sum(p.width for p in r) for r in rows) * 0.018))
    srows = []
    for r in rows:
        rh = min(p.height for p in r)
        srows.append([p.resize((max(1, int(p.width * rh / p.height)), rh), Image.LANCZOS) for p in r])
    target_w = max(sum(p.width for p in r) + g * (len(r) - 1) for r in srows)
    frows = []
    for r in srows:
        cur = sum(p.width for p in r) + g * (len(r) - 1); f = target_w / cur
        frows.append([p.resize((max(1, int(p.width * f)), max(1, int(p.height * f))), Image.LANCZOS) for p in r])
    rowH = [max(p.height for p in r) for r in frows]
    H = sum(rowH) + band * len(frows)
    canvas = Image.new("RGB", (target_w, H), bg)
    rects = []; y = 0
    for ri, r in enumerate(frows):
        x = 0
        for p in r:
            canvas.paste(p, (x, y))
            rects.append((x + p.width, y + rowH[ri]))
            x += p.width + g
        y += rowH[ri] + band
    return canvas, rects


def hexrgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--cols", type=int, default=None)
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

    bg = hexrgb(a.bg)
    labels = [s for s in a.labels.split(",") if s] if a.labels else []
    cols = a.cols or len(a.inputs)
    panels = [Image.open(p).convert("RGB") for p in a.inputs]
    if not a.no_trim:
        panels = [trim(p) for p in panels]

    glyph_h = a.label_pt / 72.0 * a.glyph_ratio          # on-screen label height (in)
    band_in = a.gap_above_in + glyph_h + a.gap_below_in   # on-screen band per row
    drop_in = a.gap_above_in + a.center_offset_in         # panel bottom -> label box center

    # solve band px so band_in is constant on screen for THIS figure's fit-scale
    band = 2
    for _ in range(5):
        tmp, _ = layout(panels, cols, band, bg, a.gap)
        fit = min(a.slide_box_w_in / tmp.width, a.slide_box_h_in / tmp.height)
        band = max(2, int(round(band_in / fit)))
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
               "gap_above_in": a.gap_above_in, "gap_below_in": a.gap_below_in,
               "label_pt": a.label_pt},
              open(a.output + ".postprocess.json", "w"))
    print(f"{name}: {W}x{H}px band={band}px fit={fit:.5f} "
          f"-> geometry[{name}] x{len(rects)} written to {a.geometry}")


if __name__ == "__main__":
    main()
