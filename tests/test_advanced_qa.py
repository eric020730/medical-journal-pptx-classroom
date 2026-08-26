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
SKILL_SCRIPTS = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "medical-journal-to-pptx-integrated"
    / "scripts"
)
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

    source = sidecar.pop("source", None)
    source_inputs = sidecar.pop("source_inputs", None)
    asset_type = str(sidecar.get("asset_type", "figure"))
    margin = int(sidecar.get("margin", 16))
    if isinstance(source, str) and Path(source).suffix.lower() != ".pdf":
        command = [
            sys.executable,
            str(SKILL_SCRIPTS / "postprocess_assets.py"),
            "trim",
            source,
            str(path),
            "--margin",
            str(margin),
            "--asset-type",
            asset_type,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        metadata_path = path.with_suffix(path.suffix + ".postprocess.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(sidecar)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return path
    if isinstance(source_inputs, list) and source_inputs:
        if len(source_inputs) == 1:
            return write_asset(root, name, width=width, source=source_inputs[0], **sidecar)
        command = [
            sys.executable,
            str(SKILL_SCRIPTS / "postprocess_assets.py"),
            "recompose-panels",
            str(path),
            "--inputs",
            *(str(value) for value in source_inputs),
            "--margin",
            str(margin),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        metadata_path = path.with_suffix(path.suffix + ".postprocess.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(sidecar)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return path

    patterned_image().resize((width, 180)).save(path)
    metadata = {"command": "trim", "asset_type": "figure", **sidecar}
    if source is not None:
        metadata["source"] = source
    if source_inputs is not None:
        metadata["source_inputs"] = source_inputs
    path.with_suffix(path.suffix + ".postprocess.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return path


def full_spec() -> dict[str, object]:
    shared_note = (
        "📌 這張投影片提供完整教學重點，協助理解研究內容與臨床判斷，"
        "並連結後續討論。"
    )
    slides: list[dict[str, object]] = [
        {
            "type": "title",
            "title": "Synthetic Medical Study",
            "authors": "Author A, Author B, et al.",
            "citation": "Synthetic Journal 2026;1:1-10",
            "notes": shared_note + " 本頁介紹研究標題、作者資訊與期刊來源。",
        },
        {
            "type": "outline",
            "title": "Learning Outline",
            "items": [
                "1️⃣ Background — Slides 3–10",
                "2️⃣ Methods — Slides 11–20",
                "3️⃣ Results — Slides 21–38",
            ],
            "notes": shared_note + " 本頁依序預告背景、方法與結果三個教學區段。",
        },
        {
            "type": "part",
            "number": 1,
            "title": "Study Design",
            "notes": shared_note + " 本頁開啟研究設計段落並提示接下來的判讀方向。",
        },
    ]
    teaching_topics = [
        "研究問題界定", "疾病負擔評估", "既有治療缺口", "研究假說形成",
        "試驗設計選擇", "收案族群界定", "納入條件判讀", "排除條件判讀",
        "介入措施細節", "對照策略合理性", "隨機分派流程", "盲法執行品質",
        "主要終點定義", "次要終點定義", "樣本數估算", "統計模型選擇",
        "缺失資料處理", "敏感度分析", "基線平衡判讀", "主要結果解讀",
        "次要結果解讀", "效果量臨床意義", "信賴區間判讀", "亞組分析限制",
        "不良事件比較", "依從性與交叉", "追蹤完整程度", "偏差風險評估",
        "外部效度判讀", "證據確定性", "研究優勢整理", "研究限制整理",
        "臨床決策轉譯", "共享決策應用", "未來研究方向",
    ]
    for index, topic in enumerate(teaching_topics, start=1):
        slides.append(
            {
                "type": "content",
                "title": f"Teaching Point {index}",
                "body": [
                    "Clinical context:",
                    "• Synthetic evidence supports this teaching example",
                    "✅ Clinical meaning remains explicit and actionable",
                ],
                "notes": (
                    shared_note
                    + f" 本頁聚焦{topic}，補充頁面專屬的證據判讀。"
                    + " ✅ 臨床結論應結合研究限制審慎運用。"
                ),
            }
        )
    slides.extend(
        [
            {
                "type": "references",
                "title": "References",
                "items": [
                    f"{number}. Author et al. Synthetic Journal 202{number};1:1-10."
                    for number in range(1, 6)
                ],
                "notes": shared_note + " 本頁整理五筆參考來源與查核文獻的方法。",
            },
            {
                "type": "thanks",
                "title": "Thank You",
                "citation": "Author et al — Synthetic Journal 2026",
                "notes": shared_note + " 本頁總結教學內容並邀請聽眾提出問題。",
            },
        ]
    )
    return {
        "meta": {
            "footer_label": "Author et al — Synthetic Journal 2026 | Synthetic topic"
        },
        "slides": slides,
    }


def write_spec(root: Path, spec: dict[str, object]) -> Path:
    path = root / "deck_spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def add_figure(
    spec: dict[str, object], asset: Path, *, caption: str = "Figure 1. Synthetic image.", **extra: object
) -> dict[str, object]:
    notes = str(
        extra.pop(
            "notes",
            "🖼️【圖片說明】此圖為虛構教學影像，呈現研究結果並協助連結臨床判讀。",
        )
    )
    notes += " 本頁補充圖像來源、主要發現與解讀限制，提醒聽眾審慎應用。"
    slide: dict[str, object] = {
        "type": "figure",
        "title": "Research Findings",
        "image": f"final_assets/{asset.name}",
        "caption": caption,
        "notes": notes,
        **extra,
    }
    slides = spec["slides"]
    assert isinstance(slides, list)
    slides[3] = slide
    return slide


def create_synthetic_inversion_fixture(
    root: Path, *, source_size: tuple[int, int] | None = None, source_format: str = "JPEG"
) -> tuple[Path, Path, Path]:
    source_pdf = root / "synthetic-inverted-image.pdf"
    source = patterned_image()
    source = source.resize(source_size or (280, 240))
    raw = ImageOps.invert(source)

    stream = BytesIO()
    raw.save(stream, format=source_format)
    document = pymupdf.open()
    page = document.new_page(width=300, height=240)
    rectangle = pymupdf.Rect(30, 30, 250, 210)
    xref = page.insert_image(rectangle, stream=stream.getvalue())
    document.xref_set_key(xref, "Decode", "[1 0]")
    document.save(source_pdf)
    document.close()

    extracted = root / "extracted"
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPTS / "extract_from_pdf.py"),
            str(source_pdf),
            "--out",
            str(extracted),
            "--dpi",
            "144",
            "--table-dpi",
            "144",
            "--no-contact-sheet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    path = extracted / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest["images"] or not manifest["figures"]:
        raise RuntimeError("Synthetic Decode fixture did not yield an auditable figure.")
    raw_path = extracted / manifest["images"][0]["file"]
    rendered_path = extracted / manifest["figures"][0]["file"]
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
            self.assertTrue(any(
                "inverted raw PDF image" in failure
                or "reverses the grayscale" in failure
                for failure in result["failures"]
            ))

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
