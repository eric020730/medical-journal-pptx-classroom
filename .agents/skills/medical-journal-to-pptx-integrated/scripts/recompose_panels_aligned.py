#!/usr/bin/env python3
"""
recompose_panels_aligned.py

Drop-in helper for the medical-journal-to-pptx skill that implements two
figure-layout behaviors:

  1. Row-height alignment ("match-height"): every panel in a row is scaled to a
     common height (default: the minimum panel height across the figure, so we
     only downscale and stay crisp). This makes the top and bottom edges of
     same-row panels line up (e.g. a wide MRI panel A aligns with a square
     arthroscopy panel B), giving a tidy grid even when source panels differ in
     size.

  2. Panel labels OUTSIDE the image: A/B/C/D are drawn in the dark gap BELOW
     each panel, right-aligned to that panel's right edge, in the caption color
     (default #8FA8C8) at a FIXED font size (default 54 px) regardless of figure
     size. The original in-image panel letters are excluded by cropping each
     panel to its own content (use individual panel crops, not a composite that
     includes the printed letters).

Gaps between panels are filled with the slide background color (default
#061428) so they blend into the dark slide instead of showing white strips.

Do NOT use this for flowcharts/algorithms/diagrams or for tables.

Usage (individual panel crops, in reading order = row-major):
  python3 recompose_panels_aligned.py OUT.png \
    --inputs A.png B.png C.png D.png --cols 2 --labels A,B,C,D

Key options:
  --cols N            columns in the grid (default = number of inputs => 1 row)
  --labels A,B,C,D    labels in reading order (omit for no labels)
  --font-size 54      FIXED label px size for every figure (default 54)
  --label-color #8FA8C8   caption color for labels
  --bg #061428        gap / background color (match the slide bg_page)
  --gap 16            uniform gap in px between panels and around label rows
  --row-height min|median   common row height strategy (default: min)
  --edge-white-thr / --edge-white-frac   near-white edge-trim controls
"""
import argparse
import json
from PIL import Image, ImageDraw, ImageFont
import glob
import os
from pathlib import Path


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _find_bold_font():
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for p in (
        "DejaVuSans-Bold.ttf",
        str(windows_fonts / "arialbd.ttf"),
        str(windows_fonts / "segoeuib.ttf"),
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            ImageFont.truetype(p, 12)
            return p
        except Exception:
            pass
    hits = glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
    return hits[0] if hits else None


def _find_regular_font():
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for c in (
        "DejaVuSans.ttf",
        "Arial.ttf",
        "LiberationSans-Regular.ttf",
        str(windows_fonts / "arial.ttf"),
        str(windows_fonts / "segoeui.ttf"),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            ImageFont.truetype(c, 10); return c
        except Exception:
            pass
    hits = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
    return hits[0] if hits else None


def edge_trim(im, thr=238, frac=0.72):
    """Iteratively crop near-white rows/cols from all four sides."""
    im = im.convert("RGB")
    px = im.load()
    w, h = im.size
    rw = lambda y: sum(1 for x in range(w) if min(px[x, y]) >= thr) / w >= frac
    cw = lambda x: sum(1 for y in range(h) if min(px[x, y]) >= thr) / h >= frac
    t, b, l, r = 0, h - 1, 0, w - 1
    while t < b and rw(t):
        t += 1
    while b > t and rw(b):
        b -= 1
    while l < r and cw(l):
        l += 1
    while r > l and cw(r):
        r -= 1
    return im.crop((l, t, r + 1, b + 1))


def frame_panel(im, fw, rgb):
    """Paint the outermost `fw` px ring of the panel with the slide bg color.
    Covers thin light-grey/film border rims that edge_trim leaves behind
    (edge_trim only removes near-white, not mid-grey, edges). Conservative:
    fw=2-3 px hides the rim without eating real content."""
    if fw <= 0:
        return im
    im = im.convert("RGB").copy()
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            if x < fw or x >= w - fw or y < fw or y >= h - fw:
                px[x, y] = rgb
    return im


def _row_width(row, gap):
    return sum(p.width for p in row) + gap * (len(row) - 1)


def _solve_label_px(target_in, box_w_in, box_h_in, W, row_h_sum, nrows, gap):
    """Pick the source label px so that, after the figure is fit into the slide
    image box (preserving aspect), the label renders at `target_in` inches on
    screen — identical across figures regardless of each figure's fit scale.

    On-screen label height = px * fit_scale, fit_scale = min(box_w/W, box_h/H).
    H depends on px via the per-row label strips (label_h = 1.25*px), so for the
    height-limited case we solve px*(box_h)/(C + 1.25*nrows*px) = target.
    """
    C = row_h_sum + gap * (nrows - 1)            # content height, no label strips
    denom = box_h_in - 1.25 * nrows * target_in
    fs_h = (target_in * C / denom) if denom > 0 else None
    fs_w = target_in * W / box_w_in              # width-limited (W indep. of px)
    if fs_h:
        ch = row_h_sum + nrows * int(1.25 * fs_h) + gap * (nrows - 1)
        if box_h_in / ch <= box_w_in / W:        # height actually limits
            return max(8, int(round(fs_h)))
    return max(8, int(round(fs_w)))


def recompose(panels, cols, labels, font_size, label_rgb, bg_rgb, gap,
              row_height, equal_row_width, trim_thr, trim_frac,
              target_label_in=None, box_w_in=12.10, box_h_in=4.85,
              panel_frame=3, frame_rgb=None, bold=False):
    if frame_rgb is None:
        frame_rgb = bg_rgb
    panels = [edge_trim(p, trim_thr, trim_frac) for p in panels]
    # Cover residual light-grey/film rims with a bg-colored frame (default on).
    panels = [frame_panel(p, panel_frame, frame_rgb) for p in panels]

    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    labs = (labels or [None] * len(panels))
    rowlabs = [labs[i:i + cols] for i in range(0, len(labs), cols)]

    # Step 1 — within-row height alignment: scale every panel in a row to one
    # common height (so same-row top/bottom edges line up). "min" downscales
    # only (crisp); "median" allows mild upscaling.
    norm = []
    for row in rows:
        hs = [p.height for p in row]
        Hr = min(hs) if row_height == "min" else sorted(hs)[len(hs) // 2]
        norm.append([p.resize((max(1, round(p.width * Hr / p.height)), Hr),
                               Image.LANCZOS) for p in row])

    # Step 2 — equal row width: scale each row uniformly so every row has the
    # same total width. This aligns the left/right edges of every row (e.g. a
    # narrower C/D row is enlarged to match a wider A/B row), giving a clean
    # outer rectangle. Skipped for single-row figures.
    if equal_row_width and len(norm) > 1:
        target_w = max(_row_width(r, gap) for r in norm)
        rescaled = []
        for row in norm:
            f = target_w / _row_width(row, gap)
            rescaled.append([p.resize((max(1, round(p.width * f)),
                                       max(1, round(p.height * f))),
                                      Image.LANCZOS) for p in row])
        norm = rescaled

    row_w = [_row_width(row, gap) for row in norm]
    row_h = [max(p.height for p in row) for row in norm]
    cw = max(row_w)

    # When a target on-screen label height is requested, derive the per-figure
    # source label px so the final rendered label is the same size on every slide.
    if labels and target_label_in:
        font_size = _solve_label_px(target_label_in, box_w_in, box_h_in, cw,
                                    sum(row_h), len(norm), gap)

    font = None
    if labels:
        fp = _find_bold_font() if bold else _find_regular_font()
        font = ImageFont.truetype(fp, font_size) if fp else ImageFont.load_default()
    label_h = int(font_size * 1.25) if labels else 0
    ch = sum(row_h) + len(norm) * label_h + gap * (len(norm) - 1)
    canvas = Image.new("RGB", (cw, ch), bg_rgb)
    d = ImageDraw.Draw(canvas)

    y = 0
    for row, rlabs, rw, H in zip(norm, rowlabs, row_w, row_h):
        # left-align when rows are equal width; otherwise center each row
        x = 0 if equal_row_width and len(norm) > 1 else (cw - rw) // 2
        for p, lab in zip(row, rlabs):
            canvas.paste(p, (x, y))
            if lab:
                tb = d.textbbox((0, 0), lab, font=font)
                tw = tb[2] - tb[0]
                # OUTSIDE the panel: below it, right-aligned to its right edge
                d.text((x + p.width - tw, y + H + int(font_size * 0.12)),
                       lab, font=font, fill=label_rgb)
            x += p.width + gap
        y += H + label_h + gap
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--inputs", nargs="+", required=True,
                    help="Individual panel images in reading order (row-major).")
    ap.add_argument("--cols", type=int, default=None)
    ap.add_argument("--labels", default="",
                    help="Comma-separated labels in reading order, e.g. A,B,C,D")
    ap.add_argument("--font-size", type=int, default=54,
                    help="Fixed source label px (used when "
                         "--label-screen-height-in is not given).")
    ap.add_argument("--label-screen-height-in", type=float, default=None,
                    help="Target on-screen label height in inches. When set, the "
                         "source label px is derived per figure so every slide's "
                         "label is the same visual size after fitting.")
    ap.add_argument("--slide-box-w-in", type=float, default=12.10,
                    help="Slide image-box width in inches (build_deck figure box).")
    ap.add_argument("--slide-box-h-in", type=float, default=4.85,
                    help="Slide image-box height in inches (build_deck figure box).")
    ap.add_argument("--label-color", default="#8FA8C8")
    ap.add_argument("--bg", default="#061428")
    ap.add_argument("--gap", type=int, default=16)
    ap.add_argument("--row-height", choices=["min", "median"], default="min")
    ap.add_argument("--equal-row-width", dest="equal_row_width",
                    action="store_true", default=True,
                    help="Scale each row to a common total width so left/right "
                         "edges of all rows align (default: on).")
    ap.add_argument("--no-equal-row-width", dest="equal_row_width",
                    action="store_false",
                    help="Disable equal row width; center each row instead.")
    ap.add_argument("--edge-white-thr", type=int, default=238)
    ap.add_argument("--edge-white-frac", type=float, default=0.72)
    ap.add_argument("--panel-frame", type=int, default=3,
                    help="Width (px) of a bg-colored frame painted over each "
                         "panel's outer rim to hide light-grey/film border "
                         "lines that near-white edge-trim leaves. Default 3; "
                         "use 0 to disable.")
    ap.add_argument("--panel-frame-color", default=None,
                    help="Frame color (default = --bg).")
    ap.add_argument("--label-bold", dest="label_bold", action="store_true",
                    default=False,
                    help="Render A/B/C/D labels in bold. Default is non-bold "
                         "(regular weight).")
    a = ap.parse_args()

    panels = [Image.open(p) for p in a.inputs]
    cols = a.cols or len(panels)
    labels = [s.strip() for s in a.labels.split(",") if s.strip()] or None
    out = recompose(panels, cols, labels, a.font_size, _hex(a.label_color),
                    _hex(a.bg), a.gap, a.row_height, a.equal_row_width,
                    a.edge_white_thr, a.edge_white_frac,
                    target_label_in=a.label_screen_height_in,
                    box_w_in=a.slide_box_w_in, box_h_in=a.slide_box_h_in,
                    panel_frame=a.panel_frame,
                    frame_rgb=_hex(a.panel_frame_color) if a.panel_frame_color else None,
                    bold=a.label_bold)
    out.save(a.output)
    sidecar = Path(a.output + ".postprocess.json")
    sidecar.write_text(
        json.dumps(
            {
                "command": "recompose-panels-aligned",
                "asset_type": "figure",
                "labels": labels or [],
                "source_inputs": [str(Path(path).expanduser().resolve()) for path in a.inputs],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {a.output} {out.size} cols={cols} labels={labels} "
          f"target_in={a.label_screen_height_in} bg={a.bg}")


if __name__ == "__main__":
    main()
