from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import classroom  # noqa: E402
import image_polarity  # noqa: E402
import qa_check  # noqa: E402


def patterned_image() -> Image.Image:
    image = Image.new("L", (220, 180), 35)
    draw = ImageDraw.Draw(image)
    draw.rectangle((25, 20, 155, 125), fill=205)
    draw.ellipse((100, 70, 200, 165), fill=110)
    draw.line((10, 165, 205, 15), fill=245, width=7)
    return image


def write_asset(root: Path, name: str, *, width: int = 220, **sidecar: object) -> Path:
    directory = root / "final_assets"
    directory.mkdir(exist_ok=True)
    path = directory / name
    patterned_image().resize((width, 180)).save(path)
    metadata = {"command": "trim", "asset_type": "figure", **sidecar}
    path.with_suffix(path.suffix + ".postprocess.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return path


def full_spec() -> dict[str, object]:
    slides: list[dict[str, object]] = [
        {
            "type": "title",
            "title": "Synthetic Medical Study",
            "authors": "Education Team",
            "citation": "Synthetic Journal, 2026",
            "notes": "📚 這是虛構教學論文。",
        },
        {
            "type": "outline",
            "title": "Learning Outline",
            "items": ["1️⃣ Study design — Slides 3–20", "2️⃣ Results — Slides 21–39"],
            "notes": "🧭 本頁說明研究架構。",
        },
        {
            "type": "part",
            "number": 1,
            "title": "Study Design",
            "notes": "🔎 本段介紹研究設計。",
        },
    ]
    slides.extend(
        {
            "type": "content",
            "title": f"Teaching Point {index}",
            "body": ["Clinical context:", "Synthetic research findings", "→ Teaching takeaway"],
            "notes": "💡 此頁為繁體中文教學講稿。",
        }
        for index in range(1, 36)
    )
    slides.extend(
        [
            {
                "type": "references",
                "title": "References",
                "items": ["Synthetic Journal, 2026"],
                "notes": "📖 本頁列出參考資料。",
            },
            {"type": "thanks", "title": "Thank You", "notes": "🙏 感謝聆聽。"},
        ]
    )
    return {"meta": {"footer_label": "Synthetic Classroom"}, "slides": slides}


def write_spec(root: Path, spec: dict[str, object]) -> Path:
    path = root / "deck_spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def add_figure(
    spec: dict[str, object], asset: Path, *, caption: str = "Figure 1. Synthetic image.", **extra: object
) -> dict[str, object]:
    slide: dict[str, object] = {
        "type": "figure",
        "title": "Research Findings",
        "image": f"final_assets/{asset.name}",
        "caption": caption,
        "notes": "🖼️【圖片說明】此圖為虛構教學影像。",
        **extra,
    }
    slides = spec["slides"]
    assert isinstance(slides, list)
    slides[3] = slide
    return slide


def create_synthetic_inversion_fixture(
    root: Path, *, source_size: tuple[int, int] | None = None, source_format: str = "PNG"
) -> tuple[Path, Path, Path]:
    extracted = root / "extracted"
    figure_directory = extracted / "figures"
    figure_directory.mkdir(parents=True)
    source_pdf = root / "synthetic-inverted-image.pdf"
    raw_path = extracted / "image_p01_01.png"
    rendered_path = figure_directory / "Figure_01.png"
    source = patterned_image()
    if source_size is not None:
        source = source.resize(source_size)
    raw = ImageOps.invert(source)
    raw.save(raw_path)

    stream = BytesIO()
    raw.save(stream, format=source_format)
    document = pymupdf.open()
    page = document.new_page(width=300, height=240)
    rectangle = pymupdf.Rect(30, 30, 250, 210)
    xref = page.insert_image(rectangle, stream=stream.getvalue())
    document.xref_set_key(xref, "Decode", "[1 0]")
    document.save(source_pdf)
    document.close()

    with pymupdf.open(source_pdf) as pdf:
        pixmap = pdf[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=rectangle, alpha=False)
        pixmap.save(rendered_path)

    bbox = {"x0": 30, "y0": 30, "x1": 250, "y1": 210}
    manifest = {
        "pdf": str(source_pdf),
        "images": [{"file": raw_path.name, "page": 1, "bbox_pt": bbox}],
        "figures": [
            {"source": raw_path.name, "page": 1, "file": "figures/Figure_01.png", "bbox_pt": bbox}
        ],
    }
    path = extracted / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, raw_path, rendered_path


