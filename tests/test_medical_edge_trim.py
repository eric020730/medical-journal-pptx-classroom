import sys
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/fixtures/classroom_v46/scripts'))
from recompose_panels_banded import trim

class MedicalTrimTests(unittest.TestCase):
    def test_white_rim_removed_without_changing_interior(self):
        core=Image.new('RGB',(100,80),(30,40,50))
        core.putpixel((50,40),(255,255,255))
        canvas=Image.new('RGB',(107,87),'white');canvas.paste(core,(3,4))
        cleaned=trim(canvas)
        self.assertEqual(cleaned.size,core.size)
        self.assertEqual(cleaned.tobytes(),core.tobytes())

    def test_dark_border_and_internal_white_anatomy_unchanged(self):
        im=Image.new('RGB',(100,100),'black')
        im.paste(Image.new('RGB',(80,80),'white'),(10,10))
        self.assertEqual(trim(im).tobytes(),im.tobytes())
