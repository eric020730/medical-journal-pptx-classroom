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
  --asset-type        figure (16 px safety canvas) or clinical-image (0 px)
  --safety-margin-px  exact outer canvas margin in px; validated by asset type
  --source-label-policy  auto, preserve, or crop-safe-margin
  --max-edge-px       maximum removable white/gray rim depth per side (default 4)
                      A panel-crop sidecar may declare a separately verified
                      per-edge trim of up to 12px; it is applied before this
                      bounded heuristic and must include an audit reason.
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
import argparse, hashlib, json, os
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor


EDGE_SIDES = ("top", "bottom", "left", "right")
VERIFIED_EDGE_TRIM_MAX_PX = 12
VERIFIED_EDGE_TRIM_REASONS = {
    "verified-pdf-exterior-band",
    "verified-image-box-correction",
    "manual-visual-review",
}


def source_metadata(path):
    """Read optional panel annotations without weakening source-sidecar QA."""
    sidecar = Path(str(path) + ".postprocess.json")
    if not sidecar.is_file():
        return {}
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(metadata, dict):
        return {}
    metadata = dict(metadata)
    metadata["_sidecar_dir"] = str(sidecar.expanduser().resolve().parent)
    return metadata


def resolved_source_path(metadata):
    """Resolve a sidecar source relative to that sidecar, never process CWD."""
    source = metadata.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    path = Path(source).expanduser()
    if not path.is_absolute():
        base = Path(metadata.get("_sidecar_dir") or ".")
        path = base / path
    return path.resolve(strict=False)


def normalized_box(value):
    """Return a numeric four-value box, or None for incomplete metadata."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    return box if box[0] < box[2] and box[1] < box[3] else None


def box_relationship(label_box, image_box):
    """Classify a label against image content, tolerating PDF glyph overshoot.

    PDF text boxes can intrude a fraction of a point into the adjacent raster
    even when the visible letter is printed in the exterior margin. Treat the
    label as embedded only when its center is inside the image or at least 15%
    of its bounding-box area overlaps image content.
    """
    label_box = normalized_box(label_box)
    image_box = normalized_box(image_box)
    if label_box is None or image_box is None:
        return None, None
    lx0, ly0, lx1, ly1 = label_box
    ix0, iy0, ix1, iy1 = image_box
    overlap_w = max(0.0, min(lx1, ix1) - max(lx0, ix0))
    overlap_h = max(0.0, min(ly1, iy1) - max(ly0, iy0))
    overlap_fraction = overlap_w * overlap_h / ((lx1 - lx0) * (ly1 - ly0))
    center_x, center_y = (lx0 + lx1) / 2.0, (ly0 + ly1) / 2.0
    center_inside = ix0 <= center_x <= ix1 and iy0 <= center_y <= iy1
    placement = "embedded" if center_inside or overlap_fraction >= 0.15 else "external-margin"
    return placement, overlap_fraction


def project_box(box, crop_box, image_size):
    """Project a PDF/source-space box into the current panel's pixel space."""
    box = normalized_box(box)
    crop_box = normalized_box(crop_box)
    if box is None or crop_box is None:
        return None
    cx0, cy0, cx1, cy1 = crop_box
    width, height = image_size
    return [
        int(round((box[0] - cx0) * width / (cx1 - cx0))),
        int(round((box[1] - cy0) * height / (cy1 - cy0))),
        int(round((box[2] - cx0) * width / (cx1 - cx0))),
        int(round((box[3] - cy0) * height / (cy1 - cy0))),
    ]


def label_details(metadata, image):
    """Resolve placement from geometry instead of trusting a stale label flag."""
    nested = metadata.get("source_panel_label")
    nested = nested if isinstance(nested, dict) else {}
    status = str(nested.get("status") or "").strip().lower().replace("_", "-")
    declared = str(
        nested.get("placement")
        or metadata.get("source_label_placement")
        or metadata.get("label_placement")
        or ("embedded" if metadata.get("embedded_label") else "")
    ).strip().lower().replace("_", "-")
    if status == "verified-absent":
        declared = "absent"
    box = (
        nested.get("box_px")
        or nested.get("bbox")
        or metadata.get("source_label_box_px")
        or metadata.get("label_box_px")
    )
    box = normalized_box(box)

    geometry_space = ""
    placement = ""
    overlap_fraction = None
    local_image_box = (
        nested.get("image_box_px")
        or metadata.get("source_image_content_box_px")
        or metadata.get("image_content_box_px")
    )
    image_box = normalized_box(local_image_box)
    if box is not None and image_box is not None:
        placement, overlap_fraction = box_relationship(box, image_box)
        geometry_space = "panel-px"
    else:
        source_label_box = nested.get("box_pt") or metadata.get("source_label_bbox_pt")
        source_image_box = nested.get("image_box_pt") or metadata.get("source_image_bbox_pt")
        placement, overlap_fraction = box_relationship(source_label_box, source_image_box)
        if placement:
            geometry_space = "source-pt"
            crop_box = nested.get("crop_box_pt") or metadata.get("source_crop_bbox_pt")
            if box is None:
                box = normalized_box(project_box(source_label_box, crop_box, image.size))
            if image_box is None:
                image_box = normalized_box(project_box(source_image_box, crop_box, image.size))

    absence_claim_invalid = False
    if not placement and declared == "absent":
        evidence = nested.get("absence_evidence")
        expected_review_box = [0, 0, image.width, image.height]
        expected_hash = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
        evidence_valid = (
            status == "verified-absent"
            and nested.get("verified_absent") is True
            and box is None
            and image_box is None
            and isinstance(evidence, dict)
            and evidence.get("method") == "full-panel-decoded-rgb-review-v1"
            and evidence.get("review_box_px") == expected_review_box
            and evidence.get("decoded_rgb_sha256") == expected_hash
        )
        if evidence_valid:
            placement = "absent"
            geometry_space = "verified-full-panel-review"
        else:
            placement = ""
            absence_claim_invalid = True
    elif not placement:
        placement = declared
    return {
        "placement": placement,
        "box": list(box) if box is not None else None,
        "image_box": list(image_box) if image_box is not None else None,
        "declared_placement": declared,
        "geometry_space": geometry_space,
        "overlap_fraction": overlap_fraction,
        "absence_claim_invalid": absence_claim_invalid,
    }