class ImagePolarityTests(unittest.TestCase):
    def test_correct_grayscale_matches_reference(self) -> None:
        image = patterned_image()
        result = image_polarity.compare_polarity(image, image.copy())
        self.assertEqual(result["status"], "correct")
        self.assertGreater(result["correlation"], 0.99)

    def test_inverted_grayscale_is_rejected(self) -> None:
        image = patterned_image()
        result = image_polarity.compare_polarity(ImageOps.invert(image), image)
        self.assertEqual(result["status"], "inverted")
        self.assertLess(result["correlation"], -0.99)

    def test_low_contrast_image_is_not_falsely_classified(self) -> None:
        plain = Image.new("L", (100, 100), 128)
        self.assertEqual(image_polarity.compare_polarity(plain, plain)["status"], "inconclusive")

    def test_pdf_decode_array_detects_unsafe_raw_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, raw, rendered = create_synthetic_inversion_fixture(Path(temporary))
            report = image_polarity.audit_extraction(manifest)
            self.assertTrue(report["ok"])
            self.assertEqual(report["unsafe_raw_streams"], 1)
            self.assertEqual(report["corrected_rendered_figures"], 1)
            self.assertEqual(report["figures"][0]["source_path"], str(raw.resolve()))
            self.assertEqual(report["figures"][0]["rendered_path"], str(rendered.resolve()))
            self.assertTrue((manifest.parent / "polarity-report.json").is_file())
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(saved["polarity_audit"]["unsafe_raw_streams"], 1)

    def test_inverted_rendered_figure_fails_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, raw, rendered = create_synthetic_inversion_fixture(Path(temporary))
            rendered.write_bytes(raw.read_bytes())
            report = image_polarity.audit_extraction(manifest, persist=False)
            self.assertFalse(report["ok"])
            self.assertIn("inverted grayscale", report["failures"][0])

    def test_final_asset_cannot_use_inverted_raw_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, raw, _ = create_synthetic_inversion_fixture(root)
            report = image_polarity.audit_extraction(manifest, persist=False)
            asset = write_asset(root, "Figure_1.png", source=str(raw))
            spec = full_spec()
            add_figure(spec, asset)
            result = image_polarity.audit_final_assets(write_spec(root, spec), report)
            self.assertFalse(result["ok"])
            self.assertIn("inverted raw PDF image", result["failures"][0])

    def test_composite_asset_cannot_hide_inverted_panel_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, raw, rendered = create_synthetic_inversion_fixture(root)
            report = image_polarity.audit_extraction(manifest, persist=False)
            asset = write_asset(root, "Figure_1.png", source_inputs=[str(rendered), str(raw)])
            spec = full_spec()
            add_figure(spec, asset)
            result = image_polarity.audit_final_assets(write_spec(root, spec), report)
            self.assertFalse(result["ok"])
            self.assertTrue(any(raw.name in message for message in result["failures"]))

    def test_rendered_source_passes_final_asset_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _, rendered = create_synthetic_inversion_fixture(root)
            report = image_polarity.audit_extraction(manifest, persist=False)
            asset = write_asset(root, "Figure_1.png", source=str(rendered))
            spec = full_spec()
            add_figure(spec, asset)
            result = image_polarity.audit_final_assets(write_spec(root, spec), report)
            self.assertTrue(result["ok"])

    def test_modified_final_image_is_checked_even_when_source_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _, rendered = create_synthetic_inversion_fixture(root)
            report = image_polarity.audit_extraction(manifest, persist=False)
            asset = write_asset(root, "Figure_1.png", source=str(rendered))
            ImageOps.invert(patterned_image()).save(asset)
            spec = full_spec()
            add_figure(spec, asset)
            result = image_polarity.audit_final_assets(write_spec(root, spec), report)
            self.assertFalse(result["ok"])
            self.assertIn("reverses the grayscale", result["failures"][0])

    def test_intermediate_sidecar_cannot_hide_unsafe_original_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, raw, _ = create_synthetic_inversion_fixture(root)
            report = image_polarity.audit_extraction(manifest, persist=False)
            intermediate = write_asset(root, "Intermediate.png", source=str(raw))
            asset = write_asset(root, "Figure_1.png", source=str(intermediate))
            spec = full_spec()
            add_figure(spec, asset)
            result = image_polarity.audit_final_assets(write_spec(root, spec), report)
            self.assertFalse(result["ok"])
            self.assertTrue(any(raw.name in message for message in result["failures"]))


class AdvancedSpecificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.spec = full_spec()

    def validate(self) -> dict[str, object]:
        return qa_check.validate_specification(write_spec(self.root, self.spec), mode="full")

    def assertFailureContains(self, expected: str) -> None:
        report = self.validate()
        self.assertFalse(report["ok"], msg=str(report))
        self.assertTrue(any(expected in value for value in report["failures"]), msg=str(report))

    def test_valid_full_deck_passes_advanced_qa(self) -> None:
        report = self.validate()
        self.assertTrue(report["ok"], msg=str(report))
        self.assertEqual(report["slides"], 40)

    def test_full_mode_rejects_short_deck_without_required_sections(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        self.spec["slides"] = [slides[0], *slides[3:9], slides[-1]]
        report = qa_check.validate_specification(write_spec(self.root, self.spec), mode="full")
        self.assertFalse(report["ok"], msg=str(report))
        self.assertEqual(report["slides"], 8)
        self.assertTrue(any("expects 40-55 slides" in failure for failure in report["failures"]))

    def test_full_deck_requires_outline_and_references(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[1]["type"] = "part"
        slides[-2]["type"] = "content"
        report = self.validate()
        self.assertTrue(any("missing its outline" in value for value in report["failures"]))
        self.assertTrue(any("missing its references" in value for value in report["failures"]))

    def test_title_requires_author_and_citation(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[0].pop("authors")
        self.assertFailureContains("metadata: authors")

    def test_visible_chinese_is_rejected_before_build(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[3]["title"] = "不應出現中文"
        self.assertFailureContains("visible field title contains Chinese")

    def test_speaker_notes_must_contain_chinese(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[3]["notes"] = "English-only speaker notes"
        self.assertFailureContains("speaker notes contain no Chinese")

    def test_multiple_panels_require_geometry(self) -> None:
        asset = write_asset(self.root, "Figure_1.png")
        add_figure(self.spec, asset, panel_labels=["A", "B"])
        self.assertFailureContains("panel labels but no panel geometry")

    def test_native_panel_geometry_is_accepted(self) -> None:
        asset = write_asset(self.root, "Figure_1.png", native_labels=True)
        add_figure(self.spec, asset, panel_labels=["A", "B"])
        self.assertTrue(self.validate()["ok"])

    def test_notes_cannot_reference_missing_panels(self) -> None:
        asset = write_asset(self.root, "Figure_1.png")
        add_figure(
            self.spec,
            asset,
            panel_labels=["A", "B"],
            panel_label_x_fracs=[0.3, 0.7],
            notes="🖼️【C圖】不存在的面板。",
        )
        self.assertFailureContains("reference missing panel")

    def test_table_margin_requires_safety_band(self) -> None:
        asset = write_asset(self.root, "Table_1.png", asset_type="table", margin=3)
        add_figure(self.spec, asset, caption="Table 1. Synthetic results.")
        self.assertFailureContains("unsafe 3px edge margin")

    def test_split_table_requires_matching_pixel_width(self) -> None:
        first = write_asset(self.root, "Table1A.png", width=220, asset_type="table", margin=12)
        second = write_asset(self.root, "Table1B.png", width=180, asset_type="table", margin=12)
        first_slide = add_figure(self.spec, first, caption="Table 1A. Results.", image_width_in=8)
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[4] = {**first_slide, "image": f"final_assets/{second.name}", "caption": "Table 1B."}
        self.assertFailureContains("unequal image pixel widths")

    def test_split_table_requires_matching_display_width(self) -> None:
        first = write_asset(self.root, "Table1A.png", asset_type="table", margin=12)
        second = write_asset(self.root, "Table1B.png", asset_type="table", margin=12)
        first_slide = add_figure(self.spec, first, caption="Table 1A. Results.", image_width_in=8)
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[4] = {
            **first_slide,
            "image": f"final_assets/{second.name}",
            "caption": "Table 1B.",
            "image_width_in": 6,
        }
        self.assertFailureContains("unequal on-screen image_width_in")

    def test_full_mode_rejects_mostly_unstructured_content(self) -> None:
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        for slide in slides:
            if slide.get("type") == "content":
                slide["body"] = ["First bullet", "Second bullet", "Third bullet"]
        self.assertFailureContains("flat bullet lists")

    def test_same_paper_figure_cannot_appear_twice(self) -> None:
        first = write_asset(self.root, "Figure_1.png")
        second = write_asset(self.root, "Figure_1_copy.png")
        first_slide = add_figure(self.spec, first)
        slides = self.spec["slides"]
        assert isinstance(slides, list)
        slides[4] = {**first_slide, "image": f"final_assets/{second.name}"}
        self.assertFailureContains("Figure 1 appears on multiple slides")

    def test_spec_gate_detects_inverted_panel_provenance(self) -> None:
        _, raw, _ = create_synthetic_inversion_fixture(self.root)
        asset = write_asset(self.root, "Figure_1.png", source_inputs=[str(raw)])
        add_figure(self.spec, asset)
        self.assertFailureContains("inverted raw PDF image")


class PortableIntegrationTests(unittest.TestCase):
    def test_launcher_exposes_both_new_qa_commands(self) -> None:
        parser = classroom.create_parser()
        self.assertEqual(parser.parse_args(["qa-spec", "deck.json"]).command, "qa-spec")
        self.assertEqual(parser.parse_args(["image-qa", "manifest.json"]).command, "image-qa")

    def test_aligned_recomposition_records_original_panel_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.png"
            second = root / "B.png"
            patterned_image().convert("RGB").save(first)
            patterned_image().convert("RGB").save(second)
            output = root / "Figure_1.png"
            subprocess.run(
                [
                    sys.executable,
                    str(classroom.resolve_skill_script("recompose_panels_aligned")),
                    str(output),
                    "--inputs",
                    str(first),
                    str(second),
                    "--labels",
                    "A,B",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sidecar = json.loads(output.with_suffix(".png.postprocess.json").read_text())
            self.assertEqual(sidecar["source_inputs"], [str(first.resolve()), str(second.resolve())])

    def test_banded_recomposition_records_original_panel_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.png"
            second = root / "B.png"
            patterned_image().convert("RGB").save(first)
            patterned_image().convert("RGB").save(second)
            output = root / "Figure_1.png"
            subprocess.run(
                [
                    sys.executable,
                    str(classroom.resolve_skill_script("recompose_panels_banded")),
                    str(output),
                    "--inputs",
                    str(first),
                    str(second),
                    "--labels",
                    "A,B",
                    "--geometry",
                    str(root / "geometry.json"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sidecar = json.loads(output.with_suffix(".png.postprocess.json").read_text())
            self.assertEqual(
                [Path(value).resolve() for value in sidecar["source_inputs"]],
                [first.resolve(), second.resolve()],
            )

    def test_standard_recomposition_records_original_panel_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.png"
            second = root / "B.png"
            patterned_image().convert("RGB").save(first)
            patterned_image().convert("RGB").save(second)
            output = root / "Figure_1.png"
            subprocess.run(
                [
                    sys.executable,
                    str(classroom.resolve_skill_script("postprocess_assets")),
                    "recompose-panels",
                    str(output),
                    "--inputs",
                    str(first),
                    str(second),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sidecar = json.loads(output.with_suffix(".png.postprocess.json").read_text())
            self.assertEqual(sidecar["source_inputs"], [str(first.resolve()), str(second.resolve())])


if __name__ == "__main__":
    unittest.main()
