#!/usr/bin/env python3
"""Synthetic regression tests for slide-aware multipanel layout selection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from recompose_panels_banded import clean_panel_edges


SCRIPT = Path(__file__).with_name("recompose_panels_banded.py")
POSTPROCESS = Path(__file__).with_name("postprocess_assets.py")


class PanelLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def compose(self, width: int, height: int, *extra: str) -> dict:
        inputs = []
        for index in range(4):
            path = self.directory / f"panel_{index}_{width}x{height}.png"
            Image.new("RGB", (width, height), (25 + 35 * index, 80, 120)).save(path)
            inputs.append(path)

        output = self.directory / f"result_{width}x{height}_{len(list(self.directory.glob('result_*.png')))}.png"
        command = [
            sys.executable,
            str(SCRIPT),
            str(output),
            "--inputs",
            *(str(path) for path in inputs),
            "--labels",
            "A,B,C,D",
            "--geometry",
            str(self.directory / "geometry.json"),
            "--no-trim",
            *extra,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(Path(str(output) + ".postprocess.json").read_text())

    def compose_inputs(self, inputs: list[Path], *extra: str) -> tuple[Path, dict, dict]:
        output = self.directory / f"custom_{len(list(self.directory.glob('custom_*.png')))}.png"
        geometry = self.directory / "custom_geometry.json"
        labels = ",".join(chr(ord("A") + index) for index in range(len(inputs)))
        command = [
            sys.executable,
            str(SCRIPT),
            str(output),
            "--inputs",
            *(str(path) for path in inputs),
            "--labels",
            labels,
            "--geometry",
            str(geometry),
            *extra,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        sidecar = json.loads(Path(str(output) + ".postprocess.json").read_text())
        return output, sidecar, json.loads(geometry.read_text())

    def source_panels(self, source: Image.Image, boxes: list[tuple[int, int, int, int]]) -> list[Path]:
        source_path = self.directory / f"source_{len(list(self.directory.glob('source_*.png')))}.png"
        source.save(source_path)
        paths = []
        for index, box in enumerate(boxes):
            label = chr(ord("A") + index)
            path = self.directory / f"{source_path.stem}_panel_{label}.png"
            source.crop(box).save(path)
            Path(str(path) + ".postprocess.json").write_text(json.dumps({
                "source": str(source_path),
                "crop_box_px": list(box),
                "source_label_placement": "embedded",
                "embedded_label": label,
            }))
            paths.append(path)
        return paths

    def test_portrait_panels_use_single_horizontal_row(self) -> None:
        result = self.compose(600, 800)

        self.assertEqual(result["layout_mode"], "auto")
        self.assertEqual((result["rows"], result["cols"]), (1, 4))
        self.assertEqual(len(result["source_inputs"]), 4)
        candidates = {candidate["cols"]: candidate for candidate in result["layout_candidates"]}
        self.assertGreater(
            candidates[4]["min_panel_area_sq_in"],
            candidates[2]["min_panel_area_sq_in"],
        )

    def test_wide_panels_use_multiple_rows(self) -> None:
        result = self.compose(1600, 400)

        self.assertEqual((result["rows"], result["cols"]), (2, 2))

    def test_explicit_columns_remain_manual_override(self) -> None:
        result = self.compose(600, 800, "--cols", "2")

        self.assertEqual(result["layout_mode"], "manual")
        self.assertEqual((result["rows"], result["cols"]), (2, 2))
        self.assertEqual(len(result["layout_candidates"]), 1)

    def test_nice_style_dimensions_are_respected(self) -> None:
        result = self.compose(
            600,
            800,
            "--slide-box-w-in",
            "12.13",
            "--slide-box-h-in",
            "4.95",
        )

        self.assertEqual((result["rows"], result["cols"]), (1, 4))
        self.assertEqual(result["slide_box_w_in"], 12.13)
        self.assertEqual(result["slide_box_h_in"], 4.95)

    def test_white_gray_and_antialiased_rims_are_removed_with_a_hard_limit(self) -> None:
        image = Image.new("RGB", (120, 100), (8, 8, 8))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 119, 1), fill=(250, 250, 250))
        draw.line((0, 2, 119, 2), fill=(143, 143, 143))
        draw.rectangle((0, 98, 119, 99), fill=(116, 116, 116))
        draw.line((0, 0, 0, 99), fill=(255, 255, 255))
        draw.line((119, 0, 119, 99), fill=(144, 144, 144))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges, {"top": 3, "bottom": 2, "left": 1, "right": 1})
        self.assertEqual(cleaned.size, (118, 95))
        self.assertEqual(cleaned.getpixel((0, 0)), (8, 8, 8))

    def test_single_pdf_boundary_column_is_removed_before_long_dark_canvas(self) -> None:
        for boundary in ((255, 255, 255), (177, 175, 176), (164, 162, 163)):
            with self.subTest(boundary=boundary):
                image = Image.new("RGB", (120, 100), (34, 30, 31))
                ImageDraw.Draw(image).line((119, 0, 119, 99), fill=boundary)

                cleaned, edges = clean_panel_edges(image, max_edge_px=4)

                self.assertEqual(
                    edges,
                    {"top": 0, "bottom": 0, "left": 0, "right": 1},
                )
                self.assertEqual(cleaned.size, (119, 100))
                self.assertEqual(cleaned.getpixel((118, 50)), (34, 30, 31))

    def test_light_image_region_thicker_than_budget_is_not_cropped(self) -> None:
        image = Image.new("RGB", (120, 100), (7, 7, 7))
        ImageDraw.Draw(image).rectangle((0, 0, 119, 11), fill=(245, 245, 245))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges["top"], 0)
        self.assertEqual(cleaned.size, image.size)
        self.assertEqual(cleaned.getpixel((60, 0)), (245, 245, 245))

    def test_bright_anatomy_touching_edge_and_dark_background_are_preserved(self) -> None:
        image = Image.new("RGB", (120, 100), (5, 5, 5))
        ImageDraw.Draw(image).rectangle((42, 0, 68, 24), fill=(250, 250, 250))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges, {"top": 0, "bottom": 0, "left": 0, "right": 0})
        self.assertEqual(cleaned.tobytes(), image.tobytes())

    def test_dark_frame_bordering_brighter_content_is_preserved(self) -> None:
        image = Image.new("RGB", (120, 100), (145, 145, 145))
        ImageDraw.Draw(image).rectangle((0, 0, 2, 99), fill=(18, 18, 18))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges["left"], 0)
        self.assertEqual(cleaned.tobytes(), image.tobytes())

    def test_colored_clinical_scale_at_image_edge_is_never_classified_as_rim(self) -> None:
        image = Image.new("RGB", (120, 100), (4, 4, 4))
        draw = ImageDraw.Draw(image)
        for y in range(image.height):
            draw.line((0, y, 3, y), fill=(min(255, y * 2), 255 - min(255, y * 2), 180))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges["left"], 0)
        self.assertEqual(cleaned.tobytes(), image.tobytes())

    def test_single_figure_trimmer_removes_bounded_dark_canvas_hairline(self) -> None:
        source = self.directory / "single_figure.png"
        output = self.directory / "single_figure_trimmed.png"
        image = Image.new("RGB", (160, 120), (5, 5, 5))
        draw = ImageDraw.Draw(image)
        draw.rectangle((38, 20, 120, 97), fill=(145, 145, 145))
        draw.line((0, 116, 79, 116), fill=(44, 44, 44))
        draw.line((80, 116, 159, 116), fill=(56, 56, 56))
        draw.line((0, 117, 159, 117), fill=(105, 105, 105))
        draw.line((0, 118, 159, 118), fill=(170, 170, 170))
        draw.line((0, 119, 159, 119), fill=(230, 230, 230))
        image.save(source)

        subprocess.run([
            sys.executable,
            str(POSTPROCESS),
            "trim",
            str(source),
            str(output),
            "--asset-type",
            "figure",
            "--bg-aware",
            "off",
        ], check=True, capture_output=True, text=True)

        metadata = json.loads(Path(str(output) + ".postprocess.json").read_text())
        self.assertEqual(metadata["edge_trim_px"]["bottom"], 4)
        self.assertEqual(metadata["max_edge_px"], 4)
        with Image.open(output) as trimmed:
            self.assertLess(trimmed.getpixel((0, trimmed.height - 1))[0], 20)

    def test_table_trimmer_keeps_its_required_margin_without_panel_rim_cleanup(self) -> None:
        source = self.directory / "table.png"
        output = self.directory / "table_trimmed.png"
        image = Image.new("RGB", (160, 120), "white")
        ImageDraw.Draw(image).rectangle((35, 30, 130, 92), outline="black", width=2)
        image.save(source)

        subprocess.run([
            sys.executable,
            str(POSTPROCESS),
            "trim",
            str(source),
            str(output),
            "--asset-type",
            "table",
        ], check=True, capture_output=True, text=True)

        metadata = json.loads(Path(str(output) + ".postprocess.json").read_text())
        self.assertEqual(metadata["margin"], 12)
        self.assertNotIn("edge_trim_px", metadata)

    def test_split_embedded_frame_moves_only_its_own_vertical_panel_pair(self) -> None:
        source = Image.new("RGB", (360, 260), (5, 5, 5))
        draw = ImageDraw.Draw(source)
        draw.rectangle((18, 82, 72, 134), outline=(235, 235, 235), width=3)
        draw.text((37, 98), "A", fill="white")
        draw.rectangle((195, 68, 249, 118), outline=(235, 235, 235), width=3)
        draw.text((214, 84), "B", fill="white")
        draw.rectangle((92, 155, 150, 225), outline=(160, 160, 160), width=2)
        inputs = self.source_panels(source, [
            (0, 0, 180, 126),
            (180, 0, 360, 126),
            (0, 126, 180, 260),
            (180, 126, 360, 260),
        ])

        _, sidecar, _ = self.compose_inputs(inputs, "--no-trim")

        first, second, third, fourth = sidecar["panel_cleanup"]
        self.assertEqual(first["boundary_adjustments"][0]["side"], "bottom")
        self.assertEqual(third["boundary_adjustments"][0]["side"], "top")
        self.assertGreater(first["boundary_adjustments"][0]["adjusted_boundary_px"], 134)
        self.assertEqual(
            first["boundary_adjustments"][0]["effective_crop_box_px"][3],
            third["boundary_adjustments"][0]["effective_crop_box_px"][1],
        )
        self.assertEqual(second["boundary_adjustments"], [])
        self.assertEqual(fourth["boundary_adjustments"], [])
        self.assertEqual(first["label_overwritten_pixels"], 0)

    def test_full_width_lower_panel_keeps_one_boundary_for_both_upper_panels(self) -> None:
        source = Image.new("RGB", (360, 300), (5, 5, 5))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 96, 49, 155), outline=(225, 225, 225), width=3)
        draw.text((14, 113), "A", fill="white")
        draw.rectangle((140, 94, 194, 150), outline=(225, 225, 225), width=3)
        draw.text((158, 110), "B", fill="white")
        draw.text((115, 178), "CBF", fill="white")
        inputs = self.source_panels(source, [
            (0, 0, 130, 145),
            (130, 0, 360, 145),
            (0, 145, 360, 300),
        ])

        _, sidecar, _ = self.compose_inputs(inputs, "--no-trim")

        records = [entry["boundary_adjustments"][0] for entry in sidecar["panel_cleanup"]]
        adjusted = {entry["adjusted_boundary_px"] for entry in records}
        self.assertEqual(len(adjusted), 1)
        self.assertGreater(next(iter(adjusted)), 155)
        self.assertEqual([entry["side"] for entry in records], ["bottom", "bottom", "top"])

    def test_colored_scale_crossing_seam_blocks_automatic_boundary_adjustment(self) -> None:
        source = Image.new("RGB", (180, 250), (5, 5, 5))
        draw = ImageDraw.Draw(source)
        draw.rectangle((10, 77, 63, 132), outline=(235, 235, 235), width=3)
        draw.text((27, 94), "A", fill="white")
        draw.rectangle((140, 120, 145, 155), fill=(240, 30, 70))
        inputs = self.source_panels(source, [
            (0, 0, 180, 120),
            (0, 120, 180, 250),
        ])

        _, sidecar, _ = self.compose_inputs(inputs, "--no-trim")

        self.assertEqual(sidecar["panel_cleanup"][0]["boundary_adjustments"], [])
        self.assertEqual(sidecar["panel_cleanup"][1]["boundary_adjustments"], [])

    def test_embedded_source_label_preserves_all_image_pixels_and_uses_no_duplicate(self) -> None:
        source = self.directory / "embedded_A.png"
        image = Image.new("RGB", (160, 120), (4, 4, 4))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 84, 55, 119), fill=(215, 215, 215))
        draw.text((8, 91), "A", fill=(0, 0, 0))
        image.save(source)
        Path(str(source) + ".postprocess.json").write_text(json.dumps({
            "source_label_placement": "embedded",
            "embedded_label": "A",
        }))

        output, sidecar, geometry = self.compose_inputs([source], "--no-trim")

        self.assertEqual(Image.open(output).convert("RGB").tobytes(), image.tobytes())
        self.assertEqual(sidecar["source_label_policy"], "preserve")
        self.assertFalse(sidecar["native_labels"])
        self.assertEqual(sidecar["embedded_labels"], ["A"])
        self.assertEqual(sidecar["panel_cleanup"][0]["label_overwritten_pixels"], 0)
        self.assertEqual(geometry[output.stem], [])
        self.assertEqual(sidecar["layout_candidates"][0]["band_px"], 0)

    def test_explicit_preserve_policy_works_without_extractor_metadata(self) -> None:
        source = self.directory / "legacy_embedded.png"
        Image.new("RGB", (160, 120), (6, 6, 6)).save(source)

        _, sidecar, _ = self.compose_inputs(
            [source], "--source-label-policy", "preserve", "--no-trim"
        )

        self.assertEqual(sidecar["source_label_policy"], "preserve")
        self.assertFalse(sidecar["native_labels"])

    def test_verified_exterior_label_margin_can_be_removed_without_overwriting(self) -> None:
        source = self.directory / "margin_A.png"
        image = Image.new("RGB", (160, 120), (10, 10, 10))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 15, 135, 80), fill=(170, 170, 170))
        draw.text((9, 100), "A", fill=(255, 255, 255))
        image.save(source)
        Path(str(source) + ".postprocess.json").write_text(json.dumps({
            "source_panel_label": {
                "placement": "external-margin",
                "box_px": [6, 96, 28, 120],
            },
        }))

        _, sidecar, geometry = self.compose_inputs([source], "--no-trim")

        self.assertEqual(sidecar["source_label_policy"], "crop-safe-margin")
        self.assertTrue(sidecar["native_labels"])
        self.assertEqual(sidecar["panel_cleanup"][0]["label_action"], "cropped-exterior-margin")
        self.assertEqual(sidecar["panel_cleanup"][0]["label_margin_crop"]["side"], "bottom")
        self.assertEqual(geometry[next(iter(geometry))][0]["label"], "A")

    def test_exterior_margin_with_image_content_falls_back_to_preservation(self) -> None:
        source = self.directory / "unsafe_margin_A.png"
        image = Image.new("RGB", (160, 120), (8, 8, 8))
        ImageDraw.Draw(image).rectangle((50, 100, 130, 119), fill=(190, 190, 190))
        image.save(source)
        Path(str(source) + ".postprocess.json").write_text(json.dumps({
            "source_panel_label": {
                "placement": "external-margin",
                "box_px": [6, 96, 28, 120],
            },
        }))

        output, sidecar, geometry = self.compose_inputs([source], "--no-trim")

        self.assertEqual(sidecar["source_label_policy"], "preserve")
        self.assertFalse(sidecar["native_labels"])
        self.assertEqual(Image.open(output).getpixel((75, 110)), (190, 190, 190))
        self.assertEqual(geometry[output.stem], [])

    def test_panel_with_solid_corner_mask_is_rejected_against_its_source_crop(self) -> None:
        original_path = self.directory / "verified_source.png"
        image = Image.new("RGB", (160, 120), (5, 5, 5))
        ImageDraw.Draw(image).rectangle((0, 90, 42, 119), fill=(210, 210, 210))
        image.save(original_path)
        masked_path = self.directory / "masked_panel.png"
        ImageDraw.Draw(image).rectangle((0, 90, 42, 119), fill=(0, 0, 0))
        image.save(masked_path)
        Path(str(masked_path) + ".postprocess.json").write_text(json.dumps({
            "source": str(original_path),
            "crop_box_px": [0, 0, 160, 120],
            "source_label_placement": "embedded",
        }))

        result = subprocess.run([
            sys.executable,
            str(SCRIPT),
            str(self.directory / "must_not_exist.png"),
            "--inputs",
            str(masked_path),
            "--labels",
            "A",
            "--geometry",
            str(self.directory / "geometry.json"),
        ], capture_output=True, text=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("solid-color corner overwrite", result.stderr)
        self.assertFalse((self.directory / "must_not_exist.png").exists())


if __name__ == "__main__":
    unittest.main()
