"""Render reviewed PDF-coordinate crops; never infer panel order from object IDs.

Usage: python source_crops.py plan.json --out NEW_DIRECTORY
See references/article_level_crop_design.md for the plan contract.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import tempfile
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def region(page, box, expected=(), *, image_only=False):
    """Reject out-of-page bounds and partial words/images before rasterization."""
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in box)):
        raise ValueError("bbox must contain four finite PDF-point coordinates")
    if not isinstance(expected, (list, tuple)) or not all(
        isinstance(term, str) and term.strip() for term in expected
    ):
        raise ValueError("expected_text must contain non-empty strings")
    rect = fitz.Rect(box)
    if rect.is_empty or not page.rect.contains(rect):
        raise ValueError(f"Invalid/out-of-page bbox: {box}")
    words = page.get_text("words")
    selected = []
    for word in words:
        wr = fitz.Rect(word[:4])
        overlap = wr & rect
        if overlap.is_empty:
            continue
        if image_only:
            # Font line boxes can extend into an image despite the glyph being
            # outside it. Accept only when every traced character of this word
            # is outside; never waive a character actually touching the crop.
            chars = [fitz.Rect(c[3]) for s in page.get_texttrace()
                     for c in s['chars'] if wr.contains(fitz.Point(c[2]))]
            if chars and all((r & rect).is_empty for r in chars):
                continue
            raise ValueError(f"Image-only crop contains source text {word[4]!r}")
        if overlap.get_area() < wr.get_area() - 0.01:
            raise ValueError(f"Crop cuts text {word[4]!r}: {box}")
        selected.append(word[4])
    for item in page.get_image_info():
        ir = fitz.Rect(item["bbox"])
        overlap = ir & rect
        if not overlap.is_empty and overlap.get_area() < ir.get_area() - 0.01:
            raise ValueError(f"Crop cuts a source image: {box}")
    # Closed vector rectangles include flowchart frames/nodes and table cells.
    # Ignore zero-area rules; they may legitimately end on a crop boundary.
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] != "re":
                continue
            vr = fitz.Rect(item[1])
            overlap = vr & rect
            if not overlap.is_empty and overlap.get_area() < vr.get_area() - 0.01:
                raise ValueError(f"Crop cuts a vector rectangle: {box}")
    text = " ".join(selected)
    for term in expected:
        if " ".join(term.split()).casefold() not in text.casefold():
            raise ValueError(f"Missing expected text {term!r}: {box}")
    return rect, text


def render(page, rect, dpi):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=rect, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def image_region(page, reviewed):
    """Separate image content from its printed label without cutting anatomy.

    Only an unambiguous complete raster object is eligible. A small PDF-point
    border allowance preserves the journal's thin vector frame. Validate the
    result again; do not silently relax text/image/vector clipping checks.
    """
    reviewed = fitz.Rect(reviewed)
    matches = [fitz.Rect(info['bbox']) for info in page.get_image_info()
               if reviewed.contains(fitz.Rect(info['bbox']))]
    if len(matches) != 1:
        raise ValueError('Image-only export needs exactly one complete source image per panel')
    bounds = fitz.Rect(matches[0])
    # Include only real rectangular frames that coincide with this image.
    # Do not invent a fixed white border around every PDF image object.
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0] == 're' and all(abs(a-b) < 1 for a,b in zip(item[1], matches[0])):
                half = drawing.get('width', 0) / 2
                bounds |= fitz.Rect(item[1]) + (-half, -half, half, half)
    if not reviewed.contains(bounds):
        raise ValueError('Reviewed panel must include the complete image border')
    rect, text = region(page, list(bounds), image_only=True)
    return rect


def source_page(document, number):
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(document):
        raise ValueError('page must be a valid one-based PDF page number')
    return document[number - 1]


def stack(images, gap=16, margin=16):
    width = max(im.width for im in images)
    out = Image.new("RGB", (width + 2 * margin,
                           sum(im.height for im in images) + gap * (len(images)-1) + 2 * margin), "white")
    y = margin
    for im in images:
        out.paste(im, (margin + (width-im.width)//2, y))
        y += im.height + gap
    return out


def grid(images, columns=2):
    # Contain/pad only: never crop, stretch, or reorder source panels.
    width = max(im.width for im in images)
    rows = []
    for start in range(0, len(images), columns):
        group = images[start:start+columns]
        height = max(im.height for im in group)
        row = Image.new("RGB", (columns * width + (columns-1)*24, height), "white")
        for j, im in enumerate(group):
            row.paste(im, (j*(width+24)+(width-im.width)//2, 0))
        rows.append(row)
    return stack(rows, gap=24)


def generate(plan, output):
    source = Path(plan["pdf"]).resolve()
    if digest(source) != plan["source_sha256"]:
        raise ValueError("Source PDF hash differs from reviewed plan")
    ids = [a["id"] for a in plan["assets"]]
    if not ids:
        raise ValueError('Asset inventory must not be empty')
    if (len(ids) != len(set(ids)) or len(plan["expected_assets"]) != len(ids)
            or set(ids) != set(plan["expected_assets"])):
        raise ValueError("Asset inventory mismatch/duplicate")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in ids):
        raise ValueError("Unsafe asset ID")
    dpi = plan.get("dpi", 300)
    if (isinstance(dpi, bool) or not isinstance(dpi, (int, float))
            or not math.isfinite(dpi) or not 72 <= dpi <= 600):
        raise ValueError("dpi must be 72..600")
    output = Path(output)
    if output.exists():
        raise ValueError("Use a new output directory; never overwrite reviewed assets")
    prepared = []
    with fitz.open(source) as doc:
        for asset in plan["assets"]:
            parts = []
            image_regions = {}
            if asset["type"] == "table":
                page = source_page(doc, asset['page'])
                box, text = region(page, asset["bbox"], asset["expected_text"])
                if not asset["expected_text"]:
                    raise ValueError("Tables require title/header/last-row/footnote anchors")
                cuts = asset.get("splits", [])
                if cuts:
                    header = asset["header_bottom"]
                    if cuts != sorted(set(cuts)) or not box.y0 < header < cuts[0] or cuts[-1] >= box.y1:
                        raise ValueError("Invalid table split boundaries")
                    hr, _ = region(page, [box.x0, box.y0, box.x1, header])
                    boundaries = [header, *cuts, box.y1]
                    for n, (top, bottom) in enumerate(zip(boundaries, boundaries[1:])):
                        body, _ = region(page, [box.x0, top, box.x1, bottom])
                        parts.append((f"{asset['id']}{chr(65+n)}", stack([
                            render(page, hr, dpi), render(page, body, dpi)], gap=0)))
                else:
                    parts.append((asset["id"], stack([render(page, box, dpi)])))
            elif asset["type"] == "figure":
                panels = asset["panels"]
                columns = asset.get('columns', 2)
                if not panels or isinstance(columns, bool) or not isinstance(columns, int) or columns < 1:
                    raise ValueError('Figures require panels and a positive integer column count')
                if [p["label"] for p in panels] != asset["expected_labels"]:
                    raise ValueError("Panel inventory/order mismatch")
                if len(set(asset["expected_labels"])) != len(panels):
                    raise ValueError("Duplicate panel labels")
                if any(not re.fullmatch(r"[A-Za-z0-9]+", p["label"]) for p in panels):
                    raise ValueError("Unsafe panel label")
                ims = []
                for panel in panels:
                    page = source_page(doc, panel['page'])
                    rect, text = region(page, panel["bbox"], panel.get("expected_text", []))
                    if panel["label"] not in text.split():
                        raise ValueError("Include the original panel letter in the crop")
                    im = render(page, rect, dpi)
                    ims.append(im)
                    parts.append((asset["id"]+"_"+panel["label"], stack([im])))
                    if 'export_image_panels' in asset and not isinstance(asset['export_image_panels'], bool):
                        raise ValueError('export_image_panels must be a boolean')
                    if asset.get('export_image_panels', False):
                        content = image_region(page, rect)
                        name = asset['id'] + '_' + panel['label'] + '_image'
                        image = render(page, content, dpi)
                        review = panel.get('source_panel_label')
                        if review is not None:
                            from recompose_panels_banded import label_details
                            details = label_details({'source_panel_label': review}, image)
                            if details['geometry_space'] != 'verified-full-panel-review':
                                raise ValueError('Image-only label review requires verified full-panel absence evidence')
                        parts.append((name, image))
                        image_regions[name] = {'page': panel['page'], 'bbox': list(content),
                                               'original_panel': panel['label']}
                        if review is not None:
                            image_regions[name]['source_panel_label'] = review
                parts.append((asset["id"], grid(ims, columns)))
            else:
                raise ValueError("Unknown asset type")
            prepared.append((asset, parts, image_regions))
        names = [name for _, parts, _ in prepared for name, _ in parts]
        if len(names) != len(set(names)):
            raise ValueError('Generated filenames collide; choose distinct asset IDs')
        # Validate the entire plan before writing any outputs.
        output.mkdir(parents=True)
        report = {"source_sha256": digest(source), "status": "STRUCTURAL_PASS_VISUAL_REVIEW_REQUIRED", "assets": []}
        cards = []
        thumbnails = []
        for asset, parts, image_regions in prepared:
            for name, im in parts:
                path = output / (name + ".png")
                im.save(path)
                meta = {"command": "source-coordinate-crop", "asset_type": asset["type"],
                        "source_sha256": report["source_sha256"], "output_sha256": digest(path),
                        "dpi": dpi, "margin": 16, "plan": asset,
                        "status": report["status"], "source": str(source),
                        "output_id": name, "schema": "medical-journal-source-crop/v1",
                        "intermediate": asset["type"] == "figure",
                        "safety_margin_px": 16, "padding_background": "#FFFFFF",
                        "padded_size_px": list(im.size),
                        "unpadded_size_px": [im.width - 32, im.height - 32]}
                if name in image_regions:
                    meta.update({'margin': 0, 'safety_margin_px': 0,
                                 'unpadded_size_px': list(im.size),
                                 'image_region': image_regions[name],
                                 'source_pdf': str(source), 'purpose': 'banded-composition-input'})
                    if 'source_panel_label' in image_regions[name]:
                        meta['source_panel_label'] = image_regions[name]['source_panel_label']
                elif asset['type'] == 'figure':
                    meta['purpose'] = 'source-review-not-slide-design'
                if asset["type"] == "table":
                    meta["table_safety_margin_px"] = 16
                path.with_suffix(".png.postprocess.json").write_text(json.dumps(meta, indent=2))
                report["assets"].append({"id": name, "sha256": digest(path)})
                if name == asset["id"] or asset["type"] == "table":
                    cards.append(f'<section><h2>{html.escape(name)}</h2><a href="{name}.png"><img src="{name}.png"></a></section>')
                    thumb = im.copy(); thumb.thumbnail((760, 800))
                    card = Image.new("RGB", (800, 850), "#edf1f5")
                    ImageDraw.Draw(card).text((20, 10), name, fill="black", font=ImageFont.load_default(size=24))
                    card.paste(thumb, ((800-thumb.width)//2, 45))
                    thumbnails.append(card)
        grid(thumbnails).save(output / "contact-sheet.png")
        (output / "qa.json").write_text(json.dumps(report, indent=2))
        (output / "plan.json").write_text(json.dumps(plan, indent=2))
        (output / "index.html").write_text('<meta charset="utf-8"><title>Source-coordinate crop review</title><style>body{font-family:system-ui;background:#edf1f5;padding:24px}section{background:white;padding:24px;margin:24px 0}img{max-width:100%;max-height:1100px}h2{font-size:24px}</style><h1>Source-coordinate crop review</h1><p>Structural checks are not a substitute for visual comparison with the source PDF. Original panel letters are preserved. Figure grids are source-review previews, not a replacement for the slide design. Use image-only panels with the banded compositor and native slide labels when preserving the classroom design.</p>'+"".join(cards))
    return report



def replay_source_crop(asset, sidecar):
    """Rebuild the declared output and compare provenance metadata and opaque pixels.

    This authenticates a transform, not its paper binding. The caller must also
    require the source PDF and every used page from a fresh extraction audit.
    """
    try:
        if sidecar.get("schema") != "medical-journal-source-crop/v1":
            raise ValueError("unsupported source-crop sidecar schema")
        source = Path(sidecar["source"]).expanduser()
        if not source.is_absolute():
            source = Path(asset).parent / source
        source = source.resolve()
        plan_asset = sidecar["plan"]
        plan = {"pdf": str(source), "source_sha256": sidecar["source_sha256"],
                "dpi": sidecar["dpi"], "assets": [plan_asset],
                "expected_assets": [plan_asset["id"]]}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "replay"
            report = generate(plan, output)
            name = sidecar["output_id"]
            if name not in {item["id"] for item in report["assets"]}:
                raise ValueError("source-crop output is absent from its plan")
            regenerated = output / (name + ".png")
            expected = json.loads(regenerated.with_suffix(".png.postprocess.json").read_text())
            normalized = dict(sidecar, source=str(source))
            if normalized != expected:
                raise ValueError("source-crop metadata does not match deterministic replay")
            if digest(asset) != sidecar["output_sha256"]:
                raise ValueError("source-crop output hash mismatch")
            with Image.open(asset) as actual, Image.open(regenerated) as fresh:
                if (actual.convert("RGBA").getchannel("A").getextrema() != (255, 255)
                        or actual.size != fresh.size
                        or actual.convert("RGB").tobytes() != fresh.convert("RGB").tobytes()):
                    raise ValueError("source-crop pixels do not match deterministic replay")
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        return [f"Source crop {Path(asset).name}: {error}"]
    return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(json.loads(args.plan.read_text()), args.out), indent=2))