def overwritten_source_pixels(image, metadata):
    """Catch solid corner masks when a panel claims to be an exact source crop."""
    source = resolved_source_path(metadata)
    box = metadata.get("crop_box_px")
    if source is None or not isinstance(box, (list, tuple)) or len(box) != 4:
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


def is_disposable_rim(line, inner_line=None, allow_gray_plateau=True):
    """Classify a thin achromatic seam without consuming dark image canvas.

    PDF image-object renders often add one full-edge white or mid-gray column
    before a long, uniform mammography background.  Dark canvas must stop the
    trim sequence; otherwise the bounded safety check sees more than its
    inspection budget and conservatively leaves the true outer seam in place.
    """
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

    # A non-white gray line is removable only when it is both flat and clearly
    # brighter than the next line inward. Uniform gray MRI background is common
    # at an image edge; treating flatness alone as whitespace caused a genuine
    # clinical region after a 2px white seam to exhaust the 4px budget, which in
    # turn preserved the white seam. The one-way contrast test still removes
    # gray/antialiased rims and preserves dark frames facing brighter anatomy.
    if inner_line is None:
        return False
    inner = inner_line.astype(np.int16)
    inner_saturation = inner.max(axis=1) - inner.min(axis=1)
    if float(np.mean(inner_saturation > 24)) > 0.20:
        return False
    flat_gray = (
        dominant_fraction >= 0.50 and dominant_luminance >= 40
    ) or (
        float(luminance.std()) <= 32 and float(luminance.mean()) >= 40
    )
    contrast = float(luminance.mean() - inner.mean(axis=1).mean())
    gray_plateau = (
        allow_gray_plateau
        and float(luminance.mean()) >= 70
        and abs(contrast) <= 4
    )
    return flat_gray and (contrast >= 32 or gray_plateau)


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
        first = edge_line(pixels, side, 0).astype(np.int16)
        starts_near_white = float(np.mean(first.min(axis=1) >= 210)) >= 0.70
        while removable <= depth_limit and is_disposable_rim(
            edge_line(pixels, side, removable),
            edge_line(pixels, side, removable + 1),
            allow_gray_plateau=not starts_near_white,
        ):
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


def apply_verified_edge_trim(image, metadata, label_mode):
    """Apply an explicitly authenticated per-edge crop before heuristics.

    The declaration is created by ``postprocess_assets panel-crop`` and is
    interpreted in the panel raster remaining after any verified image-box /
    exterior-label crop. It is intentionally unavailable for panels whose
    source label remains embedded because a manual edge crop could remove that
    label or nearby clinical pixels.
    """
    raw = metadata.get("verified_edge_trim_px")
    empty = {side: 0 for side in EDGE_SIDES}
    if raw is None:
        return image, empty, ""
    if not isinstance(raw, dict) or any(side not in EDGE_SIDES for side in raw):
        raise ValueError("verified_edge_trim_px must contain only top/bottom/left/right")
    trim_px = {}
    for side in EDGE_SIDES:
        value = raw.get(side, 0)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= VERIFIED_EDGE_TRIM_MAX_PX
        ):
            raise ValueError(
                f"verified {side} edge trim must be an integer between 0 and "
                f"{VERIFIED_EDGE_TRIM_MAX_PX}"
            )
        trim_px[side] = value
    if not any(trim_px.values()):
        raise ValueError("verified_edge_trim_px must remove at least one pixel")
    reason = metadata.get("verified_edge_trim_reason")
    if reason not in VERIFIED_EDGE_TRIM_REASONS:
        raise ValueError(
            "verified_edge_trim_reason must be one of: "
            + ", ".join(sorted(VERIFIED_EDGE_TRIM_REASONS))
        )
    if label_mode == "preserved":
        raise ValueError("verified edge trim is not allowed while a source panel label is preserved")
    width, height = image.size
    if trim_px["left"] + trim_px["right"] >= width:
        raise ValueError("verified horizontal edge trims consume the complete panel")
    if trim_px["top"] + trim_px["bottom"] >= height:
        raise ValueError("verified vertical edge trims consume the complete panel")
    return image.crop((
        trim_px["left"],
        trim_px["top"],
        width - trim_px["right"],
        height - trim_px["bottom"],
    )), trim_px, reason


