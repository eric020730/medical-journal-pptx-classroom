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

    def test_colored_clinical_scale_at_image_edge_is_never_classified_as_rim(self) -> None:
        image = Image.new("RGB", (120, 100), (4, 4, 4))
        draw = ImageDraw.Draw(image)
        for y in range(image.height):
            draw.line((0, y, 3, y), fill=(min(255, y * 2), 255 - min(255, y * 2), 180))

        cleaned, edges = clean_panel_edges(image, max_edge_px=4)

        self.assertEqual(edges["left"], 0)
        self.assertEqual(cleaned.tobytes(), image.tobytes())

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
