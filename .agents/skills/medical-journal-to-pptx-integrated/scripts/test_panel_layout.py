#!/usr/bin/env python3
"""Synthetic regression tests for slide-aware multipanel layout selection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


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


if __name__ == "__main__":
    unittest.main()