def residual_edge_review(image, max_edge_px=4, review_max_px=VERIFIED_EDGE_TRIM_MAX_PX):
    """Report a narrow full-edge white band that the hard cap preserved.

    Broad white-background panels remain unflagged: a candidate must terminate
    in a distinctly darker inward line within the independent review budget.
    The result is metadata for QA review, not permission to crop pixels.
    """
    pixels = np.asarray(image.convert("RGB"))
    height, width = pixels.shape[:2]
    candidates = {}
    for side in EDGE_SIDES:
        dimension = height if side in ("top", "bottom") else width
        limit = min(review_max_px, dimension - 2)
        if limit <= max_edge_px:
            continue
        depth = 0
        band_luminance = []
        while depth <= limit:
            line = edge_line(pixels, side, depth).astype(np.int16)
            near_white = float(np.mean(line.min(axis=1) >= 210))
            if near_white < 0.98:
                break
            band_luminance.append(float(line.mean()))
            depth += 1
        if not max_edge_px < depth <= limit:
            continue
        inner = edge_line(pixels, side, depth).astype(np.int16)
        inner_near_white = float(np.mean(inner.min(axis=1) >= 210))
        inner_luminance = float(inner.mean())
        contrast = float(np.mean(band_luminance) - inner_luminance)
        if inner_near_white >= 0.70 or contrast < 20:
            continue
        candidates[side] = {
            "depth_px": depth,
            "max_edge_px": max_edge_px,
            "review_max_px": review_max_px,
            "band_luminance": round(float(np.mean(band_luminance)), 3),
            "inner_luminance": round(inner_luminance, 3),
            "contrast": round(contrast, 3),
            "reason": "full-edge-near-white-band-exceeds-default-limit",
        }
    return {
        "status": "needs-review" if candidates else "clear",
        "candidates": candidates,
    }


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
        placement = label_details(entry, image)["placement"]
        if placement not in {"embedded", "overlay", "overlap"}:
            continue
        source = resolved_source_path(entry)
        box = entry.get("crop_box_px")
        if source is None or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            resolved = str(source.resolve(strict=True))
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
            source_path = resolved_source_path(metadata[index])
            if source_path is None:
                continue
            source = str(source_path)
            repaired[index] = sources[source].crop(tuple(boxes[index]))
    return repaired, decisions


def crop_safe_label_margin(image, box, image_box=None):
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

    content = normalized_box(image_box)
    if content is not None:
        ix0, iy0, ix1, iy1 = (int(round(value)) for value in content)
        if not (0 <= ix0 < ix1 <= width and 0 <= iy0 < iy1 <= height):
            return None
        center_x, center_y = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        exterior_sides = {}
        if center_x < ix0:
            exterior_sides["left"] = ix0 - center_x
        if center_x > ix1:
            exterior_sides["right"] = center_x - ix1
        if center_y < iy0:
            exterior_sides["top"] = iy0 - center_y
        if center_y > iy1:
            exterior_sides["bottom"] = center_y - iy1
        if not exterior_sides:
            return None
        side = min(exterior_sides, key=exterior_sides.get)
    else:
        sides = {
            "left": x0 / width,
            "right": (width - x1) / width,
            "top": y0 / height,
            "bottom": (height - y1) / height,
        }
        side = min(sides, key=sides.get)
    pad = 2
    if side == "bottom":
        boundary = iy1 if content is not None else max(0, y0 - pad)
        region = (0, boundary, width, height)
        retained = (0, 0, width, boundary)
    elif side == "top":
        boundary = iy0 if content is not None else min(height, y1 + pad)
        region = (0, 0, width, boundary)
        retained = (0, boundary, width, height)
    elif side == "right":
        boundary = ix1 if content is not None else max(0, x0 - pad)
        region = (boundary, 0, width, height)
        retained = (0, 0, boundary, height)
    else:
        boundary = ix0 if content is not None else min(width, x1 + pad)
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
    # Once the documented label box is excluded, the removable exterior band
    # must be effectively flat.  The older 98.5% rule could discard a narrow
    # colour scale or clinical overlay occupying only ~1% of the band.
    if uniform_fraction < 0.999:
        return None
    decision = {"side": side, "pixels": band_depth}
    if content is not None:
        # An extractor-provided image box is stronger evidence than an edge
        # luminance heuristic: it identifies the exact embedded raster inside
        # a PDF-rendered crop. Remove that verified exterior frame first, then
        # let clean_panel_edges inspect only the raster's bounded antialiased
        # rim. Otherwise a 3px page frame plus a 2px raster hairline becomes a
        # 5px bright band, exceeds the 4px heuristic cap, and remains intact.
        decision["verified_image_box_crop_px"] = {
            "top": iy0,
            "bottom": height - iy1,
            "left": ix0,
            "right": width - ix1,
        }
        return image.crop((ix0, iy0, ix1, iy1)), decision
    return image.crop(retained), decision


