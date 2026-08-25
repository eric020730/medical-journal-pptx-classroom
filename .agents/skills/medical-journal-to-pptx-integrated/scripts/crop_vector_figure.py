#!/usr/bin/env python3
"""
crop_vector_figure.py

Detect and crop a VECTOR figure (flowchart / tree / algorithm diagram) from a
medical-journal PDF page, using a different logic path from raster photo panels.

WHY a separate path: flowcharts/trees are drawn as vector boxes + connector
lines + text, not as an embedded raster image. The panel pipeline (exact
embedded-image-rect crop, panel split, row alignment, A/B/C/D labels) does not
apply. Instead we find the diagram's bounding box from its vector elements,
keep ALL boxes/arrows/connectors/text, and crop with a safe white margin.

DETECTION (content-based):
A paper Figure is treated as a vector figure when the page has a substantial
cluster of vector drawings (closed boxes + connector lines) and that cluster
region contains essentially no embedded raster image pixels. In the normal
skill flow this is also implied when a paper Figure number has NO matching
extracted raster image: that missing figure is almost always a vector diagram.
Tables are excluded because they are handled by the table pipeline, not as
Figures.

USAGE:
  # detect only (prints JSON: is_vector_figure, bbox, raster_frac, n_boxes)
  python3 crop_vector_figure.py SRC.pdf --page 3 --detect-only

  # crop the vector figure on page 3 to a PNG with an 8 pt margin
  python3 crop_vector_figure.py SRC.pdf final_assets/Figure_2.png --page 3

Key options:
  --page N          1-based PDF page that holds the diagram (required)
  --dpi 300         render DPI
  --margin 8        margin in PDF points added around the detected bbox
  --cluster-gap 22  proximity (pt) for merging drawings into one diagram cluster
  --raster-thr 0.05 max raster coverage in the cluster for it to count as vector
  --header 70 --footer 55  page bands (pt) whose rules/running text are ignored
"""
import argparse, json, sys
from pathlib import Path
import pymupdf as fitz


def _drawing_rects(pg, header, footer):
    W, H = pg.rect.width, pg.rect.height
    out = []
    for d in pg.get_drawings():
        r = d["rect"]
        if r.width < 2 or r.height < 2:
            continue
        if r.y1 < header or r.y0 > H - footer:      # header / footer band
            continue
        if r.width > W * 0.85 and r.height < 3:     # full-width rule line
            continue
        out.append([r.x0, r.y0, r.x1, r.y1])
    return out


def _merge(rects, pad):
    boxes = [r[:] for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        for b in boxes:
            placed = False
            for o in out:
                if (b[0] <= o[2] + pad and b[2] >= o[0] - pad and
                        b[1] <= o[3] + pad and b[3] >= o[1] - pad):
                    o[0] = min(o[0], b[0]); o[1] = min(o[1], b[1])
                    o[2] = max(o[2], b[2]); o[3] = max(o[3], b[3])
                    placed = True; changed = True
                    break
            if not placed:
                out.append(b[:])
        boxes = out
    return boxes


def _raster_frac_in(pg, box):
    bx = fitz.Rect(*box)
    area = bx.get_area() or 1
    cov = 0.0
    for im in pg.get_images(full=True):
        for r in pg.get_image_rects(im[0]):
            inter = r & bx
            if inter:
                cov += inter.get_area()
    return cov / area


def detect(pg, cluster_gap, header, footer, raster_thr):
    rects = _drawing_rects(pg, header, footer)
    if not rects:
        return {"is_vector_figure": False, "reason": "no vector drawings",
                "bbox": None, "n_boxes": 0, "raster_frac": None}
    clusters = _merge(rects, cluster_gap)
    clusters.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    fc = clusters[0]
    rfrac = _raster_frac_in(pg, fc)
    n_in = sum(1 for r in rects if r[0] >= fc[0] - 1 and r[2] <= fc[2] + 1
               and r[1] >= fc[1] - 1 and r[3] <= fc[3] + 1)
    is_vec = (rfrac <= raster_thr) and (n_in >= 4)
    return {"is_vector_figure": bool(is_vec),
            "reason": "vector cluster, low raster coverage" if is_vec
                      else f"raster_frac={rfrac:.3f} or too few boxes",
            "bbox": [round(v, 1) for v in fc], "n_boxes": n_in,
            "raster_frac": round(rfrac, 3)}


def crop(pg, box, dpi, margin, out_path):
    z = dpi / 72.0
    clip = fitz.Rect(box[0] - margin, box[1] - margin,
                     box[2] + margin, box[3] + margin)
    pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip)
    pix.save(out_path)
    return pix.width, pix.height


