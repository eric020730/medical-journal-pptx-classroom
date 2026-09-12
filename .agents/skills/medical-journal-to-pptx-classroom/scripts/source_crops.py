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
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def region(page, box, expected=()):
    """Reject out-of-page bounds and partial words/images before rasterization."""
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError("bbox must contain four finite PDF-point coordinates")
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
    bounds = matches[0] + (-0.3, -0.3, 0.3, 0.3)
    if not reviewed.contains(bounds):
        raise ValueError('Reviewed panel must include the complete image border')
    rect, text = region(page, list(bounds))
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
    if len(ids) != len(set(ids)) or set(ids) != set(plan["expected_assets"]):
        raise ValueError("Asset inventory mismatch/duplicate")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in ids):
        raise ValueError("Unsafe asset ID")
    dpi = plan.get("dpi", 300)
    if not 72 <= dpi <= 600:
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
                    if asset.get('export_image_panels', False):
                        content = image_region(page, rect)
                        name = asset['id'] + '_' + panel['label'] + '_image'
                        parts.append((name, render(page, content, dpi)))
                        image_regions[name] = {'page': panel['page'], 'bbox': list(content),
                                               'original_panel': panel['label']}
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
                        "status": report["status"]}
                if name in image_regions:
                    meta.update({'margin': 0, 'image_region': image_regions[name],
                                 'source_pdf': str(source), 'purpose': 'banded-composition-input'})
                elif asset['type'] == 'figure':
                    meta['purpose'] = 'source-review-not-slide-design'
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(json.loads(args.plan.read_text()), args.out), indent=2))