def resolve_source_labels(images, metadata, requested_policy):
    """Resolve each panel independently, preserving only labels on image content."""
    details = [label_details(entry, image) for entry, image in zip(metadata, images)]
    if requested_policy == "preserve":
        return images, "preserve", [{} for _ in images], ["preserved"] * len(images), details

    cleaned = list(images)
    decisions = [{} for _ in images]
    modes = []
    for index, detail in enumerate(details):
        placement = detail["placement"]
        if detail.get("absence_claim_invalid"):
            raise ValueError(
                "verified-absent source labels require untampered full-panel review evidence"
            )
        if placement in {"embedded", "overlay", "overlap"}:
            if requested_policy == "crop-safe-margin":
                raise ValueError("embedded image labels cannot be safely cropped from an exterior margin")
            modes.append("preserved")
            continue
        if placement in {"external-margin", "exterior-margin", "margin"}:
            result = crop_safe_label_margin(
                cleaned[index], detail["box"], detail.get("image_box")
            )
            if result is None:
                if requested_policy == "crop-safe-margin":
                    raise ValueError("source-label margin contains image content or lacks a verified label box")
                modes.append("preserved")
                continue
            cleaned[index], decisions[index] = result
            modes.append("native")
            continue
        if placement == "absent":
            modes.append("native")
            continue
        if requested_policy == "crop-safe-margin":
            raise ValueError("crop-safe-margin requires an exterior-margin placement and label box for every panel")
        # Missing/unknown metadata is ambiguous: a visible source label may be
        # embedded in image pixels. AUTO therefore preserves it and emits no
        # native duplicate. Explicit crop-safe-margin still fails above.
        modes.append("preserved")

    has_native = "native" in modes
    has_preserved = "preserved" in modes
    if has_native and has_preserved:
        policy = "mixed"
    elif has_preserved:
        policy = "preserve"
    elif any(decisions):
        policy = "crop-safe-margin"
    else:
        policy = "native"
    return cleaned, policy, decisions, modes, details


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
        scaled_row = [
            (max(1, int(width * scale)), max(1, int(height * scale)))
            for width, height in row
        ]
        # Absorb integer rounding in the final panel so a nominal 0 px clinical
        # canvas cannot expose a one-pixel background strip at the right edge.
        correction = target_width - (
            sum(width for width, _ in scaled_row) + gutter * (len(scaled_row) - 1)
        )
        scaled_row[-1] = (
            max(1, scaled_row[-1][0] + correction), scaled_row[-1][1]
        )
        final_rows.append(scaled_row)

    row_heights = [max(height for _, height in row) for row in final_rows]
    total_height = sum(row_heights) + band * len(final_rows)
    return target_width, total_height, final_rows, row_heights, gutter


def layout(panels, cols, band, bg, gap, safety_margin_px):
    """Compose a grid and return right/bottom anchors in source reading order."""
    target_width, total_height, final_rows, row_heights, gutter = layout_dimensions(
        panels, cols, band, gap
    )
    canvas = Image.new(
        "RGB",
        (target_width + 2 * safety_margin_px, total_height + 2 * safety_margin_px),
        bg,
    )
    rects = []; y = safety_margin_px
    panel_index = 0
    for row_index, row in enumerate(final_rows):
        x = safety_margin_px
        for width, height in row:
            panel = panels[panel_index].resize((width, height), Image.LANCZOS)
            canvas.paste(panel, (x, y))
            rects.append({"x": x, "y": y, "w": width, "h": height})
            x += width + gutter
            panel_index += 1
        y += row_heights[row_index] + band
    return canvas, rects


