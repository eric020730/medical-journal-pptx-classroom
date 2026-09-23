"""Source-native placement: exact pixels, one source scale, authenticated replay."""
import json
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/medical-journal-to-pptx-integrated/scripts'


class SourceNativeTests(unittest.TestCase):
    def setUp(self):
        # Legacy classroom tests import same-named modules from tools/. Keep
        # this suite on the integrated implementations without polluting them.
        self.enterContext(patch.dict(sys.modules))
        self.enterContext(patch.object(sys, 'path', [str(SCRIPTS), *sys.path]))
        for script in SCRIPTS.glob('*.py'):
            sys.modules.pop(script.stem, None)
        global image_polarity, banded
        image_polarity = importlib.import_module('image_polarity')
        banded = importlib.import_module('recompose_panels_banded')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def inputs(self, boxes=None, rim=False):
        authenticated = boxes is None
        boxes = boxes or [(5, 5, 65, 45), (25, 65, 70, 105)]
        source = Image.fromarray(np.random.default_rng(5).integers(20, 180, (180, 260, 3), dtype=np.uint8))
        draw = ImageDraw.Draw(source)
        for index, (x0, y0, x1, y1) in enumerate(boxes):
            if rim:
                draw.rectangle((x0,y0,x0+1,y1-1), fill='white')
            draw.text((x0+8, y1-15), chr(65+index), fill='black')
        path = self.root/'source.png'
        source.save(path)
        reviews = {}
        if authenticated:
            # Review the two independent edges of the horizontal source gutter.
            for edge, coordinate in [('bottom',45),('top',65)]:
                report = self.root/f'{edge}.json'
                command = [sys.executable,str(SCRIPTS/'postprocess_assets.py'),'seam-review',
                           str(path),str(report),str(self.root/f'{edge}.png'),
                           '--axis','y','--band','5','70','--search',str(coordinate),str(coordinate),
                           '--selected',str(coordinate),'--tolerance','0']
                result = subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                reviews[edge] = report
        inputs = []
        for i, box in enumerate(boxes):
            output = self.root/f'panel-{i}.png'
            crop = source.crop(box)
            crop.save(output)
            metadata = {'command':'panel-crop','source':str(path),'crop_box_px':list(box),
                        'source_size_px':list(source.size),'output_size_px':list(crop.size),
                        'asset_type':'figure','intermediate':True,'label_overwritten_pixels':0,
                        'source_panel_label': {'label':chr(65+i), 'placement':'embedded',
                            'status':'present','box_px':[8,crop.height-15,18,crop.height-3],
                            'image_box_px':[0,0,crop.width,crop.height]}}
            Path(str(output)+'.postprocess.json').write_text(json.dumps(metadata))
            if authenticated:
                edge = 'bottom' if i == 0 else 'top'
                command = [sys.executable,str(SCRIPTS/'postprocess_assets.py'),'panel-crop',
                           str(path),str(output),'--box',*map(str,box),'--label',chr(65+i),
                           '--label-box','8',str(crop.height-15),'18',str(crop.height-3),
                           '--image-box','0','0',str(crop.width),str(crop.height),
                           '--seam-review',str(reviews[edge]),'--seam-edge',edge,
                           '--require-seam-edge',edge]
                result = subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            inputs.append(output)
        return inputs

    def compose(self, inputs, *extra, check=True):
        output = self.root/'out.png'
        command = [sys.executable,str(SCRIPTS/'recompose_panels_banded.py'),str(output),
                   '--inputs',*map(str,inputs),'--labels',','.join(chr(65+i) for i in range(len(inputs))),
                   '--layout-template','source-native','--asset-type','clinical-image',
                   '--geometry',str(self.root/'geometry.json'),'--source-label-policy','preserve',*extra]
        result = subprocess.run(command, capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode,0,result.stderr)
            return output,json.loads(Path(str(output)+'.postprocess.json').read_text())
        self.assertNotEqual(result.returncode,0)
        return result.stderr

    def test_cli_exact_pixels_gutters_active_trim_and_replay(self):
        inputs = self.inputs(rim=True)
        out, meta = self.compose(inputs)
        self.assertFalse(meta['native_labels'])
        self.assertEqual(meta['native_label_geometry'],[])
        self.assertEqual(meta['source_native_layout']['scale'],1)
        self.assertTrue(any(c['total_edge_trim_px']['left'] for c in meta['panel_cleanup']))
        with Image.open(self.root/'source.png') as original, Image.open(out) as composed:
            for box, effective in zip(meta['panel_boxes_px'],meta['source_native_layout']['effective_crop_boxes_px']):
                actual=composed.crop((box['x'],box['y'],box['x']+box['w'],box['y']+box['h']))
                expected=original.crop(effective)
                self.assertEqual(actual.size,expected.size)
                self.assertEqual(actual.tobytes(),expected.tobytes())
            self.assertEqual(composed.getpixel((30,50)),(6,20,40))
        self.assertEqual(image_polarity._deterministic_helper_evidence(out,meta),(True,[]))
        self.assertGreater(meta['panel_boxes_px'][1]['y']-meta['panel_boxes_px'][0]['h'],0)

    def test_five_panels_keep_bottom_scale_and_trim_source_origins(self):
        boxes=[(0,0,100,80),(110,0,180,80),(190,0,240,80),(0,90,75,160),(85,90,180,160)]
        paths=self.inputs(boxes)
        metadata=[banded.source_metadata(p) for p in paths]
        panels=[];cleanup=[]
        for path in paths:
            with Image.open(path) as image:
                panels.append(image.crop((1,2,image.width,image.height)))
            cleanup.append({'total_edge_trim_px':{'left':1,'top':2,'right':0,'bottom':0}})
        comp,rects,selected,binding=banded.layout_source_native(panels,metadata,cleanup,[[]]*5,
            (6,20,40),0,12.1,4.85)
        for box,rect,panel in zip(boxes,rects,panels):
            self.assertEqual((rect['w'],rect['h']),panel.size)
            self.assertEqual((rect['x'],rect['y']),(box[0],box[1]))
            self.assertEqual(comp.crop((rect['x'],rect['y'],rect['x']+rect['w'],rect['y']+rect['h'])).tobytes(),panel.tobytes())
        self.assertEqual(binding['union_box_px'],[1,2,240,160])
        self.assertEqual(rects[3]['w'],74)  # never enlarged to fill the final row
        self.assertEqual(rects[3]['y']-rects[0]['h'],12)
        self.assertEqual((selected['rows'],selected['cols']),(2,3))

    def test_single_missing_sidecar_mixed_source_and_unverified_labels_rejected(self):
        paths=self.inputs()
        self.assertIn('at least two',self.compose(paths[:1],check=False))
        sidecar=Path(str(paths[1])+'.postprocess.json');original=sidecar.read_text()
        sidecar.unlink()
        self.assertIn('same source',self.compose(paths,check=False))
        data=json.loads(original)
        other=self.root/'other.png';other.write_bytes((self.root/'source.png').read_bytes())
        data['source']=str(other);sidecar.write_text(json.dumps(data))
        self.assertIn('same source',self.compose(paths,check=False))
        for placement in ('unknown','absent','external-margin'):
            data=json.loads(original);data['source_panel_label']={'label':'B','placement':placement}
            sidecar.write_text(json.dumps(data))
            self.assertIn('embedded',self.compose(paths,check=False))

    def test_modified_pixels_and_overlap_fail_closed(self):
        paths=self.inputs()
        with Image.open(paths[1]) as opened:
            modified=opened.copy();modified.putpixel((25,20),(255,0,0));modified.save(paths[1])
        self.assertIn('authentication failed',self.compose(paths,check=False))
        paths=self.inputs([(5,5,65,45),(5,5,65,45)])
        panels=[Image.open(p).convert('RGB') for p in paths]
        with self.assertRaisesRegex(ValueError,'overlap'):
            banded.authenticate_source_native_inputs(paths,panels,[banded.source_metadata(p) for p in paths])

    def test_source_seam_evidence_is_still_mandatory(self):
        paths=self.inputs([(5,5,65,45),(75,5,130,45)])
        self.assertIn('source-seam evidence',self.compose(paths,check=False))

    def test_replay_rejects_tampered_layout_binding_and_pixels(self):
        out,meta=self.compose(self.inputs())
        for key in ('source_native_layout','panel_boxes_px'):
            modified=json.loads(json.dumps(meta))
            modified.pop(key)
            handled,failures=image_polarity._deterministic_helper_evidence(out,modified)
            self.assertTrue(handled);self.assertTrue(failures)
        with Image.open(out) as opened:
            changed=opened.copy();changed.putpixel((15,15),(255,0,0));changed.save(out)
        self.assertTrue(image_polarity._deterministic_helper_evidence(out,meta)[1])


if __name__=='__main__':
    unittest.main()
