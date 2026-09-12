import copy
import io
import json
import subprocess
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

    def test_body_text_cannot_replace_table(self):
        p = copy.deepcopy(self.plan)
        p['assets'][0]['bbox'] = [10, 80, 280, 190]
        with self.assertRaisesRegex(ValueError, 'Missing expected text'):
            crops.generate(p, self.root/'out')

    def test_invalid_page_and_generated_filename_collision_rejected(self):
        p = copy.deepcopy(self.plan)
        p['assets'][0]['page'] = 0
        with self.assertRaisesRegex(ValueError, 'one-based'):
            crops.generate(p, self.root/'out')
        p = copy.deepcopy(self.plan)
        second = copy.deepcopy(p['assets'][0])
        second['id'] = 'Table_1A'; second.pop('splits')
        p['assets'].append(second); p['expected_assets'].append('Table_1A')
        with self.assertRaisesRegex(ValueError, 'filenames collide'):
            crops.generate(p, self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_image_only_export_preserves_content_and_banded_design(self):
        pdf = self.root/'figures.pdf'
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=300)
            for rect, label, color in [(fitz.Rect(20,20,120,120),'A','red'),
                                        (fitz.Rect(150,20,200,170),'B','blue')]:
                stream = io.BytesIO()
                Image.new('RGB', (int(rect.width),int(rect.height)), color).save(stream,format='PNG')
                page.insert_image(rect,stream=stream.getvalue())
                page.insert_text((rect.x1-10,rect.y1+15),label)
            doc.save(pdf)
        plan = {'pdf':str(pdf), 'source_sha256':crops.digest(pdf), 'dpi':72,
                'expected_assets':['Figure_1'], 'assets':[
                    {'id':'Figure_1', 'type':'figure', 'expected_labels':['A','B'],
                     'export_image_panels':True, 'panels':[
                         {'label':'A','page':1,'bbox':[19,19,121,140]},
                         {'label':'B','page':1,'bbox':[149,19,201,190]}]}]}
        out = self.root/'out'
        crops.generate(plan,out)
        with fitz.open(pdf) as doc:
            for label, expected in [('A',(19.7,19.7,120.3,120.3)),('B',(149.7,19.7,200.3,170.3))]:
                path = out/f'Figure_1_{label}_image.png'
                with Image.open(path) as image:
                    reference = crops.render(doc[0],fitz.Rect(expected),72)
                    self.assertEqual(image.size,reference.size)
                    self.assertEqual(image.tobytes(),reference.tobytes())
                meta=json.loads(path.with_suffix('.png.postprocess.json').read_text())
                self.assertEqual(meta['image_region']['original_panel'],label)
                self.assertEqual(meta['margin'],0)
        script=ROOT/'.agents/skills/medical-journal-to-pptx-classroom/scripts/recompose_panels_banded.py'
        subprocess.run([sys.executable,str(script),str(out/'final.png'),'--inputs',
                        str(out/'Figure_1_A_image.png'),str(out/'Figure_1_B_image.png'),
                        '--cols','2','--labels','A,B','--geometry',str(out/'geometry.json'),
                        '--no-trim'],check=True,capture_output=True)
        geometry=json.loads((out/'geometry.json').read_text())['final']
        self.assertEqual([g['label'] for g in geometry],['A','B'])
        self.assertEqual(geometry[0]['fy_center'],geometry[1]['fy_center'])
        with Image.open(out/'final.png') as image:
            self.assertEqual(image.getpixel((0,image.height-1)),(6,20,40))

    def test_image_only_export_rejects_ambiguous_or_absent_images(self):
        with fitz.open(self.pdf) as doc:
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                crops.image_region(doc[0],doc[0].rect)
            stream=io.BytesIO();Image.new('RGB',(10,10),'red').save(stream,format='PNG')
            for x in [20,50]:
                doc[0].insert_image(fitz.Rect(x,200,x+10,210),stream=stream.getvalue())
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                crops.image_region(doc[0],doc[0].rect)

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