def left_span_2x2_dimensions(panels, gap):
    """Return a deterministic five-panel layout with panel 1 spanning two rows."""
    if len(panels) != 5:
        raise ValueError("left-span-2x2 requires exactly five panels")
    gutter = max(8, int(gap))
    row_sizes = []
    for row in (panels[1:3], panels[3:5]):
        row_height = min(panel.height for panel in row)
        sizes = [
            (max(1, int(round(panel.width * row_height / panel.height))), row_height)
            for panel in row
        ]
        row_sizes.append(sizes)
    target_right_width = max(
        sum(width for width, _ in row) + gutter for row in row_sizes
    )
    normalized_rows = []
    for row in row_sizes:
        current_width = sum(width for width, _ in row) + gutter
        scale = target_right_width / current_width
        normalized_rows.append([
            (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
            for width, height in row
        ])
    # Absorb rounding in each row's second panel so both rows share one edge.
    for row in normalized_rows:
        row[1] = (max(1, target_right_width - gutter - row[0][0]), row[1][1])
    top_height = max(height for _, height in normalized_rows[0])
    bottom_height = max(height for _, height in normalized_rows[1])
    total_height = top_height + gutter + bottom_height
    left_width = max(1, int(round(panels[0].width * total_height / panels[0].height)))
    total_width = left_width + gutter + target_right_width
    rects = [
        {"x": 0, "y": 0, "w": left_width, "h": total_height},
        {"x": left_width + gutter, "y": 0,
         "w": normalized_rows[0][0][0], "h": normalized_rows[0][0][1]},
        {"x": left_width + gutter + normalized_rows[0][0][0] + gutter, "y": 0,
         "w": normalized_rows[0][1][0], "h": normalized_rows[0][1][1]},
        {"x": left_width + gutter, "y": top_height + gutter,
         "w": normalized_rows[1][0][0], "h": normalized_rows[1][0][1]},
        {"x": left_width + gutter + normalized_rows[1][0][0] + gutter,
         "y": top_height + gutter,
         "w": normalized_rows[1][1][0], "h": normalized_rows[1][1][1]},
    ]
    return total_width, total_height, rects, gutter


def layout_left_span_2x2(panels, bg, gap, safety_margin_px):
    width, height, base_rects, _ = left_span_2x2_dimensions(panels, gap)
    canvas = Image.new(
        "RGB", (width + 2 * safety_margin_px, height + 2 * safety_margin_px), bg
    )
    rects = []
    for panel, base in zip(panels, base_rects):
        rect = {
            "x": base["x"] + safety_margin_px,
            "y": base["y"] + safety_margin_px,
            "w": base["w"],
            "h": base["h"],
        }
        canvas.paste(panel.resize((rect["w"], rect["h"]), Image.LANCZOS),
                     (rect["x"], rect["y"]))
        rects.append(rect)
    return canvas, rects


def evaluate_left_span_2x2(
    panels, box_width_in, box_height_in, gap, safety_margin_px
):
    width, height, rects, gutter = left_span_2x2_dimensions(panels, gap)
    padded_width = width + 2 * safety_margin_px
    padded_height = height + 2 * safety_margin_px
    fit = min(box_width_in / padded_width, box_height_in / padded_height)
    displayed = [(rect["w"] * fit, rect["h"] * fit) for rect in rects]
    areas = [panel_width * panel_height for panel_width, panel_height in displayed]
    short_edges = [min(panel_width, panel_height) for panel_width, panel_height in displayed]
    return {
        "cols": 3,
        "rows": 2,
        "band_px": 0,
        "gutter_px": gutter,
        "composite_width_px": padded_width,
        "composite_height_px": padded_height,
        "unpadded_width_px": width,
        "unpadded_height_px": height,
        "safety_margin_px": safety_margin_px,
        "fit_in_per_px": fit,
        "min_panel_area_sq_in": min(areas),
        "min_panel_short_edge_in": min(short_edges),
        "total_panel_area_sq_in": sum(areas),
        "utilization_fraction": sum(areas) / (box_width_in * box_height_in),
        "empty_cells": 0,
        "displayed_panel_sizes_in": [
            {"width": panel_width, "height": panel_height}
            for panel_width, panel_height in displayed
        ],
        "layout_template": "left-span-2x2",
    }


def right_span_2x2_dimensions(panels, gap):
    """Return a five-panel source-topology layout with panel 3 spanning right.

    Input order stays A, B, C, D, E: A/B form the upper-left row, D/E the
    lower-left row, and C retains its full-height right-hand span. This mirrors
    ``left-span-2x2`` without reordering semantic panel labels.
    """
    if len(panels) != 5:
        raise ValueError("right-span-2x2 requires exactly five panels")
    gutter = max(8, int(gap))
    row_sizes = []
    for row in ((panels[0], panels[1]), (panels[3], panels[4])):
        row_height = min(panel.height for panel in row)
        sizes = [
            (max(1, int(round(panel.width * row_height / panel.height))), row_height)
            for panel in row
        ]
        row_sizes.append(sizes)
    target_left_width = max(
        sum(width for width, _ in row) + gutter for row in row_sizes
    )
    normalized_rows = []
    for row in row_sizes:
        current_width = sum(width for width, _ in row) + gutter
        scale = target_left_width / current_width
        normalized_rows.append([
            (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
            for width, height in row
        ])
    for row in normalized_rows:
        row[1] = (max(1, target_left_width - gutter - row[0][0]), row[1][1])
    top_height = max(height for _, height in normalized_rows[0])
    bottom_height = max(height for _, height in normalized_rows[1])
    total_height = top_height + gutter + bottom_height
    right_width = max(1, int(round(panels[2].width * total_height / panels[2].height)))
    right_x = target_left_width + gutter
    rects = [
        {"x": 0, "y": 0,
         "w": normalized_rows[0][0][0], "h": normalized_rows[0][0][1]},
        {"x": normalized_rows[0][0][0] + gutter, "y": 0,
         "w": normalized_rows[0][1][0], "h": normalized_rows[0][1][1]},
        {"x": right_x, "y": 0, "w": right_width, "h": total_height},
        {"x": 0, "y": top_height + gutter,
         "w": normalized_rows[1][0][0], "h": normalized_rows[1][0][1]},
        {"x": normalized_rows[1][0][0] + gutter, "y": top_height + gutter,
         "w": normalized_rows[1][1][0], "h": normalized_rows[1][1][1]},
    ]
    return right_x + right_width, total_height, rects, gutter


def layout_right_span_2x2(panels, bg, gap, safety_margin_px):
    width, height, base_rects, _ = right_span_2x2_dimensions(panels, gap)
    canvas = Image.new(
        "RGB", (width + 2 * safety_margin_px, height + 2 * safety_margin_px), bg
    )
    rects = []
    for panel, base in zip(panels, base_rects):
        rect = {
            "x": base["x"] + safety_margin_px,
            "y": base["y"] + safety_margin_px,
            "w": base["w"],
            "h": base["h"],
        }
        canvas.paste(
            panel.resize((rect["w"], rect["h"]), Image.LANCZOS),
            (rect["x"], rect["y"]),
        )
        rects.append(rect)
    return canvas, rects


def evaluate_right_span_2x2(
    panels, box_width_in, box_height_in, gap, safety_margin_px
):
    width, height, rects, gutter = right_span_2x2_dimensions(panels, gap)
    padded_width = width + 2 * safety_margin_px
    padded_height = height + 2 * safety_margin_px
    fit = min(box_width_in / padded_width, box_height_in / padded_height)
    displayed = [(rect["w"] * fit, rect["h"] * fit) for rect in rects]
    areas = [panel_width * panel_height for panel_width, panel_height in displayed]
    short_edges = [min(panel_width, panel_height) for panel_width, panel_height in displayed]
    return {
        "cols": 3,
        "rows": 2,
        "band_px": 0,
        "gutter_px": gutter,
        "composite_width_px": padded_width,
        "composite_height_px": padded_height,
        "unpadded_width_px": width,
        "unpadded_height_px": height,
        "safety_margin_px": safety_margin_px,
        "fit_in_per_px": fit,
        "min_panel_area_sq_in": min(areas),
        "min_panel_short_edge_in": min(short_edges),
        "total_panel_area_sq_in": sum(areas),
        "utilization_fraction": sum(areas) / (box_width_in * box_height_in),
        "empty_cells": 0,
        "displayed_panel_sizes_in": [
            {"width": panel_width, "height": panel_height}
            for panel_width, panel_height in displayed
        ],
        "layout_template": "right-span-2x2",
    }


def two_span_right_stack_dimensions(panels, gap):
    """Return a four-panel layout with panels 1-2 spanning two source rows.

    Panels 3-4 share one right-hand column and remain stacked. The right-column
    width is solved against the average native height of panels 1-2 so adding a
    visible gutter does not double the stacked panels' relative display scale.
    Every panel is resized uniformly; only integer-pixel rounding may change an
    output aspect ratio.
    """
    if len(panels) != 4:
        raise ValueError("two-span-right-stack requires exactly four panels")
    gutter = max(8, int(gap))
    left_target_height = max(
        gutter + 2,
        int(round((panels[0].height + panels[1].height) / 2.0)),
    )
    stacked_height_per_width = (
        panels[2].height / panels[2].width
        + panels[3].height / panels[3].width
    )
    right_width = max(
        1,
        int(round((left_target_height - gutter) / stacked_height_per_width)),
    )
    top_height = max(1, int(round(panels[2].height * right_width / panels[2].width)))
    bottom_height = max(1, int(round(panels[3].height * right_width / panels[3].width)))
    total_height = top_height + gutter + bottom_height
    left_widths = [
        max(1, int(round(panel.width * total_height / panel.height)))
        for panel in panels[:2]
    ]
    right_x = left_widths[0] + gutter + left_widths[1] + gutter
    rects = [
        {"x": 0, "y": 0, "w": left_widths[0], "h": total_height},
        {"x": left_widths[0] + gutter, "y": 0,
         "w": left_widths[1], "h": total_height},
        {"x": right_x, "y": 0, "w": right_width, "h": top_height},
        {"x": right_x, "y": top_height + gutter,
         "w": right_width, "h": bottom_height},
    ]
    total_width = right_x + right_width
    return total_width, total_height, rects, gutter


def layout_two_span_right_stack(panels, bg, gap, safety_margin_px):
    width, height, base_rects, _ = two_span_right_stack_dimensions(panels, gap)
    canvas = Image.new(
        "RGB", (width + 2 * safety_margin_px, height + 2 * safety_margin_px), bg
    )
    rects = []
    for panel, base in zip(panels, base_rects):
        rect = {
            "x": base["x"] + safety_margin_px,
            "y": base["y"] + safety_margin_px,
            "w": base["w"],
            "h": base["h"],
        }
        canvas.paste(
            panel.resize((rect["w"], rect["h"]), Image.LANCZOS),
            (rect["x"], rect["y"]),
        )
        rects.append(rect)
    return canvas, rects


def evaluate_two_span_right_stack(
    panels, box_width_in, box_height_in, gap, safety_margin_px
):
    width, height, rects, gutter = two_span_right_stack_dimensions(panels, gap)
    padded_width = width + 2 * safety_margin_px
    padded_height = height + 2 * safety_margin_px
    fit = min(box_width_in / padded_width, box_height_in / padded_height)
    displayed = [(rect["w"] * fit, rect["h"] * fit) for rect in rects]
    areas = [panel_width * panel_height for panel_width, panel_height in displayed]
    short_edges = [min(panel_width, panel_height) for panel_width, panel_height in displayed]
    return {
        "cols": 3,
        "rows": 2,
        "band_px": 0,
        "gutter_px": gutter,
        "composite_width_px": padded_width,
        "composite_height_px": padded_height,
        "unpadded_width_px": width,
        "unpadded_height_px": height,
        "safety_margin_px": safety_margin_px,
        "fit_in_per_px": fit,
        "min_panel_area_sq_in": min(areas),
        "min_panel_short_edge_in": min(short_edges),
        "total_panel_area_sq_in": sum(areas),
        "utilization_fraction": sum(areas) / (box_width_in * box_height_in),
        "empty_cells": 0,
        "displayed_panel_sizes_in": [
            {"width": panel_width, "height": panel_height}
            for panel_width, panel_height in displayed
        ],
        "layout_template": "two-span-right-stack",
    }


def evaluate_layout(
    panels,
    cols,
    band_in,
    box_width_in,
    box_height_in,
    gap,
    safety_margin_px,
):
    """Score a candidate using the actual slide-fit and fixed-size label bands."""
    band = 2 if band_in > 0 else 0
    for _ in range(12):
        width, height, _, _, _ = layout_dimensions(panels, cols, band, gap)
        padded_width = width + 2 * safety_margin_px
        padded_height = height + 2 * safety_margin_px
        fit = min(box_width_in / padded_width, box_height_in / padded_height)
        next_band = max(2, int(round(band_in / fit))) if band_in > 0 else 0
        if next_band == band:
            break
        band = next_band

    width, height, rows, _, gutter = layout_dimensions(panels, cols, band, gap)
    padded_width = width + 2 * safety_margin_px
    padded_height = height + 2 * safety_margin_px
    fit = min(box_width_in / padded_width, box_height_in / padded_height)
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
        "composite_width_px": padded_width,
        "composite_height_px": padded_height,
        "unpadded_width_px": width,
        "unpadded_height_px": height,
        "safety_margin_px": safety_margin_px,
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
    ap.add_argument(
        "--layout-template",
        choices=("grid", "left-span-2x2", "right-span-2x2", "two-span-right-stack"),
        default="grid",
        help="optional reviewed irregular layout; left-span-2x2 requires five panels, "
             "right-span-2x2 requires five panels, and two-span-right-stack requires four panels",
    )
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
    ap.add_argument(
        "--asset-type",
        choices=("clinical-image", "figure"),
        default="figure",
        help="clinical-image requires 0px outer canvas; figure requires 16px",
    )
    ap.add_argument("--safety-margin-px", type=int, default=None,
                    help="exact outer canvas margin in px (default: 0 for "
                         "clinical-image, 16 for figure)")
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
    if a.layout_template != "grid" and a.cols is not None:
        ap.error("--cols cannot be combined with an irregular --layout-template")
    if a.slide_box_w_in <= 0 or a.slide_box_h_in <= 0:
        ap.error("slide-box dimensions must be positive")
    if not 0 <= a.max_edge_px <= 12:
        ap.error("--max-edge-px must be between 0 and 12")
    if not 0 <= a.max_boundary_shift_px <= 64:
        ap.error("--max-boundary-shift-px must be between 0 and 64")
    expected_margin = 0 if a.asset_type == "clinical-image" else 16
    if a.safety_margin_px is None:
        a.safety_margin_px = expected_margin
    elif not 0 <= a.safety_margin_px <= 256:
        ap.error("--safety-margin-px must be between 0 and 256")
    elif a.safety_margin_px != expected_margin:
        ap.error(
            f"final {a.asset_type} composites require --safety-margin-px "
            f"{expected_margin}"
        )

    bg = hexrgb(a.bg)
    output_path = Path(a.output).expanduser().resolve(strict=False)
    input_paths = [Path(path).expanduser().resolve(strict=False) for path in a.inputs]
    if output_path in input_paths:
        ap.error("output must differ from every input panel")
    geometry_path = Path(a.geometry).expanduser().resolve(strict=False)
    if geometry_path == output_path or geometry_path in input_paths:
        ap.error("geometry output must differ from the composite and every input panel")

    labels = [s.strip() for s in a.labels.split(",") if s.strip()] if a.labels else []
    if labels and len(labels) != len(a.inputs):
        ap.error(f"label count ({len(labels)}) must equal panel count ({len(a.inputs)})")
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
        panels, label_policy, label_margins, label_modes, label_detection = resolve_source_labels(
            panels,
            panel_metadata,
            # Without replacement label values, never remove a source label.
            a.source_label_policy if labels else "preserve",
        )
    except ValueError as error:
        ap.error(str(error))
    cleanup = []
    prepared = []
    try:
        for panel, metadata, label_mode in zip(panels, panel_metadata, label_modes):
            verified_panel, verified_edges, verified_reason = apply_verified_edge_trim(
                panel, metadata, label_mode
            )
            if not a.no_trim:
                cleaned, heuristic_edges = clean_panel_edges(verified_panel, a.max_edge_px)
            else:
                cleaned = verified_panel
                heuristic_edges = {side: 0 for side in EDGE_SIDES}
            prepared.append(cleaned)
            cleanup.append({
                "verified_edge_trim_px": verified_edges,
                "verified_edge_trim_reason": verified_reason,
                "edge_trim_px": heuristic_edges,
                "total_edge_trim_px": {
                    side: verified_edges[side] + heuristic_edges[side]
                    for side in EDGE_SIDES
                },
                "residual_edge_review": residual_edge_review(cleaned, a.max_edge_px),
            })
    except ValueError as error:
        ap.error(str(error))
    panels = prepared

    glyph_h = a.label_pt / 72.0 * a.glyph_ratio          # on-screen label height (in)
    native_labels = "native" in label_modes
    band_in = a.gap_above_in + glyph_h + a.gap_below_in if native_labels else 0
    drop_in = a.gap_above_in + a.center_offset_in         # panel bottom -> label box center

    if a.layout_template == "left-span-2x2":
        if len(panels) != 5:
            ap.error("left-span-2x2 requires exactly five input panels")
        if native_labels:
            ap.error(
                "left-span-2x2 currently requires preserved embedded labels; "
                "native label bands are not supported for spanning layouts"
            )
        selected = evaluate_left_span_2x2(
            panels, a.slide_box_w_in, a.slide_box_h_in, a.gap,
            a.safety_margin_px,
        )
        candidates = [selected]
        cols = selected["cols"]
        band = 0
        comp, rects = layout_left_span_2x2(
            panels, bg, a.gap, a.safety_margin_px
        )
    elif a.layout_template == "right-span-2x2":
        if len(panels) != 5:
            ap.error("right-span-2x2 requires exactly five input panels")
        if native_labels:
            ap.error(
                "right-span-2x2 currently requires preserved embedded labels; "
                "native label bands are not supported for spanning layouts"
            )
        selected = evaluate_right_span_2x2(
            panels, a.slide_box_w_in, a.slide_box_h_in, a.gap,
            a.safety_margin_px,
        )
        candidates = [selected]
        cols = selected["cols"]
        band = 0
        comp, rects = layout_right_span_2x2(
            panels, bg, a.gap, a.safety_margin_px
        )
    elif a.layout_template == "two-span-right-stack":
        if len(panels) != 4:
            ap.error("two-span-right-stack requires exactly four input panels")
        if native_labels:
            ap.error(
                "two-span-right-stack currently requires preserved embedded labels; "
                "native label bands are not supported for spanning layouts"
            )
        selected = evaluate_two_span_right_stack(
            panels, a.slide_box_w_in, a.slide_box_h_in, a.gap,
            a.safety_margin_px,
        )
        candidates = [selected]
        cols = selected["cols"]
        band = 0
        comp, rects = layout_two_span_right_stack(
            panels, bg, a.gap, a.safety_margin_px
        )
    else:
        candidate_columns = [a.cols] if a.cols is not None else range(1, len(panels) + 1)
        candidates = [
            evaluate_layout(panels, columns, band_in,
                            a.slide_box_w_in, a.slide_box_h_in, a.gap,
                            a.safety_margin_px)
            for columns in candidate_columns
        ]
        selected = max(candidates, key=layout_score)
        cols = selected["cols"]
        band = selected["band_px"]
        comp, rects = layout(panels, cols, band, bg, a.gap, a.safety_margin_px)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    comp.save(output_path)
    W, H = comp.size
    fit = min(a.slide_box_w_in / W, a.slide_box_h_in / H)
    drop_px = drop_in / fit

    name = os.path.splitext(os.path.basename(a.output))[0]
    geom = {}
    if os.path.exists(a.geometry):
        geom = json.load(open(a.geometry))
    native_geometry = ([{"label": labels[i] if i < len(labels) else "",
                         "fx_right": (rects[i]["x"] + rects[i]["w"]) / W,
                         "fy_center": (rects[i]["y"] + rects[i]["h"] + drop_px) / H,
                         "reason": ("verified-absent"
                                    if label_detection[i]["placement"] == "absent"
                                    else "cropped-exterior-margin")}
                        for i in range(len(rects)) if label_modes[i] == "native"]
                       if native_labels else [])
    geom[name] = native_geometry
    json.dump(geom, open(a.geometry, "w"), indent=1)

    # postprocess sidecar (so the bundled build_deck.py asset gate passes)
    json.dump({"command": "recompose-panels-banded", "asset_type": a.asset_type,
               "labels": labels, "native_labels": native_labels,
               "native_label_values": [labels[index] for index, mode in enumerate(label_modes)
                                       if mode == "native" and index < len(labels)],
               "cropped_exterior_labels": [
                   labels[index] for index, decision in enumerate(label_margins)
                   if decision and index < len(labels)
               ],
               "verified_absent_labels": [
                   labels[index] for index, detail in enumerate(label_detection)
                   if detail["placement"] == "absent" and index < len(labels)
               ],
               "native_label_geometry": native_geometry,
               "native_label_color": "#8FA8C8",
               "source_label_policy": label_policy,
               "embedded_labels": [labels[index] for index, mode in enumerate(label_modes)
                                   if mode == "preserved" and index < len(labels)],
               "max_edge_px": a.max_edge_px,
               "verified_edge_trim_max_px": VERIFIED_EDGE_TRIM_MAX_PX,
               "max_boundary_shift_px": a.max_boundary_shift_px,
               "panel_cleanup": [
                   {"source": os.path.abspath(path),
                    "label": labels[index] if index < len(labels) else "",
                    **cleanup[index],
                    "label_margin_crop": label_margins[index],
                    "label_action": ("preserved" if label_modes[index] == "preserved" else
                                     "cropped-exterior-margin" if label_margins[index] else
                                     "native-from-verified-absence"),
                    "label_detection": label_detection[index],
                    "label_overwritten_pixels": 0,
                    "boundary_adjustments": boundary_adjustments[index]}
                   for index, path in enumerate(a.inputs)
               ],
               "source_inputs": [os.path.abspath(path) for path in a.inputs],
               "panel_boxes_px": rects,
               "layout_mode": ("template" if a.layout_template != "grid" else
                               "manual" if a.cols is not None else "auto"),
               "layout_template": a.layout_template,
               "requested_cols": a.cols,
               "requested_source_label_policy": a.source_label_policy,
               "cols": cols, "rows": selected["rows"],
               "margin": a.safety_margin_px,
               "safety_margin_px": a.safety_margin_px,
               "padding_background": "#" + "".join(
                   f"{channel:02X}" for channel in ImageColor.getrgb(a.bg)[:3]
               ),
               "unpadded_size_px": [selected["unpadded_width_px"],
                                    selected["unpadded_height_px"]],
               "padded_size_px": [W, H],
               "slide_box_w_in": a.slide_box_w_in,
               "slide_box_h_in": a.slide_box_h_in,
               "glyph_ratio": a.glyph_ratio,
               "center_offset_in": a.center_offset_in,
               "gap": a.gap,
               "no_trim": a.no_trim,
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
