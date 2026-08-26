#!/usr/bin/env python3
"""Post-process final figure/table assets for medical journal PPTX decks.

Commands:
  trim INPUT OUTPUT [--asset-type figure|table|flowchart|unknown] [--margin N] [--intermediate] [--bg-aware auto|on|off]
  labels INPUT OUTPUT --labels A,B,C,D [--asset-type ...] [--margin N] [--intermediate] [--bg-aware auto|on|off]
  microcrop INPUT OUTPUT --px 2
  same-width OUT_DIR INPUT_A INPUT_B [INPUT_C...]
  recompose-panels OUT --inputs A.png B.png ... --cols N [--gap PX]
  recompose-panels OUT --composite FIG.png --rows R --cols C [--gap PX]
  split-table INPUT OUT_A OUT_B --split-y Y --repeat-header-y Y
  audit-final ASSET_DIR [--spec SPEC] [--allow-table-margin a.png,b.png]
  notes-audit --spec SPEC [--require-all-notes]

Final raster Figures and Tables default to an exact 16 px safety margin added
after conservative trimming. Intermediate crops default to 0 px so downstream
panel recomposition can work from an unpadded core. Tables REFUSE to
write a final asset with margin < 8 px unless --intermediate is given (meaning
a later padding/white-canvas step restores the margin). Use microcrop only for
non-flowchart figure panels after visual review; never for tables or
flowcharts.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw
from notes_quality import (
    CJK_RE,
    SIMPLIFIED_ONLY_RE,
    duplicate_note_failures,
    has_closing_takeaway,
    note_diversity_failure,
)


POSTPROCESS_SUFFIX = ".postprocess.json"

# Final raster-asset safety margin (px). The margin is drawn on a new canvas
# after trimming, so it remains exact even when source content touches an edge.
FINAL_RASTER_SAFETY_MARGIN_PX = 16
FIGURE_SAFETY_MARGIN_PX = FINAL_RASTER_SAFETY_MARGIN_PX
TABLE_SAFETY_MARGIN_PX = FINAL_RASTER_SAFETY_MARGIN_PX
TABLE_MARGIN_MIN = 8
TABLE_MARGIN_MAX = 24
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


def _resolved(path: Path) -> Path:
    """Resolve a path without requiring the output to exist yet."""
    return path.expanduser().resolve(strict=False)


def _assert_distinct_paths(source: Path, *outputs: Path) -> None:
    """Refuse in-place image operations so a failed write cannot destroy source data."""
    source_resolved = _resolved(source)
    seen: set[Path] = set()
    for output in outputs:
        output_resolved = _resolved(output)
        if output_resolved == source_resolved:
            raise SystemExit(
                f"Refusing in-place image processing: input and output are both {source_resolved}"
            )
        if output_resolved in seen:
            raise SystemExit(f"Refusing duplicate output path: {output_resolved}")
        seen.add(output_resolved)


def content_bbox(im: Image.Image, threshold: int = 246) -> tuple[int, int, int, int]:
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, "white")
    diff = ImageChops.difference(rgb, bg).convert("L")
    mask = diff.point(lambda p: 255 if p > (255 - threshold) else 0)
    bbox = mask.getbbox()
    return bbox or (0, 0, im.width, im.height)


def expand_box(
    box: tuple[int, int, int, int],
    size: tuple[int, int],
    margin: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    w, h = size
    return (
        max(0, x0 - margin),
        max(0, y0 - margin),
        min(w, x1 + margin),
        min(h, y1 + margin),
    )


def postprocess_meta_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + POSTPROCESS_SUFFIX)


def write_postprocess_meta(output_path: Path, command: str, source: Path | None, **extra) -> None:
    meta = {
        "command": command,
        "output": str(output_path),
    }
    if source is not None:
        meta["source"] = str(source.expanduser().resolve())
    meta.update(extra)
    postprocess_meta_path(output_path).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_bottom_label_cut(im: Image.Image, threshold: int = 246) -> int | None:
    """Find a whitespace gap above bottom panel letters.

    This intentionally errs on the conservative side. If no clean gap is found,
    use --cut-bottom-px manually.
    """
    gray = im.convert("L")
    w, h = gray.size
    start = int(h * 0.72)
    rows = []
    for y in range(start, h):
        dark = sum(1 for x in range(w) if gray.getpixel((x, y)) < threshold)
        rows.append((y, dark / max(1, w)))

    # Bottom letters are usually sparse dark pixels after a nearly blank gap.
    sparse_tail = any(ratio < 0.035 for _, ratio in rows[-max(8, h // 80):])
    if not sparse_tail:
        return None

    gap_run = []
    for y, ratio in rows:
        if ratio < 0.006:
            gap_run.append(y)
            if len(gap_run) >= 10:
                return gap_run[0]
        else:
            gap_run = []
    return None


# ---------------------------------------------------------------------------
# Background-aware edge refinement.
#
# This is an ADDITIVE refinement layered on top of the existing white-based
# content_bbox()/trim_image() flow — it does NOT replace it. The baseline crop
# runs first and stays the baseline; this step only refines the outer edges of
# that result when the asset's real background is NOT pure white (e.g. a
# light-grey journal page, or a black image canvas with a residual light
# scanner hairline that the pure-white test cannot see).
# ---------------------------------------------------------------------------

def detect_bg_color(arr, ring: int = 4):
    """Representative colour of the dominant bucket in the outer pixel ring."""
    import numpy as _np
    h, w, _ = arr.shape
    ring = max(1, min(ring, h // 2, w // 2))
    s = _np.concatenate([
        arr[:ring].reshape(-1, 3), arr[-ring:].reshape(-1, 3),
        arr[:, :ring].reshape(-1, 3), arr[:, -ring:].reshape(-1, 3),
    ])
    b = (s // 8) * 8
    uniq, cnt = _np.unique(b, axis=0, return_counts=True)
    winning_bucket = uniq[cnt.argmax()]
    members = s[_np.all(b == winning_bucket, axis=1)]
    return _np.median(members, axis=0).astype(int)


def _peel_edges(arr, bg, bg_tol: int, edge_std: int, max_artifact: int,
                bg_frac: float):
    """Peel each of the 4 edges inward relative to ONE background colour `bg`.

    An outer line is removed if it is either:
      * background: >= `bg_frac` (~all) of its pixels are within `bg_tol` of
        `bg` — unlimited; OR
      * a CONTINUOUS thin anomaly rim (>= 0.6 of its pixels differ from `bg`,
        capped at `max_artifact`) that is either nearly uniform along its
        length (std <= `edge_std`) or has background two steps inward. The
        ">= 0.6 non-bg" guard separates a solid film hairline from a sparse
        TEXT line (mostly background with a few glyphs), so table titles and
        footnotes near an edge are never stripped.
    Stop at the first line that is neither — it carries real structure.
    """
    import numpy as _np
    h, w, _ = arr.shape
    rim_frac = 0.6

    def peel(get_line, count):
        cur, artifacts = 0, 0
        while cur < count:
            line = get_line(cur)
            far = _np.abs(line - bg).max(axis=1) > bg_tol
            if (~far).mean() >= bg_frac:
                cur += 1
                continue
            if artifacts < max_artifact and far.mean() >= rim_frac \
                    and _np.abs(line.mean(axis=0) - bg).max() > bg_tol:
                inner = get_line(min(cur + 2, count - 1))
                inner_is_bg = (_np.abs(inner - bg).max(axis=1) <= bg_tol).mean() >= 0.6
                if line.std(axis=0).max() <= edge_std or inner_is_bg:
                    cur += 1
                    artifacts += 1
                    continue
            break
        return cur

    top = peel(lambda i: arr[i, :, :], h)
    bottom = peel(lambda i: arr[h - 1 - i, :, :], h)
    left = peel(lambda i: arr[:, i, :], w)
    right = peel(lambda i: arr[:, w - 1 - i, :], w)
    return left, top, right, bottom


def background_aware_bbox(im: "Image.Image", bg_tol: int = 26, edge_std: int = 16,
                          max_artifact: int = 4, bg_frac: float = 0.99, passes: int = 2):
    """Return ((x0, y0, x1, y1), detected_bg_color).

    Runs `passes` rounds, re-detecting the background each round, so an asset
    with TWO backgrounds (e.g. a light page margin around a black image canvas)
    is handled: round 1 removes the page margin, round 2 re-detects the canvas
    colour and strips any residual hairline relative to it.
    """
    import numpy as _np
    arr = _np.asarray(im.convert("RGB")).astype(int)
    h, w, _ = arr.shape
    x0, y0, x1, y1 = 0, 0, w, h
    first_bg = None
    for _ in range(max(1, passes)):
        sub = arr[y0:y1, x0:x1]
        if sub.shape[0] < 4 or sub.shape[1] < 4:
            break
        bg = detect_bg_color(sub)
        if first_bg is None:
            first_bg = bg
        l, t, r, b = _peel_edges(sub, bg, bg_tol, edge_std, max_artifact, bg_frac)
        if (l, t, r, b) == (0, 0, 0, 0):
            break
        nx0, ny0, nx1, ny1 = x0 + l, y0 + t, x1 - r, y1 - b
        if nx0 >= nx1 or ny0 >= ny1:
            break
        x0, y0, x1, y1 = nx0, ny0, nx1, ny1
    bg_out = tuple(int(c) for c in (first_bg if first_bg is not None else (255, 255, 255)))
    return (x0, y0, x1, y1), bg_out


def bg_aware_refine(im: "Image.Image", margin: int, bg_tol: int = 26,
                    force: bool = False) -> tuple["Image.Image", dict]:
    """Additive edge refinement applied after the baseline white-based crop.

    In `auto` mode (force=False): if the current background is essentially pure
    white (every channel >= 250) the baseline result is already correct and is
    returned unchanged — so pure-white decks never regress. Otherwise (grey
    page or residual hairline on a dark canvas) the edges are re-trimmed
    relative to the detected background and `margin` is re-added in that same
    background colour, preserving the table safety-margin contract.
    """
    box, bg = background_aware_bbox(im, bg_tol=bg_tol)
    meta = {"bg_aware_applied": False, "detected_bg": list(bg)}
    if not force and min(bg) >= 250:
        return im, meta                       # near-pure-white: keep baseline result
    if box == (0, 0, im.width, im.height):
        return im, meta                       # nothing to refine; avoid re-padding twice
    core = im.crop(box)
    if margin > 0:
        out = Image.new("RGB", (core.width + 2 * margin, core.height + 2 * margin), tuple(bg))
        out.paste(core, (margin, margin))
    else:
        out = core
    meta["bg_aware_applied"] = True
    meta["content_box"] = list(box)
    return out, meta


def add_exact_safety_padding(
    image: "Image.Image",
    margin: int,
    asset_type: str,
    detected_background: object = None,
) -> tuple["Image.Image", dict]:
    """Add an exact post-trim safety canvas without consuming source pixels."""
    if margin < 0:
        raise ValueError("margin must be non-negative")
    unpadded_size = [image.width, image.height]
    if asset_type == "table":
        background = (255, 255, 255)
    elif (
        isinstance(detected_background, (list, tuple))
        and len(detected_background) == 3
    ):
        background = tuple(max(0, min(255, int(value))) for value in detected_background)
    else:
        import numpy as _np

        background = tuple(int(value) for value in detect_bg_color(
            _np.asarray(image.convert("RGB"))
        ))

    if margin:
        padded = Image.new(
            "RGB",
            (image.width + 2 * margin, image.height + 2 * margin),
            background,
        )
        padded.paste(image, (margin, margin))
    else:
        padded = image
    return padded, {
        "safety_margin_px": margin,
        "padding_background": list(background),
        "unpadded_size_px": unpadded_size,
        "padded_size_px": [padded.width, padded.height],
    }


def trim_image(
    input_path: Path,
    output_path: Path,
    margin: int,
    threshold: int,
    cut_bottom_px: int,
    remove_bottom_labels: bool,
    bg_aware: str = "auto",
    bg_tol: int = 26,
    asset_type: str = "figure",
    max_edge_px: int = 4,
) -> dict:
    im = Image.open(input_path).convert("RGB")
    # Refine the source background before a tight white-content crop. Running
    # broad background refinement after the crop can mistake a meaningful dark
    # diagram/table border newly exposed at the edge for disposable canvas.
    refine_meta = {"bg_aware_applied": False}
    if asset_type == "figure":
        # Clinical figures commonly use a meaningful black/grey acquisition
        # canvas.  Broad background peeling cannot distinguish that canvas
        # from disposable page background, so AUTO deliberately leaves it
        # intact and relies on the bounded (<= max_edge_px) seam cleaner below.
        import numpy as _np

        detected = tuple(int(value) for value in detect_bg_color(
            _np.asarray(im.convert("RGB"))
        ))
        refine_meta["detected_bg"] = list(detected)
        if bg_aware == "auto":
            refine_meta["bg_aware_skip_reason"] = (
                "clinical-figure-auto-preserves-source-canvas"
            )
        elif bg_aware == "on":
            original = im
            candidate, candidate_meta = bg_aware_refine(
                original, 0, bg_tol=bg_tol, force=True
            )
            box = candidate_meta.get("content_box")
            trims = [0, 0, 0, 0]
            if isinstance(box, list) and len(box) == 4:
                trims = [
                    int(box[0]),
                    int(box[1]),
                    int(original.width - box[2]),
                    int(original.height - box[3]),
                ]
            dark_or_colored_canvas = max(detected) < 235 or max(detected) - min(detected) > 12
            if (
                candidate_meta.get("bg_aware_applied")
                and dark_or_colored_canvas
                and max(trims) > max_edge_px
            ):
                refine_meta.update({
                    "bg_aware_rejected": True,
                    "bg_aware_skip_reason": "would-remove-clinical-canvas",
                    "rejected_edge_trim_px": {
                        "left": trims[0], "top": trims[1],
                        "right": trims[2], "bottom": trims[3],
                    },
                })
            else:
                im = candidate
                refine_meta = candidate_meta
    elif bg_aware != "off" and asset_type != "table":
        im, refine_meta = bg_aware_refine(
            im,
            0,
            bg_tol=bg_tol,
            force=(bg_aware == "on"),
        )
    elif asset_type == "table":
        refine_meta["detected_bg"] = [255, 255, 255]

    # Build an unpadded core first. Expanding a crop box inside the source does
    # not guarantee a real margin when content already touches a source edge.
    box = content_bbox(im, threshold)
    cropped = im.crop(box)

    if remove_bottom_labels:
        if cut_bottom_px <= 0:
            raise SystemExit(
                "Removing panel-label pixels requires an explicit positive "
                "--cut-bottom-px value after visual review; automatic label "
                "cropping is disabled."
            )
        if cut_bottom_px >= cropped.height:
            raise SystemExit("--cut-bottom-px would remove the complete image")
        cropped = cropped.crop((0, 0, cropped.width, cropped.height - cut_bottom_px))

    # Re-trim after optional bottom-label removal (baseline white-based result).
    box2 = content_bbox(cropped, threshold)
    result = cropped.crop(box2)

    # A single figure does not pass through the multipanel recomposer, so run
    # the same bounded, color-safe seam check after background refinement.
    # Tables and flowcharts remain untouched. Figure cleanup runs on the core
    # before the safety canvas is added, so the new default margin does not
    # disable the bounded seam protection.
    if asset_type == "figure":
        from recompose_panels_banded import clean_panel_edges

        result, edge_trim_px = clean_panel_edges(result, max_edge_px=max_edge_px)
        refine_meta["edge_trim_px"] = edge_trim_px
        refine_meta["max_edge_px"] = max_edge_px

    result, padding_meta = add_exact_safety_padding(
        result,
        margin,
        asset_type,
        refine_meta.get("detected_bg"),
    )
    refine_meta.update(padding_meta)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, quality=95)
    return {"bg_aware": bg_aware, **refine_meta}


def labels_command(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    _assert_distinct_paths(input_path, output_path)
    if args.cut_bottom_px <= 0:
        raise SystemExit(
            "The labels command no longer guesses where a label band ends. "
            "Pass an explicit, visually verified positive --cut-bottom-px value, or use "
            "trim/preserve when labels overlap image content."
        )
    labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    if not labels:
        raise SystemExit("--labels must contain at least one non-empty label")
    margin = resolve_asset_margin(args)
    asset_type = getattr(args, "asset_type", "figure")
    bg_aware = getattr(args, "bg_aware", "auto")
    bg_tol = getattr(args, "bg_tol", 26)
    refine = trim_image(
        input_path,
        output_path,
        margin,
        args.threshold,
        args.cut_bottom_px,
        True,
        bg_aware=bg_aware,
        bg_tol=bg_tol,
        asset_type=asset_type,
    )
    extra = dict(
        labels=labels,
        margin=margin,
        threshold=args.threshold,
        cut_bottom_px=args.cut_bottom_px,
        asset_type=asset_type,
        bg_tol=bg_tol,
        intermediate=bool(getattr(args, "intermediate", False)),
        **refine,
    )
    if asset_type == "table":
        extra["table_safety_margin_px"] = margin
    write_postprocess_meta(
        output_path,
        "labels",
        input_path,
        **extra,
    )
    meta_path = Path(args.output).with_suffix(Path(args.output).suffix + ".labels.json")
    meta_path.write_text(json.dumps({"panel_labels": labels}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"wrote {meta_path}")


def microcrop_command(args: argparse.Namespace) -> None:
    """Apply a tiny inward crop for non-flowchart figure panels.

    This is intentionally simple and conservative. It should be used only
    after normal trimming when a dark-slide contact sheet shows thin white edge
    pixels. Do not use it for tables or flowcharts.
    """
    input_path = Path(args.input)
    output_path = Path(args.output)
    _assert_distinct_paths(input_path, output_path)
    px = max(0, args.px)
    im = Image.open(args.input).convert("RGB")
    if px == 0:
        cropped = im
    elif im.width <= px * 2 or im.height <= px * 2:
        raise SystemExit("Image is too small for requested micro-crop")
    else:
        cropped = im.crop((px, px, im.width - px, im.height - px))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    cropped.save(args.output, quality=95)
    write_postprocess_meta(
        Path(args.output), "microcrop", Path(args.input),
        px=px, asset_type="figure", intermediate=True,
    )
    print(f"wrote {args.output} ({cropped.width}x{cropped.height}); microcrop_px={px}")


def same_width_command(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = [(Path(p), Image.open(p).convert("RGB")) for p in args.inputs]
    max_w = max(im.width for _, im in images)

    for path, im in images:
        canvas = Image.new("RGB", (max_w, im.height), "white")
        canvas.paste(im, ((max_w - im.width) // 2, 0))
        out_path = out_dir / path.name
        _assert_distinct_paths(path, out_path)
        canvas.save(out_path, quality=95)
        source_meta = _read_sidecar(path) or {}
        extra = {"output_width": max_w}
        for key in (
            "asset_type",
            "margin",
            "safety_margin_px",
            "table_safety_margin_px",
            "padding_background",
        ):
            if key in source_meta:
                extra[key] = source_meta[key]
        margin = extra.get("safety_margin_px")
        if isinstance(margin, int) and canvas.width > 2 * margin and canvas.height > 2 * margin:
            extra["unpadded_size_px"] = [canvas.width - 2 * margin, canvas.height - 2 * margin]
        extra["padded_size_px"] = [canvas.width, canvas.height]
        write_postprocess_meta(out_path, "same-width", path, **extra)
        print(f"wrote {out_path} ({canvas.width}x{canvas.height})")


def split_table_command(args: argparse.Namespace) -> None:
    """Split a long table while repeating its title/header on both halves.

    Use after visual review of the full table crop. The split-y coordinate
    should be a natural row or section boundary, never a row midpoint.
    repeat-header-y should include the table title band plus column headers.
    """
    input_path = Path(args.input)
    out_a = Path(args.out_a)
    out_b = Path(args.out_b)
    _assert_distinct_paths(input_path, out_a, out_b)
    im = Image.open(input_path).convert("RGB")
    x0 = max(0, args.crop_left)
    y0 = max(0, args.crop_top)
    x1 = im.width - max(0, args.crop_right)
    y1 = im.height - max(0, args.crop_bottom)
    if x1 <= x0 or y1 <= y0:
        raise SystemExit("Invalid crop margins for input image")

    im = im.crop((x0, y0, x1, y1))
    split_y = args.split_y - y0
    repeat_header_y = args.repeat_header_y - y0
    if not (0 < repeat_header_y < split_y < im.height):
        raise SystemExit(
            "Expected 0 < repeat-header-y < split-y < image height after crop margins"
        )

    header = im.crop((0, 0, im.width, repeat_header_y))
    top = im.crop((0, 0, im.width, split_y))
    bottom_body = im.crop((0, split_y, im.width, im.height))
    bottom = Image.new("RGB", (im.width, header.height + bottom_body.height), "white")
    bottom.paste(header, (0, 0))
    bottom.paste(bottom_body, (0, header.height))

    margin = args.margin
    if not TABLE_MARGIN_MIN <= margin <= TABLE_MARGIN_MAX:
        raise SystemExit(
            f"Final split-table outputs require --margin in "
            f"{TABLE_MARGIN_MIN}-{TABLE_MARGIN_MAX}px (received {margin})."
        )
    cores = [
        part.crop(content_bbox(part, args.threshold))
        for part in (top, bottom)
    ]
    max_w = max(core.width for core in cores)
    outputs = [(out_a, cores[0], "top"), (out_b, cores[1], "bottom")]
    for out_path, core, part in outputs:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Image.new(
            "RGB",
            (max_w + 2 * margin, core.height + 2 * margin),
            "white",
        )
        canvas.paste(core, (margin + (max_w - core.width) // 2, margin))
        canvas.save(out_path, quality=95)
        write_postprocess_meta(
            out_path,
            "split-table",
            input_path,
            asset_type="table",
            split_y=args.split_y,
            repeat_header_y=args.repeat_header_y,
            part=part,
            crop_left=args.crop_left,
            crop_top=args.crop_top,
            crop_right=args.crop_right,
            crop_bottom=args.crop_bottom,
            threshold=args.threshold,
            output_width=canvas.width,
            margin=margin,
            safety_margin_px=margin,
            table_safety_margin_px=margin,
            padding_background=[255, 255, 255],
            unpadded_size_px=[max_w, core.height],
            padded_size_px=[canvas.width, canvas.height],
        )
        print(f"wrote {out_path} ({canvas.width}x{canvas.height})")


def resolve_asset_margin(args: argparse.Namespace) -> int:
    """Resolve the effective trim margin given the asset type.

    Final raster Figures and Tables default to an exact 16 px safety margin.
    Intermediate crops default to 0 unless the caller explicitly requests a
    margin, because panel assembly should receive an unpadded core.
    """
    asset_type = getattr(args, "asset_type", "figure")
    margin = args.margin
    if margin is not None and margin < 0:
        raise SystemExit("Refusing a negative panel safety margin.")
    intermediate = bool(getattr(args, "intermediate", False))
    if margin is None:
        if intermediate:
            margin = 0
        elif asset_type in {"figure", "flowchart"}:
            margin = FIGURE_SAFETY_MARGIN_PX
        elif asset_type == "table":
            margin = TABLE_SAFETY_MARGIN_PX
        else:
            margin = 0
    if margin < 0:
        raise SystemExit("Refusing a negative crop margin.")

    if asset_type == "table":
        if not getattr(args, "intermediate", False) and margin < TABLE_MARGIN_MIN:
            raise SystemExit(
                f"Refusing to write final table asset with margin={margin}. "
                f"Final tables need an outer white safety margin of "
                f"{TABLE_MARGIN_MIN}-{TABLE_MARGIN_MAX} px (default "
                f"{TABLE_SAFETY_MARGIN_PX}). Re-run with --margin "
                f"{TABLE_SAFETY_MARGIN_PX}, or pass --intermediate if this is a "
                f"throwaway crop that a later padding step will fix."
            )
        if margin > TABLE_MARGIN_MAX and not getattr(args, "intermediate", False):
            raise SystemExit(
                f"Refusing final table margin={margin}; supported range is "
                f"{TABLE_MARGIN_MIN}-{TABLE_MARGIN_MAX}px."
            )
    if (
        asset_type in {"figure", "flowchart"}
        and not intermediate
        and margin != FINAL_RASTER_SAFETY_MARGIN_PX
    ):
        raise SystemExit(
            f"Final {asset_type} assets require an exact "
            f"{FINAL_RASTER_SAFETY_MARGIN_PX}px safety canvas; received {margin}. "
            "Use --intermediate for a non-final crop."
        )
    return margin


def trim_command(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    _assert_distinct_paths(input_path, output_path)
    margin = resolve_asset_margin(args)
    asset_type = getattr(args, "asset_type", "figure")
    bg_aware = getattr(args, "bg_aware", "auto")
    bg_tol = getattr(args, "bg_tol", 26)
    refine = trim_image(
        input_path,
        output_path,
        margin,
        args.threshold,
        args.cut_bottom_px,
        False,
        bg_aware=bg_aware,
        bg_tol=bg_tol,
        asset_type=asset_type,
    )
    extra = dict(
        margin=margin,
        threshold=args.threshold,
        cut_bottom_px=args.cut_bottom_px,
        asset_type=asset_type,
        bg_tol=bg_tol,
        intermediate=bool(getattr(args, "intermediate", False)),
        **refine,
    )
    if asset_type == "table":
        extra["table_safety_margin_px"] = margin
    write_postprocess_meta(
        output_path,
        "trim",
        input_path,
        **extra,
    )
    applied = refine.get("bg_aware_applied")
    print(f"wrote {args.output} (asset_type={asset_type}, margin={margin}, "
          f"bg_aware={bg_aware}, applied={applied})")


def table_split_group(path: Path) -> str | None:
    match = re.match(r"^(Table[_ -]?\d+)[A-Z]", path.stem, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower().replace(" ", "_").replace("-", "_")


def spec_slides_with_images(spec_path: Path) -> list[tuple[dict, Path]]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = []
    for slide in spec.get("slides", []):
        image = slide.get("image")
        if not image:
            continue
        path = Path(image)
        if not path.is_absolute():
            path = (spec_path.parent / path).resolve()
        out.append((slide, path))
    return out


def spec_image_paths(spec_path: Path) -> list[Path]:
    return [path for _, path in spec_slides_with_images(spec_path)]


def _runmanifest_mentions(asset_dir: Path, name: str) -> bool:
    """True if a RUN_MANIFEST.md near the assets documents this asset name."""
    for base in (asset_dir, asset_dir.parent, asset_dir.parent.parent):
        rm = base / "RUN_MANIFEST.md"
        try:
            if rm.exists() and name in rm.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _looks_like_table(path: Path, sidecar: dict) -> bool:
    if sidecar.get("asset_type") == "table":
        return True
    return bool(re.match(r"^table[_ -]?\d", path.stem, re.IGNORECASE))


def _read_sidecar(image_path: Path) -> dict | None:
    sc = postprocess_meta_path(image_path)
    if not sc.exists():
        return None
    try:
        return json.loads(sc.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _valid_rgb(value: object) -> bool:
    if isinstance(value, str):
        return bool(re.fullmatch(r"#?[0-9A-Fa-f]{6}", value.strip()))
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, int) and 0 <= item <= 255 for item in value)
    )


def _rgb_tuple(value: object) -> tuple[int, int, int] | None:
    if isinstance(value, str) and re.fullmatch(r"#?[0-9A-Fa-f]{6}", value.strip()):
        raw = value.strip().lstrip("#")
        return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))
    if (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 255 for item in value)
    ):
        return tuple(value)
    return None


def _padding_pixels_match(
    image: Image.Image, margin: int, background: tuple[int, int, int]
) -> bool:
    """Verify that all four declared safety bands physically exist in the raster."""
    if "A" in image.getbands() or "transparency" in image.info:
        alpha = image.convert("RGBA").getchannel("A")
        if alpha.getextrema() != (255, 255):
            return False
    rgb = image.convert("RGB")
    if margin <= 0 or rgb.width <= 2 * margin or rgb.height <= 2 * margin:
        return False
    bands = (
        rgb.crop((0, 0, rgb.width, margin)),
        rgb.crop((0, rgb.height - margin, rgb.width, rgb.height)),
        rgb.crop((0, margin, margin, rgb.height - margin)),
        rgb.crop((rgb.width - margin, margin, rgb.width, rgb.height - margin)),
    )
    lossy = str(image.format or "").upper() in {"JPEG", "WEBP"}
    tolerance = 24 if lossy else 3
    total = 0
    mismatched = 0
    for band in bands:
        raw = band.tobytes()
        for offset in range(0, len(raw), 3):
            pixel = raw[offset:offset + 3]
            total += 1
            if max(abs(pixel[channel] - background[channel]) for channel in range(3)) > tolerance:
                mismatched += 1
    allowed_fraction = 0.03 if lossy else 0.0
    return total > 0 and mismatched / total <= allowed_fraction


def _core_has_visible_content(
    image: Image.Image, margin: int, background: tuple[int, int, int]
) -> bool:
    if margin <= 0 or image.width <= 2 * margin or image.height <= 2 * margin:
        return False
    core = image.convert("RGB").crop(
        (margin, margin, image.width - margin, image.height - margin)
    )
    raw = core.tobytes()
    different = 0
    for offset in range(0, len(raw), 3):
        pixel = raw[offset:offset + 3]
        if max(abs(pixel[channel] - background[channel]) for channel in range(3)) > 8:
            different += 1
    minimum = max(16, int(core.width * core.height * 0.0005))
    return different >= minimum


def validate_final_sidecar(image_path: Path, sidecar: dict) -> list[str]:
    """Validate the minimum evidence required for a final raster asset."""
    failures: list[str] = []
    prefix = f"final raster {image_path.name}"
    if "intermediate" in sidecar and not isinstance(sidecar.get("intermediate"), bool):
        failures.append(f"{prefix} intermediate must be a JSON boolean")
    elif sidecar.get("intermediate") is True:
        failures.append(f"{prefix} is marked intermediate and cannot be used in a deck")

    command = sidecar.get("command")
    if not isinstance(command, str) or not command.strip():
        failures.append(f"{prefix} command must be a non-empty string")

    source = sidecar.get("source")
    source_inputs = sidecar.get("source_inputs")
    if not (
        isinstance(source, str) and source.strip()
        or isinstance(source_inputs, list)
        and source_inputs
        and all(isinstance(item, str) and item.strip() for item in source_inputs)
    ):
        failures.append(f"{prefix} lacks a non-empty source/source_inputs provenance field")

    asset_type = sidecar.get("asset_type")
    if asset_type not in {"figure", "table", "flowchart"}:
        failures.append(f"{prefix} has invalid asset_type={asset_type!r}")

    margin = sidecar.get("safety_margin_px")
    if not isinstance(margin, int) or isinstance(margin, bool) or margin < 0:
        failures.append(f"{prefix} safety_margin_px must be a non-negative integer")
        margin = None
    elif asset_type in {"figure", "flowchart"} and margin != FINAL_RASTER_SAFETY_MARGIN_PX:
        failures.append(
            f"{prefix} requires exact {FINAL_RASTER_SAFETY_MARGIN_PX}px safety margin; "
            f"found {margin}"
        )
    elif asset_type == "table" and not TABLE_MARGIN_MIN <= margin <= TABLE_MARGIN_MAX:
        failures.append(
            f"{prefix} table safety margin must be {TABLE_MARGIN_MIN}-{TABLE_MARGIN_MAX}px; "
            f"found {margin}"
        )

    background = sidecar.get("padding_background")
    if not _valid_rgb(background):
        failures.append(f"{prefix} padding_background must be #RRGGBB or [r,g,b]")
    if asset_type == "table" and _rgb_tuple(background) != (255, 255, 255):
        failures.append(f"{prefix} table padding_background must be white")

    unpadded = sidecar.get("unpadded_size_px")
    padded = sidecar.get("padded_size_px")
    dimension_validity: dict[str, bool] = {}
    for field, value in (("unpadded_size_px", unpadded), ("padded_size_px", padded)):
        valid = (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
        )
        dimension_validity[field] = valid
        if not valid:
            failures.append(f"{prefix} {field} must be two positive integers")

    declared_margin = sidecar.get("margin")
    if not isinstance(declared_margin, int) or isinstance(declared_margin, bool):
        failures.append(f"{prefix} margin must be an integer")
    elif margin is not None and declared_margin != margin:
        failures.append(f"{prefix} margin must equal safety_margin_px")

    background_rgb = _rgb_tuple(background)
    try:
        with Image.open(image_path) as image:
            actual = [image.width, image.height]
            pixel_canvas_ok = (
                margin is not None
                and background_rgb is not None
                and _padding_pixels_match(image, margin, background_rgb)
            )
            core_content_ok = (
                margin is not None
                and background_rgb is not None
                and _core_has_visible_content(image, margin, background_rgb)
            )
    except OSError as error:
        failures.append(f"{prefix} cannot be decoded: {error}")
        return failures
    if dimension_validity["padded_size_px"] and padded != actual:
        failures.append(f"{prefix} padded_size_px={padded} does not match actual size={actual}")
    if (
        margin is not None
        and dimension_validity["unpadded_size_px"]
        and dimension_validity["padded_size_px"]
        and padded != [unpadded[0] + 2 * margin, unpadded[1] + 2 * margin]
    ):
        failures.append(
            f"{prefix} size arithmetic is inconsistent with safety_margin_px={margin}"
        )
    if asset_type == "table" and sidecar.get("table_safety_margin_px") != margin:
        failures.append(f"{prefix} table_safety_margin_px must equal safety_margin_px")
    if not pixel_canvas_ok:
        failures.append(
            f"{prefix} actual outer pixels do not contain the declared safety canvas/background"
        )
    if not core_content_ok:
        failures.append(f"{prefix} unpadded core has no visible content distinct from its background")
    return failures


_PANEL_FRAGMENT_RE = re.compile(r"(_panel[_\-]?[a-z0-9]+|panel_[a-z0-9]+)\.png$", re.I)
_FIG_NUM_RE = re.compile(r"\bfig(?:ure)?\s*\.?\s*([0-9]+)", re.I)


def _figure_number_of(slide: dict, image_path: Path):
    """Best-effort paper Figure number for a figure slide.
    Checks caption (most reliable), then title, then filename."""
    for field in (slide.get("caption"), slide.get("title"), image_path.name):
        if not field:
            continue
        m = _FIG_NUM_RE.search(str(field))
        if m:
            return m.group(1)
    return None


def audit_command(args: argparse.Namespace) -> None:
    asset_dir = Path(args.asset_dir).resolve()
    allow_table_margin = {
        n.strip() for n in (args.allow_table_margin or "").split(",") if n.strip()
    }

    slides: list[dict] = []
    if args.spec:
        pairs = [
            (sl, p)
            for sl, p in spec_slides_with_images(Path(args.spec).resolve())
            if p.suffix.lower() in RASTER_SUFFIXES
        ]
        images = [p for _, p in pairs]
        slides = [sl for sl, _ in pairs]
    else:
        images = sorted(
            path for path in asset_dir.iterdir()
            if path.is_file() and path.suffix.lower() in RASTER_SUFFIXES
        )
        pairs = [({}, p) for p in images]

    failures = []
    table_groups: dict[str, list[Path]] = {}

    for slide, image_path in pairs:
        if not image_path.exists():
            failures.append(f"missing image: {image_path}")
            continue

        sidecar = _read_sidecar(image_path)
        if args.require_postprocess and sidecar is None:
            failures.append(f"missing postprocess sidecar: {postprocess_meta_path(image_path)}")
        if sidecar is not None:
            failures.extend(validate_final_sidecar(image_path, sidecar))

        # Table safety-margin gate.
        if sidecar is not None and _looks_like_table(image_path, sidecar):
            cmd = sidecar.get("command")
            margin = sidecar.get("margin", sidecar.get("safety_margin_px"))
            documented = (
                image_path.name in allow_table_margin
                or _runmanifest_mentions(asset_dir, image_path.name)
            )
            if cmd in {"trim", "labels"} and (
                not isinstance(margin, int)
                or not TABLE_MARGIN_MIN <= margin <= TABLE_MARGIN_MAX
            ) and not documented:
                failures.append(
                    f"table asset {image_path.name} has {cmd} margin={margin!r}; "
                    f"expected {TABLE_MARGIN_MIN}-{TABLE_MARGIN_MAX}px and no "
                    f"documented exception was found"
                )

        # Multi-panel figure geometry gate (spec-driven only).
        if slide.get("type") == "figure":
            labels = slide.get("panel_labels") or []
            if len(labels) > 1 and not slide.get("panel_geometry_exception"):
                xf = slide.get("panel_label_x_fracs") or []
                boxes = slide.get("panel_boxes") or []
                if len(xf) < len(labels) and len(boxes) < len(labels):
                    failures.append(
                        f"figure {image_path.name} has {len(labels)} panel_labels "
                        f"but no panel geometry (panel_label_x_fracs/panel_boxes)"
                    )

            # One-figure-one-slide gate: a slide must not reference a raw panel crop.
            if _PANEL_FRAGMENT_RE.search(image_path.name):
                failures.append(
                    f"figure slide references a raw panel crop ({image_path.name}); "
                    f"recompose panels into a single image before adding to the spec"
                )

        group = table_split_group(image_path)
        if group:
            table_groups.setdefault(group, []).append(image_path)

    for group, paths in sorted(table_groups.items()):
        if len(paths) < 2:
            continue
        widths = {}
        for path in paths:
            with Image.open(path) as im:
                widths[path.name] = im.width
        if len(set(widths.values())) > 1:
            failures.append(f"table split widths differ for {group}: {widths}")

    # One-figure-one-slide gate: the same paper Figure number must not appear on
    # more than one figure slide. (Tables may legitimately split into 1A/1B, so
    # only Figure numbers are checked here.)
    fig_slides: dict[str, list[str]] = {}
    for slide, image_path in pairs:
        if slide.get("type") != "figure":
            continue
        blob = str(slide.get("caption", "")) + str(slide.get("title", ""))
        if re.search(r"\btable\b", blob, re.I):
            continue
        if slide.get("figure_slide_exception"):
            continue
        num = _figure_number_of(slide, image_path)
        if num:
            fig_slides.setdefault(num, []).append(image_path.name)
    for num, names in sorted(fig_slides.items()):
        if len(names) > 1:
            failures.append(
                f"paper Figure {num} appears on {len(names)} slides "
                f"({', '.join(names)}); each paper Figure must be one slide with "
                f"one recomposed image"
            )

    if failures:
        print("asset audit failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print(f"asset audit passed: {len(images)} image(s)")


_NOTE_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),  # symbols & pictographs, emoji, supplemental
    (0x2600, 0x27BF),    # misc symbols + dingbats (✅ ⚠ ➡ etc.)
    (0x2B00, 0x2BFF),    # arrows / stars
    (0x1F000, 0x1F0FF),
    (0xFE00, 0xFE0F),    # variation selectors
)
_NOTE_CJK_RE = CJK_RE
_NOTE_SIMPLIFIED_ONLY_RE = SIMPLIFIED_ONLY_RE
_MIN_NOTE_CJK = {
    "title": 12,
    "outline": 20,
    "part": 12,
    "content": 20,
    "figure": 20,
    "references": 16,
    "thanks": 12,
}


def _count_emoji(text: str) -> int:
    total = 0
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _NOTE_EMOJI_RANGES):
            total += 1
    return total


def _note_diversity_failure(text: str) -> str | None:
    return note_diversity_failure(text)


def _referenced_panel_letters(notes: str) -> set[str]:
    # Matches 【A 圖】, 【A: ...】, 【1：...】, and "panel A/1".
    import re as _re
    letters = set()
    for m in _re.finditer(r"【\s*([A-Za-z]|\d+)\s*(?:[圖图]|[:：])", notes):
        letters.add(m.group(1).upper())
    for m in _re.finditer(r"\bpanel\s*([A-Za-z]|\d+)\b", notes, _re.IGNORECASE):
        letters.add(m.group(1).upper())
    return letters


def _trim_to_content(im: "Image.Image", threshold: int, margin: int = 0) -> "Image.Image":
    box = content_bbox(im, threshold)
    box = expand_box(box, im.size, margin)
    return im.crop(box)


def _gutter_runs(whiteness, n_cuts: int, edge_skip_frac: float = 0.03,
                 white_line: float = 0.92):
    """Return up to n_cuts interior white-gutter runs as (start, end) ranges.

    A gutter is a band of lines that are overwhelmingly near-white. We keep the
    n_cuts widest interior runs (away from the outer edges), ordered by position.
    Returns [] when not enough gutters are found (caller falls back to even).
    """
    length = len(whiteness)
    edge = int(length * edge_skip_frac)
    runs = []
    i = edge
    while i < length - edge:
        if whiteness[i] >= white_line:
            j = i
            while j < length - edge and whiteness[j] >= white_line:
                j += 1
            runs.append((i, j))  # [start, end)
            i = j
        else:
            i += 1
    runs.sort(key=lambda r: (r[1] - r[0]), reverse=True)
    chosen = sorted(runs[:n_cuts], key=lambda r: r[0])
    return chosen if len(chosen) == n_cuts else []


def _axis_bounds(whiteness, n_cells: int, length: int):
    """Return per-cell (start, end) spans along one axis, EXCLUDING gutters."""
    gaps = _gutter_runs(whiteness, n_cells - 1)
    if not gaps:
        step = length / n_cells
        return [(int(step * k), int(step * (k + 1))) for k in range(n_cells)]
    bounds = [0]
    for s, e in gaps:
        bounds += [s, e]
    bounds += [length]
    starts = bounds[0::2]
    ends = bounds[1::2]
    return list(zip(starts, ends))


def _split_composite(im: "Image.Image", rows: int, cols: int, threshold: int):
    """Split a composite grid into rows*cols cells, EXCLUDING the white gutters.

    Cutting at gutter boundaries (not centres) means no part of the white
    separator line is left inside any panel, so panels show no inner white edge.
    """
    import numpy as _np
    arr = _np.asarray(im.convert("RGB")).astype("int16")
    near_white = (arr > threshold).all(axis=2)
    col_white = near_white.mean(axis=0)
    row_white = near_white.mean(axis=1)
    xspans = _axis_bounds(col_white, cols, im.width)
    yspans = _axis_bounds(row_white, rows, im.height)
    cells = []
    for r in range(rows):
        y0, y1 = yspans[r]
        for c in range(cols):
            x0, x1 = xspans[c]
            cells.append(im.crop((x0, y0, x1, y1)))
    return cells


def _edge_trim_white(im: "Image.Image", white_thr: int = 238, frac: float = 0.7,
                     light_thr: int = 222, light_frac: float = 0.92,
                     max_iter: int = 10000) -> "Image.Image":
    """Iteratively crop each of the 4 edges until no white/uniform-light strip remains.

    A border line is cropped if EITHER:
      - it is near-white: fraction of pixels (all channels >= white_thr) >= frac, OR
      - it is a uniform light line: fraction (all channels >= light_thr) >= light_frac.
    The second test removes thin light-grey separator/background lines that a
    pure-white test misses, while the high light_frac protects textured image
    content (e.g. CT bone+tissue edges, which are not uniformly light).
    Repeats per edge until all four sides reach real content.
    """
    import numpy as _np
    arr = _np.asarray(im.convert("RGB"))
    hi = (arr >= white_thr).all(axis=2)
    lt = (arr >= light_thr).all(axis=2)

    def white_line(idx_slice, axis_is_row, pos):
        if axis_is_row:
            a = hi[pos, idx_slice]; b = lt[pos, idx_slice]
        else:
            a = hi[idx_slice, pos]; b = lt[idx_slice, pos]
        return a.mean() >= frac or b.mean() >= light_frac

    h, w = hi.shape
    top, bottom, left, right = 0, h, 0, w
    changed = True
    it = 0
    while changed and it < max_iter and bottom - top > 2 and right - left > 2:
        changed = False
        it += 1
        if white_line(slice(left, right), True, top):
            top += 1; changed = True
        if bottom - 1 > top and white_line(slice(left, right), True, bottom - 1):
            bottom -= 1; changed = True
        if white_line(slice(top, bottom), False, left):
            left += 1; changed = True
        if right - 1 > left and white_line(slice(top, bottom), False, right - 1):
            right -= 1; changed = True
    return im.crop((left, top, right, bottom))


def _inset_panel(im: "Image.Image", px: int) -> "Image.Image":
    """Crop a panel inward by px on all sides as a final safety step."""
    if px <= 0:
        return im
    if im.width <= 2 * px or im.height <= 2 * px:
        return im
    return im.crop((px, px, im.width - px, im.height - px))


def _fit_into_cell(im: "Image.Image", cw: int, ch: int, mode: str, bg) -> "Image.Image":
    """Place a panel into a fixed cell (cw x ch) so cells form an aligned grid."""
    if mode == "stretch":
        return im.resize((cw, ch), Image.LANCZOS)
    s_fit = min(cw / im.width, ch / im.height)
    s_cov = max(cw / im.width, ch / im.height)
    if mode == "fill":
        nw, nh = max(1, round(im.width * s_cov)), max(1, round(im.height * s_cov))
        r = im.resize((nw, nh), Image.LANCZOS)
        left = (nw - cw) // 2
        top = (nh - ch) // 2
        return r.crop((left, top, left + cw, top + ch))
    nw, nh = max(1, round(im.width * s_fit)), max(1, round(im.height * s_fit))
    r = im.resize((nw, nh), Image.LANCZOS)
    cell = Image.new("RGB", (cw, ch), bg)
    cell.paste(r, ((cw - nw) // 2, (ch - nh) // 2))
    return cell


def _draw_panel_frame(im: "Image.Image", px: int, color) -> "Image.Image":
    """Overlay a px-wide frame in `color` around the panel, covering the
    outermost bright content edge so it does not touch the gap."""
    if px <= 0:
        return im
    im = im.copy()
    d = ImageDraw.Draw(im)
    for k in range(px):
        d.rectangle([k, k, im.width - 1 - k, im.height - 1 - k], outline=color)
    return im


def recompose_panels_command(args: argparse.Namespace) -> None:
    """Rebuild a multi-panel figure as an aligned grid with no white gutters.

    Pipeline per panel: trim to content (removes source-page white gutters) ->
    optional inward inset (`--inset`, kills the thin residual white edge) ->
    fit into a uniform cell (`--fit pad|fill|stretch`) so columns and rows line
    up and the figure reads as one complete, edge-aligned rectangle. Implements
    the SKILL rules 'remove source-page white gutters; rebuild with controlled
    uniform gaps' and 'panels evenly arranged, scaled to align all four edges'.

    For figures on a dark slide, pass --bg matching the slide background
    (e.g. --bg '#061428') so gaps do not appear as white lines.
    """
    output_path = Path(args.output)
    if args.composite:
        _assert_distinct_paths(Path(args.composite), output_path)
    for input_name in args.inputs:
        _assert_distinct_paths(Path(input_name), output_path)
    threshold = args.threshold
    if args.composite:
        if not (args.rows and args.cols):
            raise SystemExit("--composite requires --rows and --cols")
        comp = Image.open(args.composite).convert("RGB")
        panels = _split_composite(comp, args.rows, args.cols, threshold)
        cols = args.cols
    else:
        if not args.inputs:
            raise SystemExit("Provide panel images via --inputs or a --composite")
        panels = [Image.open(p).convert("RGB") for p in args.inputs]
        cols = args.cols or len(panels)

    # 1) bbox trim (remove source gutters / outer white)
    panels = [_trim_to_content(im, threshold, margin=0) for im in panels]
    # 2) iterative per-edge white trim: crop every edge until no white strip
    #    remains on any of the 4 sides (handles residual lines bbox trim keeps)
    panels = [_edge_trim_white(im, white_thr=args.edge_white_thr,
                               frac=args.edge_white_frac,
                               light_thr=args.edge_light_thr,
                               light_frac=args.edge_light_frac) for im in panels]
    # 3) optional extra inward inset as a final safety
    panels = [_inset_panel(im, args.inset) for im in panels]
    if not panels:
        raise SystemExit("No panels to recompose")

    import statistics as _stats
    rows = (len(panels) + cols - 1) // cols
    gap = args.gap
    margin = args.margin
    if margin != FINAL_RASTER_SAFETY_MARGIN_PX:
        raise SystemExit(
            f"Final recomposed figures require an exact "
            f"{FINAL_RASTER_SAFETY_MARGIN_PX}px safety margin; received {margin}."
        )

    # 3) uniform cell size -> aligned grid, all four outer edges flush
    cell_w = args.panel_width or int(round(_stats.median(im.width for im in panels)))
    cell_h = args.panel_height or int(round(_stats.median(im.height for im in panels)))
    cells = [_fit_into_cell(im, cell_w, cell_h, args.fit, args.bg) for im in panels]
    if args.panel_frame > 0:
        frame_color = args.panel_frame_color or args.bg
        cells = [_draw_panel_frame(im, args.panel_frame, frame_color) for im in cells]

    canvas_w = cols * cell_w + (cols - 1) * gap + 2 * margin
    canvas_h = rows * cell_h + (rows - 1) * gap + 2 * margin
    canvas = Image.new("RGB", (canvas_w, canvas_h), args.bg)

    boxes = []
    for idx, im in enumerate(cells):
        r, c = divmod(idx, cols)
        x = margin + c * (cell_w + gap)
        y = margin + r * (cell_h + gap)
        canvas.paste(im, (x, y))
        boxes.append({"index": idx, "row": r, "col": c,
                       "x": x, "y": y, "w": im.width, "h": im.height,
                       "right_x_frac": round((x + im.width) / canvas_w, 4)})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=95)
    padding_rgb = ImageColor.getrgb(args.bg)[:3]
    padding_hex = "#" + "".join(f"{channel:02X}" for channel in padding_rgb)
    write_postprocess_meta(
        Path(args.output), "recompose-panels",
        Path(args.composite) if args.composite else None,
        asset_type="figure",
        input_mode="composite" if args.composite else "inputs",
        source_inputs=[str(Path(path).expanduser().resolve()) for path in args.inputs]
        if args.inputs else [],
        panels=len(cells), rows=rows, cols=cols, gap=gap, margin=margin,
        safety_margin_px=margin, padding_background=padding_hex,
        unpadded_size_px=[canvas_w - 2 * margin, canvas_h - 2 * margin],
        padded_size_px=[canvas_w, canvas_h],
        threshold=args.threshold,
        panel_width=args.panel_width,
        panel_height=args.panel_height,
        edge_white_thr=args.edge_white_thr,
        edge_white_frac=args.edge_white_frac,
        edge_light_thr=args.edge_light_thr,
        edge_light_frac=args.edge_light_frac,
        inset=args.inset, fit=args.fit, cell_w=cell_w, cell_h=cell_h,
        bg=args.bg, panel_frame=args.panel_frame,
        panel_frame_color=(args.panel_frame_color or args.bg), panel_boxes=boxes,
    )
    print(f"wrote {args.output} ({canvas.width}x{canvas.height}); "
          f"{len(cells)} panels, {rows}x{cols}, cell={cell_w}x{cell_h}, "
          f"fit={args.fit}, inset={args.inset}, gap={gap}px")


def vector_table_command(args: argparse.Namespace) -> None:
    """Render a table region from the PDF as a VECTOR EMF (no rasterisation).

    PDF table text is vector; this keeps it vector all the way into PowerPoint so
    it stays razor-sharp at any zoom (true original quality). Pipeline:
    PDF clip -> SVG (PyMuPDF) -> EMF (LibreOffice). Prints the aspect ratio to
    put in the deck spec as 'image_aspect'; build_deck places the EMF on a white
    card on the dark slide.
    """
    import vector_table

    try:
        bbox = [float(value) for value in args.bbox.split(",")]
        if len(bbox) != 4:
            raise ValueError
    except ValueError as error:
        raise SystemExit("--bbox must contain exactly x0,y0,x1,y1") from error
    out = Path(args.output).expanduser().resolve()
    try:
        metadata = vector_table.generate_vector_table(
            Path(args.pdf),
            out,
            page=args.page,
            requested_bbox=bbox,
            pad_x=args.pad_x,
            pad_top=args.pad_top,
            pad_bottom=args.pad_bottom,
            soffice=args.soffice,
        )
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    aspect = metadata["image_aspect"]
    print(f"wrote {out} (vector EMF); image_aspect={aspect:.8f}")
    print(f'spec: "image": "{out.name}", "image_aspect": {aspect:.8f}')


def notes_audit_command(args: argparse.Namespace) -> None:
    spec_path = Path(args.spec).expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not isinstance(spec.get("slides"), list):
        raise SystemExit("notes specification must be an object containing a slides list")
    slides = spec["slides"]
    failures = []
    warnings = []

    notes_slides = 0
    total_emoji = 0
    note_entries: list[tuple[int, str]] = []
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            failures.append(f"slide {idx} must be an object")
            continue
        raw_notes = slide.get("notes")
        if not isinstance(raw_notes, str):
            failures.append(f"slide {idx} ({slide.get('type')}) notes must be a string")
            continue
        notes = raw_notes
        if not notes.strip():
            failures.append(f"slide {idx} ({slide.get('type')}) has no notes")
            continue
        note_entries.append((idx, notes))
        notes_slides += 1
        emoji_count = _count_emoji(notes)
        total_emoji += emoji_count
        slide_type = str(slide.get("type", ""))
        cjk_count = len(_NOTE_CJK_RE.findall(notes))
        minimum = _MIN_NOTE_CJK.get(slide_type, 12)
        if cjk_count < minimum:
            failures.append(
                f"slide {idx} ({slide_type}) notes are not substantive: "
                f"{cjk_count} CJK characters; at least {minimum} required"
            )
        if diversity_failure := _note_diversity_failure(notes):
            failures.append(f"slide {idx} notes contain {diversity_failure}")
        if _NOTE_SIMPLIFIED_ONLY_RE.search(notes):
            failures.append(f"slide {idx} notes contain Simplified-Chinese-only forms")
        if emoji_count == 0:
            failures.append(f"slide {idx} notes contain no structural emoji marker")
        if slide_type == "content" and not has_closing_takeaway(notes):
            failures.append(f"slide {idx} content notes need a closing takeaway marker")

        if "**" in notes:
            warnings.append(
                f"slide {idx}: notes contain literal '**' markup "
                f"(builder converts these to bold, but check source)"
            )

        # Figure/table panel-mention check.
        if slide.get("type") == "figure":
            labels = {str(l).strip().upper() for l in (slide.get("panel_labels") or []) if str(l).strip()}
            image_value = slide.get("image")
            if isinstance(image_value, str) and image_value.strip():
                image_path = Path(image_value).expanduser()
                if not image_path.is_absolute():
                    image_path = spec_path.parent / image_path
                sidecar = _read_sidecar(image_path.resolve()) or {}
                for key in ("labels", "embedded_labels", "native_label_values"):
                    value = sidecar.get(key)
                    if isinstance(value, list):
                        labels.update(str(item).strip().upper() for item in value if str(item).strip())
            referenced = _referenced_panel_letters(notes)
            ghost = referenced - labels
            missing = labels - referenced
            if ghost:
                failures.append(
                    f"slide {idx}: notes reference panel(s) "
                    f"{sorted(ghost)} not present in visible label metadata {sorted(labels)}"
                )
            if missing:
                failures.append(
                    f"slide {idx}: notes do not describe visible panel(s) {sorted(missing)}"
                )

    failures.extend(duplicate_note_failures(note_entries))

    for w in warnings:
        print(f"warning: {w}")

    if failures:
        print("notes audit failed:")
        for f in failures:
            print(f"- {f}")
        raise SystemExit(1)

    print(
        f"notes audit passed: {notes_slides}/{len(slides)} slides with notes, "
        f"{total_emoji} note emoji"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    trim = sub.add_parser("trim")
    trim.add_argument("input")
    trim.add_argument("output")
    trim.add_argument("--margin", type=int, default=None,
                      help="Exact post-trim safety margin in px. Default 16 for "
                           "final figures/tables and 0 for intermediate crops.")
    trim.add_argument("--asset-type", choices=["figure", "table", "flowchart", "unknown"],
                      default="figure",
                      help="Asset class. 'table' enforces an 8-24px safety margin.")
    trim.add_argument("--intermediate", action="store_true",
                      help="Mark output as a non-final intermediate crop "
                           "(skips the table safety-margin requirement).")
    trim.add_argument("--threshold", type=int, default=246)
    trim.add_argument("--cut-bottom-px", type=int, default=0)
    trim.add_argument("--bg-aware", choices=["auto", "on", "off"], default="auto",
                      help="Background-aware edge refinement layered on top of "
                           "the baseline white-based crop. 'auto' (default): apply "
                           "only when the real background is not pure white "
                           "(grey page / dark canvas with a residual hairline); "
                           "'on': always; 'off': baseline white-only behaviour.")
    trim.add_argument("--bg-tol", type=int, default=26,
                      help="Per-channel tolerance for matching the detected "
                           "background colour (default 26).")
    trim.set_defaults(func=trim_command)

    labels = sub.add_parser("labels")
    labels.add_argument("input")
    labels.add_argument("output")
    labels.add_argument("--labels", required=True, help="Comma-separated labels, e.g. A,B,C,D")
    labels.add_argument("--margin", type=int, default=None,
                        help="Exact post-trim safety margin in px. Default 16 for "
                             "final figures/tables and 0 for intermediate crops.")
    labels.add_argument("--asset-type", choices=["figure", "table", "flowchart", "unknown"],
                        default="figure")
    labels.add_argument("--intermediate", action="store_true")
    labels.add_argument("--threshold", type=int, default=246)
    labels.add_argument("--cut-bottom-px", type=int, default=0)
    labels.add_argument("--bg-aware", choices=["auto", "on", "off"], default="auto",
                        help="Background-aware edge refinement (see `trim`).")
    labels.add_argument("--bg-tol", type=int, default=26,
                        help="Per-channel background match tolerance (default 26).")
    labels.set_defaults(func=labels_command)

    micro = sub.add_parser("microcrop")
    micro.add_argument("input")
    micro.add_argument("output")
    micro.add_argument("--px", type=int, default=2)
    micro.set_defaults(func=microcrop_command)

    same = sub.add_parser("same-width")
    same.add_argument("out_dir")
    same.add_argument("inputs", nargs="+")
    same.set_defaults(func=same_width_command)

    recompose = sub.add_parser(
        "recompose-panels",
        help="Rebuild a multi-panel figure with source gutters removed and "
             "uniform gaps.")
    recompose.add_argument("output")
    recompose.add_argument("--inputs", nargs="+", default=[],
                           help="Individual panel images, in reading order.")
    recompose.add_argument("--composite",
                           help="A single composite grid image to auto-split "
                                "(requires --rows and --cols).")
    recompose.add_argument("--rows", type=int, default=0,
                           help="Grid rows (for --composite auto-split).")
    recompose.add_argument("--cols", type=int, default=0,
                           help="Grid columns. Defaults to #panels when using "
                                "--inputs.")
    recompose.add_argument("--gap", type=int, default=18,
                           help="Uniform gap in px between panels (default 18).")
    recompose.add_argument("--margin", type=int, default=FINAL_RASTER_SAFETY_MARGIN_PX,
                           help="Outer safety margin in px around the grid "
                                "(default 16).")
    recompose.add_argument("--panel-height", type=int, default=0,
                           help="Force the uniform cell height in px; default is "
                                "the median trimmed panel height.")
    recompose.add_argument("--panel-width", type=int, default=0,
                           help="Force the uniform cell width in px; default is "
                                "the median trimmed panel width.")
    recompose.add_argument("--inset", type=int, default=0,
                           help="Extra inward crop per panel in px AFTER the "
                                "iterative edge-white trim (usually 0 now).")
    recompose.add_argument("--edge-white-thr", type=int, default=238,
                           help="A pixel counts as white when all channels >= "
                                "this value (default 238).")
    recompose.add_argument("--edge-white-frac", type=float, default=0.7,
                           help="Crop a border line while this fraction of it is "
                                "near-white (default 0.7). Lower = more aggressive.")
    recompose.add_argument("--edge-light-thr", type=int, default=222,
                           help="Light-grey threshold for the uniform-line edge "
                                "test (default 222).")
    recompose.add_argument("--edge-light-frac", type=float, default=0.92,
                           help="Crop a border line when this fraction is uniform "
                                "light-grey (default 0.92); high value protects "
                                "textured image content.")
    recompose.add_argument("--fit", choices=["pad", "fill", "stretch"],
                           default="fill",
                           help="How each panel fills its uniform grid cell: "
                                "fill (cover+centre-crop, edges flush; default), "
                                "pad (letterbox on bg), stretch (exact cell).")
    recompose.add_argument("--panel-frame", type=int, default=0,
                           help="Draw a frame of this width (px) around each "
                                "panel, covering the outermost bright content "
                                "edge (e.g. 2-3). 0 = off.")
    recompose.add_argument("--panel-frame-color", default="",
                           help="Frame colour (default = --bg, so it merges with "
                                "the gaps and panels look uniformly inset).")
    recompose.add_argument("--bg", default="white",
                           help="Gap/background fill color (default white).")
    recompose.add_argument("--threshold", type=int, default=246)
    recompose.set_defaults(func=recompose_panels_command)

    split = sub.add_parser("split-table")
    split.add_argument("input")
    split.add_argument("out_a")
    split.add_argument("out_b")
    split.add_argument("--split-y", type=int, required=True)
    split.add_argument("--repeat-header-y", type=int, required=True)
    split.add_argument("--crop-left", type=int, default=0)
    split.add_argument("--crop-top", type=int, default=0)
    split.add_argument("--crop-right", type=int, default=0)
    split.add_argument("--crop-bottom", type=int, default=0)
    split.add_argument("--margin", type=int, default=TABLE_SAFETY_MARGIN_PX,
                       help="Exact outer white safety margin on each output "
                            "part (default 16).")
    split.add_argument("--threshold", type=int, default=246)
    split.set_defaults(func=split_table_command)

    audit = sub.add_parser("audit-final")
    audit.add_argument("asset_dir")
    audit.add_argument("--spec")
    audit.add_argument("--require-postprocess", dest="require_postprocess",
                       action="store_true", default=True)
    audit.add_argument("--no-require-postprocess", dest="require_postprocess",
                       action="store_false",
                       help="Do not fail on missing postprocess sidecars.")
    audit.add_argument("--allow-table-margin", default="",
                       help="Comma-separated table asset filenames exempt from "
                            "the safety-margin gate (documented exceptions).")
    audit.set_defaults(func=audit_command)

    vt = sub.add_parser("vector-table",
                        help="Render a PDF table region as a vector EMF (no "
                             "rasterisation; razor-sharp at any zoom).")
    vt.add_argument("pdf")
    vt.add_argument("output", help="Output .emf path")
    vt.add_argument("--page", type=int, required=True, help="1-based page number")
    vt.add_argument("--bbox", required=True, help="x0,y0,x1,y1 in PDF points")
    vt.add_argument("--pad-x", type=float, default=15.0)
    vt.add_argument("--pad-top", type=float, default=6.0)
    vt.add_argument("--pad-bottom", type=float, default=10.0)
    vt.add_argument("--soffice", default="soffice", help="LibreOffice binary")
    vt.set_defaults(func=vector_table_command)

    notes = sub.add_parser("notes-audit")
    notes.add_argument("--spec", required=True, help="Deck spec JSON to audit.")
    notes.add_argument("--require-all-notes", action="store_true",
                       help="Also fail if any slide is missing notes.")
    notes.set_defaults(func=notes_audit_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
