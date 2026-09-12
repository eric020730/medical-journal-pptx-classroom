import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf as fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/medical-journal-to-pptx-classroom/scripts'))
sys.path.insert(0, str(ROOT / 'tools'))
import source_crops as crops
import classroom


class SourceCropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'synthetic.pdf'
        with fitz.open() as doc:
            page = doc.new_page(width=300, height=300)
            for y, text in [(30, 'TABLE 1'), (55, 'Header'), (100, 'First row'),
                            (150, 'Last row'), (180, 'Footnote')]:
                page.insert_text((20, y), text)
            doc.save(self.pdf)
        self.plan = {'pdf': str(self.pdf), 'source_sha256': crops.digest(self.pdf),
                     'dpi': 72, 'expected_assets': ['Table_1'], 'assets': [
                         {'id': 'Table_1', 'type': 'table', 'page': 1,
                          'bbox': [10, 10, 280, 190], 'header_bottom': 70,
                          'splits': [120], 'expected_text': ['TABLE 1', 'Header', 'Last row', 'Footnote']}]}

    def test_split_repeats_header_and_keeps_equal_width(self):
        out = self.root / 'out'
        report = crops.generate(self.plan, out)
        self.assertEqual([x['id'] for x in report['assets']], ['Table_1A', 'Table_1B'])
        with Image.open(out/'Table_1A.png') as a, Image.open(out/'Table_1B.png') as b:
            self.assertEqual(a.width, b.width)
            self.assertEqual(a.crop((16,16,286,76)).tobytes(), b.crop((16,16,286,76)).tobytes())
        with self.assertRaisesRegex(ValueError, 'never overwrite'):
            crops.generate(self.plan, out)

    def test_bad_source_inventory_anchor_and_split_fail_before_output(self):
        plans = []
        p = copy.deepcopy(self.plan); p['source_sha256'] = 'bad'; plans.append(p)
        p = copy.deepcopy(self.plan); p['expected_assets'] += ['Table_2']; plans.append(p)
        p = copy.deepcopy(self.plan); p['assets'][0]['expected_text'] += ['absent']; plans.append(p)
        p = copy.deepcopy(self.plan); p['assets'][0]['splits'] = [98]; plans.append(p)
        for n, p in enumerate(plans):
            out = self.root / str(n)
            with self.subTest(n=n), self.assertRaises(ValueError): crops.generate(p, out)
            self.assertFalse(out.exists())

    def test_partial_text_image_vector_and_out_of_page_rejected(self):
        with fitz.open(self.pdf) as doc:
            page = doc[0]
            for box in [[10, 10, 30, 190], [-1, 0, 300, 300]]:
                with self.assertRaises(ValueError): crops.region(page, box)
            stream = io.BytesIO(); Image.new('RGB', (10,10), 'red').save(stream, format='PNG')
            page.insert_image(fitz.Rect(200,200,250,250), stream=stream.getvalue())
            with self.assertRaisesRegex(ValueError, 'source image'):
                crops.region(page, [210,200,260,260])
            page.draw_rect(fitz.Rect(20,200,100,280))
            with self.assertRaisesRegex(ValueError, 'vector rectangle'):
                crops.region(page, [10,210,110,290])

    def test_wrong_panel_order_rejected(self):
        p = copy.deepcopy(self.plan)
        p['expected_assets'] = ['Figure_1']
        p['assets'] = [{'id':'Figure_1', 'type':'figure', 'expected_labels':['A','B'],
                        'panels':[{'label':'B'}, {'label':'A'}]}]
        with self.assertRaisesRegex(ValueError, 'order mismatch'):
            crops.generate(p, self.root/'out')

    def test_preview_includes_pages_after_six(self):
        pdf = self.root/'nine.pdf'
        with fitz.open() as doc:
            for _ in range(9): doc.new_page(width=100, height=100)
            doc.save(pdf)
        with mock.patch.object(classroom, 'find_binary', return_value=None):
            classroom.preview_contact_sheet(pdf, self.root/'previews')
        self.assertEqual(len(list((self.root/'previews').glob('slide-*.png'))), 9)


if __name__ == '__main__':
    unittest.main()
