#!/usr/bin/env python3
"""Generate a small, clearly fictional medical-journal article for testing."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont


NAVY = (0.024, 0.078, 0.157)
BLUE = (0.16, 0.39, 0.68)
GREY = (0.35, 0.39, 0.44)
PAGE_WIDTH = 595
PAGE_HEIGHT = 842


def drawing_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")
        if bold
        else ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def synthetic_workflow_image() -> bytes:
    canvas = Image.new("RGB", (1280, 680), "#f4f7fb")
    draw = ImageDraw.Draw(canvas)
    title_font = drawing_font(34, bold=True)
    heading_font = drawing_font(25, bold=True)
    body_font = drawing_font(21)
    draw.text((48, 35), "SYNTHETIC RESEARCH WORKFLOW — FICTIONAL DATA", fill="#102444", font=title_font)

    boxes = [
        ((48, 155, 378, 495), "Dataset assembly", ["120 synthetic records", "Three assessors", "No patient data"]),
        ((470, 155, 800, 495), "Structured review", ["Predefined checklist", "Assessor calibration", "Fictional reference"]),
        ((892, 155, 1222, 495), "Teaching outcome", ["Primary measure: 88%", "Secondary measure: 82%", "Illustrative only"]),
    ]
    for rectangle, heading, lines in boxes:
        draw.rounded_rectangle(rectangle, radius=26, fill="white", outline="#b3c4d9", width=4)
        left, top, _, _ = rectangle
        draw.text((left + 24, top + 30), heading, fill="#102444", font=heading_font)
        for index, line in enumerate(lines):
            draw.text((left + 25, top + 116 + index * 58), f"- {line}", fill="#384455", font=body_font)

    for x in (399, 821):
        draw.line((x, 323, x + 46, 323), fill="#397bb5", width=12)
        draw.polygon([(x + 52, 323), (x + 28, 303), (x + 28, 343)], fill="#397bb5")

    draw.text(
        (48, 567),
        "This diagram is generated for software validation and must not inform clinical care.",
        fill="#854346",
        font=body_font,
    )
    stream = io.BytesIO()
    canvas.save(stream, format="PNG")
    return stream.getvalue()


def add_header(page: fitz.Page, number: int) -> None:
    page.draw_rect(fitz.Rect(0, 0, PAGE_WIDTH, 57), color=NAVY, fill=NAVY)
    page.insert_text(
        (42, 35),
        "SYNTHETIC MEDICAL JOURNAL | NOT A REAL STUDY",
        fontsize=12,
        color=(1, 1, 1),
        fontname="hebo",
    )
    page.insert_text((42, 810), f"Synthetic demonstration / Page {number}", fontsize=9, color=GREY)
    page.insert_text((360, 810), "Fictional results - educational use only", fontsize=8, color=GREY)


def add_heading(page: fitz.Page, text: str, y: float, *, level: int = 1) -> float:
    page.insert_text(
        (46, y),
        text,
        fontsize=16 if level == 1 else 12,
        color=NAVY if level == 1 else BLUE,
        fontname="hebo",
    )
    return y + (28 if level == 1 else 21)


def add_paragraph(page: fitz.Page, text: str, y: float, *, height: float = 70) -> float:
    rectangle = fitz.Rect(46, y, PAGE_WIDTH - 46, y + height)
    inserted = page.insert_textbox(
        rectangle,
        text,
        fontsize=10,
        lineheight=1.42,
        fontname="helv",
        color=(0.13, 0.16, 0.2),
    )
    if inserted < 0:
        raise ValueError(f"Synthetic paragraph does not fit: {text[:40]!r}")
    return rectangle.y1 + 10


def draw_table(page: fitz.Page, top: float) -> float:
    x_positions = [46, 220, 338, 450, 549]
    rows = [
        ("Synthetic measure", "Workflow A", "Workflow B", "Difference"),
        ("Primary measure", "88%", "76%", "+12 points"),
        ("Secondary measure", "82%", "79%", "+3 points"),
        ("Median review time", "4.2 min", "5.1 min", "-0.9 min"),
        ("Assessor agreement", "0.74", "0.61", "+0.13"),
    ]
    row_height = 33
    for index, row in enumerate(rows):
        y0 = top + index * row_height
        fill = NAVY if index == 0 else ((0.95, 0.97, 0.99) if index % 2 == 0 else (1, 1, 1))
        page.draw_rect(fitz.Rect(x_positions[0], y0, x_positions[-1], y0 + row_height), fill=fill, color=(0.78, 0.82, 0.87))
        for cell_index, value in enumerate(row):
            page.insert_text(
                (x_positions[cell_index] + 7, y0 + 21),
                value,
                fontsize=8.4,
                fontname="hebo" if index == 0 else "helv",
                color=(1, 1, 1) if index == 0 else (0.15, 0.18, 0.22),
            )
    for x in x_positions:
        page.draw_line((x, top), (x, top + len(rows) * row_height), color=(0.78, 0.82, 0.87), width=0.6)
    return top + len(rows) * row_height + 12


def create_demo_paper(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()

    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    add_header(page, 1)
    y = 94
    y = add_heading(page, "Synthetic Evaluation of a Structured Research Workflow", y)
    y = add_paragraph(
        page,
        "Synthetic Education Team | Synthetic Journal of Medical Education | 2026. "
        "This article and all results were created solely to test educational software.",
        y,
        height=47,
    )
    y = add_heading(page, "Abstract", y)
    y = add_paragraph(
        page,
        "Purpose: demonstrate how a medical journal can be converted into a teaching presentation. "
        "Methods: 120 fictional records were reviewed with two imaginary workflows. "
        "Results: all numerical values are invented. Conclusion: this file is useful for software "
        "validation and must never be interpreted as evidence for medical decisions.",
        y,
        height=72,
    )
    y = add_heading(page, "Introduction", y)
    y = add_paragraph(
        page,
        "A reusable educational example must avoid copyrighted articles and identifiable patient data. "
        "This synthetic document includes searchable text, a raster workflow figure, and a vector table "
        "so students can verify extraction, image post-processing, and PowerPoint creation.",
        y,
        height=72,
    )
    y = add_heading(page, "Methods", y)
    y = add_paragraph(
        page,
        "The simulated dataset contains 120 invented records. Three fictional assessors apply a structured "
        "checklist. The reference standard, outcomes, and all confidence estimates are fabricated. "
        "No human participants, protected health information, or real clinical datasets are included.",
        y,
        height=72,
    )
    page.insert_text((46, y + 8), "Study design: synthetic research simulation", fontsize=10, color=BLUE, fontname="hebo")

    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    add_header(page, 2)
    y = add_heading(page, "Results", 97)
    y = add_paragraph(
        page,
        "The diagram illustrates the imaginary transition from dataset assembly to structured review "
        "and a fictional teaching outcome. All percentages are placeholders for pipeline validation.",
        y,
        height=48,
    )
    image_rectangle = fitz.Rect(45, y + 10, 550, y + 278)
    page.insert_image(image_rectangle, stream=synthetic_workflow_image())
    y = image_rectangle.y1 + 18
    y = add_paragraph(
        page,
        "Figure 1. Synthetic research-review workflow with fictional performance measures. "
        "This figure is generated for testing and contains no patient information.",
        y,
        height=52,
    )
    y = add_heading(page, "Interpretation", y)
    add_paragraph(
        page,
        "Students should explain the workflow rather than treat its performance values as scientific "
        "findings. A figure should remain on one slide and retain all labels and arrows.",
        y,
        height=60,
    )

    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    add_header(page, 3)
    y = add_heading(page, "Comparative Performance", 98)
    y = add_paragraph(
        page,
        "Table 1 compares two fully fictional workflows. The vector table is intentionally included "
        "to test text-based table extraction and safe image padding.",
        y,
        height=48,
    )
    page.insert_text((46, y + 4), "Table 1. Synthetic workflow comparison", fontsize=11, color=NAVY, fontname="hebo")
    y = draw_table(page, y + 18)
    y = add_heading(page, "Discussion", y + 16)
    y = add_paragraph(
        page,
        "This synthetic resource supports repeatable testing on macOS, Windows, and continuous "
        "integration environments. It demonstrates document structure and figure placement without "
        "distributing copyrighted journal content.",
        y,
        height=61,
    )
    y = add_heading(page, "Limitations", y)
    y = add_paragraph(
        page,
        "The article has no real participants, no validated reference standard, no institutional "
        "review, and no scientific conclusions. Its sole intended use is software validation.",
        y,
        height=53,
    )
    y = add_heading(page, "Conclusion", y)
    add_paragraph(
        page,
        "A portable teaching repository can demonstrate medical-journal presentation generation "
        "without exposing protected information. Every result in this document is fictional.",
        y,
        height=52,
    )

    document.set_metadata(
        {
            "title": "Synthetic Evaluation of a Structured Research Workflow",
            "author": "Synthetic Education Team",
            "subject": "Fictional article for software testing; not clinical evidence",
            "keywords": "synthetic, medical education, fictional, no patient data",
        }
    )
    document.save(destination, garbage=4, deflate=True)
    document.close()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = create_demo_paper(args.output.expanduser().resolve())
    print(f"Created synthetic demonstration paper: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