def _content_bbox_excluding_frame(pg, frame, frac=0.95):
    """Union of all inner drawing rects + text inside the frame, EXCLUDING the
    outer frame rectangle itself (the largest rect). This is the true content
    extent, so cropping to it removes the frame without clipping any inner box,
    even when an inner box sits only ~2 pt inside the frame edge.
    """
    fr = fitz.Rect(*frame)
    farea = fr.get_area() or 1
    c = [1e9, 1e9, -1e9, -1e9]

    def acc(x0, y0, x1, y1):
        c[0] = min(c[0], x0); c[1] = min(c[1], y0)
        c[2] = max(c[2], x1); c[3] = max(c[3], y1)

    for d in pg.get_drawings():
        r = d["rect"]
        if r.width < 2 or r.height < 2:
            continue
        if r.get_area() > frac * farea:           # skip the outer frame itself
            continue
        if (r.x0 >= frame[0] - 1 and r.x1 <= frame[2] + 1 and
                r.y0 >= frame[1] - 1 and r.y1 <= frame[3] + 1):
            acc(r.x0, r.y0, r.x1, r.y1)
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            x0, y0, x1, y1 = l["bbox"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if frame[0] <= cx <= frame[2] and frame[1] <= cy <= frame[3]:
                acc(x0, y0, x1, y1)
    if c[2] < c[0]:
        return None
    return c


def crop_inside_frame(pg, box, dpi, inset, white_margin, out_path,
                      white_thr=245):
    """Remove a decorative outer rectangle frame and pad even white margins.

    The cut targets the CONTENT bbox (union of all inner boxes + text, excluding
    the outer frame rect) rather than a fixed inward inset, so an inner box that
    sits only ~2 pt inside the frame edge is never clipped. The content bbox is
    clamped to stay at least 1 pt inside the frame so the frame stroke is
    excluded, rendered, trimmed to content, then padded. Internal boxes, arrows,
    connectors, and text are preserved. Opt-in; default preserves frames.
    """
    from PIL import Image
    import numpy as np
    z = dpi / 72.0
    cb = _content_bbox_excluding_frame(pg, box)
    if cb is None:                                # fallback: simple inset
        clip = fitz.Rect(box[0] + inset, box[1] + inset,
                         box[2] - inset, box[3] - inset)
    else:
        m = 1.5                                    # tiny safety pad around content
        x0 = max(cb[0] - m, box[0] + 1)
        y0 = max(cb[1] - m, box[1] + 1)
        x1 = min(cb[2] + m, box[2] - 1)
        y1 = min(cb[3] + m, box[3] - 1)
        clip = fitz.Rect(x0, y0, x1, y1)
    pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip)
    pix.save(out_path)
    im = Image.open(out_path).convert("RGB")
    g = np.asarray(im.convert("L")).astype(int)
    ink = g < white_thr
    ys = np.where(ink.any(1))[0]
    xs = np.where(ink.any(0))[0]
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    cw, ch = im.size
    canvas = Image.new("RGB", (cw + 2 * white_margin, ch + 2 * white_margin),
                       (255, 255, 255))
    canvas.paste(im, (white_margin, white_margin))
    canvas.save(out_path)
    return canvas.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--page", type=int, required=True, help="1-based page")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--margin", type=float, default=8)
    ap.add_argument("--cluster-gap", type=float, default=22)
    ap.add_argument("--raster-thr", type=float, default=0.05)
    ap.add_argument("--header", type=float, default=70)
    ap.add_argument("--footer", type=float, default=55)
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--strip-outer-frame", action="store_true",
                    help="Remove a decorative outer rectangle frame, then add a "
                         "uniform white margin on all four sides.")
    ap.add_argument("--white-margin", type=int, default=44,
                    help="White margin in px added on each side when "
                         "--strip-outer-frame is used (default 44).")
    ap.add_argument("--frame-inset", type=float, default=3.0,
                    help="PDF points to inset from the detected frame so the "
                         "frame stroke + halo are excluded (default 3).")
    a = ap.parse_args()

    doc = fitz.open(a.pdf)
    pg = doc[a.page - 1]
    info = detect(pg, a.cluster_gap, a.header, a.footer, a.raster_thr)

    if a.detect_only:
        print(json.dumps(info, ensure_ascii=False))
        return
    if not info["is_vector_figure"]:
        print(json.dumps({"error": "not detected as a vector figure", **info},
                         ensure_ascii=False))
        sys.exit(2)
    if not a.output:
        print("error: output path required when cropping", file=sys.stderr)
        sys.exit(1)
    if a.strip_outer_frame:
        w, h = crop_inside_frame(pg, info["bbox"], a.dpi, a.frame_inset,
                                 a.white_margin, a.output)
        info["outer_frame_stripped"] = True
        info["white_margin_px"] = a.white_margin
        info["frame_inset_pt"] = a.frame_inset
    else:
        w, h = crop(pg, info["bbox"], a.dpi, a.margin, a.output)
    output = Path(a.output).expanduser().resolve()
    output.with_suffix(output.suffix + ".postprocess.json").write_text(
        json.dumps(
            {
                "command": "crop-vector-figure",
                "asset_type": "flowchart",
                "source": str(Path(a.pdf).expanduser().resolve()),
                "page": a.page,
                "dpi": a.dpi,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"wrote": a.output, "size": [w, h], **info},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
