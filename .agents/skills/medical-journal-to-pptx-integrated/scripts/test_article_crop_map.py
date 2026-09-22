"""Synthetic caption-bound crop-map regressions; no paper or patient fixtures."""
import argparse
import copy
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import pymupdf as fitz
import article_asset_map as maps
import extract_from_pdf
import image_polarity
import postprocess_assets as post
import source_crops


class ReviewedCropMapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.pdf = self.root / 'synthetic.pdf'
        self.boxes = {1: [10, 10, 215, 195], 2: [230, 10, 435, 195]}
        with fitz.open() as doc:
            page = doc.new_page(width=450, height=300)
            for number, x in [(1, 20), (2, 240)]:
                for y, text in [(30, f'Table {number}: Synthetic values'), (60, 'Header'),
                                (90, 'First row'), (140, 'Last row'), (180, 'Footnote')]:
                    page.insert_text((x, y), text, fontsize=9)
            # The left table has a structural frame. Right table is text-only;
            # same-line captions plus the left frame cause the real detector
            # to omit its independent region. Do not edit the emitted manifest.
            page.draw_rect(fitz.Rect(18, 45, 210, 185))
            doc.save(self.pdf)
        self.extracted = self.root / 'extracted'
        extract_from_pdf.extract(str(self.pdf), str(self.extracted), dpi=72, table_dpi=72)
        self.manifest = self.extracted / 'manifest.json'
        self.manifest_hash = maps.sha256_path(self.manifest)
        self.report = image_polarity.audit_extraction(self.manifest, persist=False)
        self.assertTrue(self.report['ok'], self.report['failures'])
        self.plan = {'pdf': str(self.pdf), 'source_sha256': maps.sha256_path(self.pdf),
                     'dpi': 72, 'expected_assets': ['table1', 'table2'], 'assets': [
            {'id': f'table{n}', 'type': 'table', 'page': 1, 'bbox': self.boxes[n],
             'expected_text': [f'Table {n}:', 'Header', 'Last row', 'Footnote']}
            for n in (1, 2)]}
        self.plan_path = self.root / 'plan.json'
        self.plan_path.write_text(json.dumps(self.plan))
        self.crops = self.root / 'crops'
        source_crops.generate(self.plan, self.crops)
        self.map_path = self.root / 'article-map.json'
        self.spec = self.root / 'spec.json'

    def mapping(self, number=2):
        bbox = self.boxes[number]
        caption_box = [bbox[0], 15, bbox[2], 36]
        with fitz.open(self.pdf) as doc:
            caption = maps.normalize_caption(doc[0].get_text('text', clip=fitz.Rect(caption_box), sort=True))
        return {'schema': maps.SCHEMA, 'source_pdf': str(self.pdf),
                'source_pdf_sha256': maps.sha256_path(self.pdf),
                'extraction_manifest': str(self.manifest),
                'extraction_manifest_sha256': self.manifest_hash,
                'assets': [{'asset_id': f'table:{number}', 'kind': 'table', 'number': number,
                    'caption_evidence': {'page': 1, 'bbox_pt': caption_box,
                        'normalizer': maps.NORMALIZER, 'normalized_text': caption,
                        'normalized_text_sha256': maps.caption_sha256(caption)},
                    'source_bindings': [{'type': maps.CROP_BINDING, 'plan': 'plan.json',
                        'plan_sha256': maps.sha256_path(self.plan_path), 'asset_id': f'table{number}',
                        'page': 1, 'bbox_pt': bbox, 'header_bbox_pt': [bbox[0],10,bbox[2],70]}],
                    'association': {'method': maps.CROP_ASSOCIATION,
                        'review_note': 'Synthetic title, header, last row and footnote reviewed.'}}]}

    def save_map(self, value):
        self.map_path.write_text(json.dumps(value))
        return maps.validate_map(self.map_path)

    def audit(self, images, number=2):
        self.spec.write_text(json.dumps({'meta': {'article_asset_map': self.map_path.name},
            'slides': [{'type': 'figure', 'image': str(path), 'source_asset_id': f'table:{number}',
                        'caption': f'Table {number}. Synthetic values.'} for path in images]}))
        return image_polarity.audit_final_assets(self.spec, self.report)

    def test_omitted_table_authenticates_without_manifest_modification(self):
        manifest = json.loads(self.manifest.read_text())
        self.assertTrue(manifest['tables'])  # legacy left-table extraction remains
        self.assertEqual(len(manifest['tables']), 1)
        self.assertTrue(all(not fitz.Rect(entry['bbox']).contains(fitz.Rect(self.boxes[2]))
                            for entry in manifest['tables']))
        result = self.save_map(self.mapping())
        self.assertTrue(result['ok'], result['failures'])
        result = self.audit([self.crops / 'table2.png'])
        self.assertTrue(result['ok'], result['failures'])
        self.assertEqual(maps.sha256_path(self.manifest), self.manifest_hash)

    def test_same_page_wrong_table_and_extra_roots_fail(self):
        self.save_map(self.mapping())
        result = self.audit([self.crops / 'table1.png'])
        self.assertFalse(result['ok'])
        self.assertTrue(any('exact caption-bound' in error for error in result['failures']))
        # Replayable composite of two authentic crops is still the wrong table.
        final = self.root / 'mixed.png'
        self.compose(final, [self.crops/'table1.png', self.crops/'table2.png'])
        result = self.audit([final])
        self.assertFalse(result['ok'])
        self.assertTrue(any('wrong or mixed source roots' in e for e in result['failures']))
        # An authentic reviewed crop plus a whole-page manifest root is forbidden.
        page = next(r['path'] for r in self.report['verified_references'] if r['kind']=='page')
        self.compose(final, [self.crops/'table2.png', Path(page)])
        result = self.audit([final])
        self.assertFalse(result['ok'])
        self.assertTrue(any('wrong or mixed source roots' in e for e in result['failures']))

        with redirect_stdout(StringIO()):
            post.same_width_command(argparse.Namespace(inputs=[page], out_dir=str(self.root/'page-only')))
        result = self.audit([self.root/'page-only'/Path(page).name])
        self.assertFalse(result['ok'])
        self.assertTrue(any('wrong or mixed source roots' in e for e in result['failures']))

    def test_forged_crop_identity_cannot_hide_same_page_swapped_pixels(self):
        self.save_map(self.mapping())
        wrong = self.crops/'table1.png'
        sidecar = wrong.with_suffix('.png.postprocess.json')
        metadata = json.loads(sidecar.read_text())
        metadata['plan'] = self.plan['assets'][1]
        metadata['output_id'] = 'table2'
        sidecar.write_text(json.dumps(metadata))
        result = self.audit([wrong])
        self.assertFalse(result['ok'])
        self.assertTrue(any('Source crop' in e and 'replay' in e for e in result['failures']),
                        result['failures'])

    def compose(self, final, inputs):
        with redirect_stdout(StringIO()):
            post.recompose_panels_command(argparse.Namespace(
                output=str(final), inputs=[str(p) for p in inputs], composite=None, rows=1, cols=2,
                gap=18, margin=16, panel_height=0, panel_width=0, inset=0,
                edge_white_thr=238, edge_white_frac=.7, edge_light_thr=222, edge_light_frac=.92,
                fit='pad', panel_frame=0, panel_frame_color='', bg='white', threshold=246))

    def test_split_helpers_and_shared_root_dag_keep_exact_table_identity(self):
        self.save_map(self.mapping())
        top, bottom = self.root/'top.png', self.root/'bottom.png'
        with redirect_stdout(StringIO()):
            post.split_table_command(argparse.Namespace(input=str(self.crops/'table2.png'),
                out_a=str(top),out_b=str(bottom),split_y=126,repeat_header_y=76,
                crop_left=0,crop_top=0,crop_right=0,crop_bottom=0,margin=16,threshold=246))
        result = self.audit([top, bottom]); self.assertTrue(result['ok'], result['failures'])
        final = self.root/'shared.png'; self.compose(final,[top,bottom])
        result = self.audit([final]); self.assertTrue(result['ok'], result['failures'])
        # Native source_crops splits also carry the same original plan identity.
        self.plan['assets'][1].update(header_bottom=70,splits=[115])
        self.plan_path.write_text(json.dumps(self.plan))
        out=self.root/'split-crops';source_crops.generate(self.plan,out)
        self.save_map(self.mapping())
        result=self.audit([out/'table2A.png',out/'table2B.png'])
        self.assertTrue(result['ok'],result['failures'])

    def test_wrong_caption_bbox_header_page_and_plan_identity_rejected(self):
        original=self.mapping()
        changes = [
            lambda m:m['assets'][0]['source_bindings'][0].update(asset_id='table1'),
            lambda m:m['assets'][0]['source_bindings'][0].update(page=2),
            lambda m:m['assets'][0]['source_bindings'][0].update(bbox_pt=self.boxes[1]),
            lambda m:m['assets'][0]['source_bindings'][0].update(header_bbox_pt=[230,80,435,190]),
            lambda m:m['assets'][0].update(caption_evidence=self.mapping(1)['assets'][0]['caption_evidence']),
            lambda m:m['assets'][0]['source_bindings'][0].update(plan_sha256='0'*64),
            lambda m:m['assets'][0]['association'].update(method='reviewed-source-binding-v1'),
            lambda m:m['assets'][0]['source_bindings'].append(copy.deepcopy(m['assets'][0]['source_bindings'][0])),
        ]
        for change in changes:
            bad=copy.deepcopy(original);change(bad)
            result=self.save_map(bad);self.assertFalse(result['ok'],bad)

    def test_plan_changes_stale_hash_or_asset_object_and_whole_page_rejected(self):
        original=self.mapping();self.save_map(original)
        self.plan_path.write_text(self.plan_path.read_text()+' ')
        self.assertFalse(maps.validate_map(self.map_path)['ok'])
        # Even after explicitly updating the plan-file hash, old crop roots may
        # not impersonate a newly reviewed asset with changed parameters.
        self.plan['assets'][1]['expected_text'].append('First row')
        self.plan_path.write_text(json.dumps(self.plan));self.save_map(self.mapping())
        result=self.audit([self.crops/'table2.png'])
        self.assertFalse(result['ok'])
        self.assertTrue(any('exact caption-bound' in e for e in result['failures']))
        # Selecting both tables in one broad crop cannot use Table 1's caption.
        self.plan['assets'][0]['bbox']=[10,10,435,195]
        self.plan_path.write_text(json.dumps(self.plan))
        broad=self.mapping(1);binding=broad['assets'][0]['source_bindings'][0]
        binding.update(bbox_pt=[10,10,435,195],header_bbox_pt=[10,10,435,70])
        self.assertFalse(self.save_map(broad)['ok'])

    def test_original_manifest_binding_still_accepts_its_extracted_table(self):
        mapping=self.mapping(1)
        extracted=json.loads(self.manifest.read_text())['tables'][0]
        mapping['assets'][0]['source_bindings']=[{
            'manifest_collection':'tables','manifest_file':extracted['file'],
            'sha256':extracted['sha256'],'page':extracted['page']}]
        mapping['assets'][0]['association']={'method':'reviewed-source-binding-v1',
            'review_note':'Synthetic extracted table compared with the original caption.'}
        self.assertTrue(self.save_map(mapping)['ok'])
        source=self.extracted/extracted['file']
        with redirect_stdout(StringIO()):
            post.same_width_command(argparse.Namespace(inputs=[str(source)],out_dir=str(self.root/'legacy')))
        # same-width CLI takes directory-independent output names.
        final=self.root/'legacy'/source.name
        result=self.audit([final],number=1)
        self.assertTrue(result['ok'],result['failures'])

if __name__=='__main__':
    unittest.main()
