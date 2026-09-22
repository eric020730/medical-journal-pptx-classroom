"""Mutation regressions for automatic QA source dependency receipts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.agents/skills/medical-journal-to-pptx-integrated/scripts/qa_attestation.py'
module = importlib.util.spec_from_file_location('dependency_qa_test', SCRIPT)
qa = importlib.util.module_from_spec(module)
module.loader.exec_module(qa)


class DependencyReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.pptx = self.root / 'deck.pptx'
        self.pptx.write_bytes(b'fake deck accepted by mocked validator')
        self.spec = self.root / 'spec.json'
        self.source = self.write('sources/paper.pdf', b'%PDF-source')
        self.crop_pdf = self.write('sources/crop-source.pdf', b'%PDF-crop-source')
        self.original = self.write('extracted/page.png', b'synthetic raw image')
        self.panel = self.write('assets/panel.png', b'synthetic panel')
        self.image = self.write('assets/figure.png', b'synthetic figure')
        self.panel_sidecar = self.json('assets/panel.png.postprocess.json', {
            'source': '../extracted/page.png', 'source_pdf': '../sources/paper.pdf',
            'source_crop_plan': '../plans/crop.json', 'notes': 'not/a/path at all',
        })
        self.sidecar = self.json('assets/figure.png.postprocess.json', {
            'source_inputs': ['panel.png'], 'caption': 'Clinical prose is not a path.'})
        self.manifest = self.json('extracted/manifest.json', {
            'pdf': '../sources/paper.pdf', 'pages': [{'render': 'page.png'}]})
        self.crop_plan = self.json('plans/crop.json', {'pdf': '../sources/crop-source.pdf'})
        self.plan = self.json('plans/panels.json', {'source_crop_plan': 'crop.json', 'assets': []})
        self.mapping = self.json('maps/article.json', {
            'source_pdf': '../sources/paper.pdf', 'extraction_manifest': '../extracted/manifest.json'})
        self.specification = {'meta': {
            'article_asset_map': 'maps/article.json', 'panel_crop_plan': 'plans/panels.json',
            'extraction_manifest': 'extracted/manifest.json'},
            'slides': [{'image': 'assets/figure.png', 'notes': 'arbitrary/prose'}]}
        self.spec.write_text(json.dumps(self.specification))

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def json(self, relative, value):
        return self.write(relative, json.dumps(value).encode())

    def record(self, validator=None):
        return qa.record_qa(self.pptx, self.spec, mode='full', style='standard',
            validate=validator or (lambda: {'ok': True, 'slides': 40, 'failures': [], 'warnings': []}))

    def status(self):
        return qa.status(self.pptx, self.spec)

    def test_every_declared_source_and_transitive_provenance_mutation_invalidates(self):
        for path in (self.image, self.sidecar, self.panel, self.panel_sidecar,
                     self.original, self.manifest, self.source, self.plan,
                     self.mapping, self.crop_plan, self.crop_pdf):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                self.record()
                self.assertTrue(self.status()['ok'])
                path.write_bytes(original + b' ')
                status = self.status()
                self.assertFalse(status['ok'])
                self.assertIn('dependencies_sha256', ' '.join(status['reasons']))
                path.write_bytes(original)

    def test_missing_dependency_fails_closed_and_retry_invalidates_pass(self):
        self.record()
        self.crop_pdf.unlink()
        self.assertFalse(self.status()['ok'])
        with self.assertRaisesRegex(ValueError, 'missing or unreadable'):
            self.record()
        self.assertEqual(json.loads(qa.receipt_path(self.pptx).read_text())['result'], 'failed')

    def test_added_and_removed_sidecars_invalidate(self):
        self.record()
        self.sidecar.unlink()
        self.assertFalse(self.status()['ok'])
        self.record()
        self.json('assets/figure.png.postprocess.json', {'source_inputs': ['panel.png']})
        self.assertFalse(self.status()['ok'])

    def test_sources_changing_during_qa_are_not_attested(self):
        def changing_validator():
            self.image.write_bytes(b'changed during validation')
            return {'ok': True, 'slides': 40, 'failures': [], 'warnings': []}
        self.assertFalse(self.record(changing_validator)['ok'])
        self.assertFalse(self.status()['ok'])

    def test_inventory_is_private_and_follows_only_known_fields(self):
        self.record()
        record = qa.receipt_path(self.pptx).read_text()
        self.assertEqual(len(json.loads(record)['dependencies_sha256']), 64)
        for private in (str(self.root), 'paper.pdf', 'figure.png', 'Clinical prose'):
            self.assertNotIn(private, record)
        self.assertTrue(self.status()['ok'])

    def test_shared_and_cyclic_provenance_is_bounded(self):
        # Full QA rejects invalid provenance cycles; snapshot traversal must still
        # terminate and detect mutations rather than loop or miss another branch.
        self.json('assets/panel.png.postprocess.json', {'source_inputs': ['figure.png', '../extracted/page.png']})
        first = qa.dependency_digest(self.spec)
        self.original.write_bytes(b'changed shared dependency')
        self.assertNotEqual(first, qa.dependency_digest(self.spec))

    def test_empty_spec_and_default_logo_dependency(self):
        self.spec.write_text('{}')
        fake_skill = self.root / 'bundled'
        logo = self.write('bundled/assets/dr_leether_logo.png', b'logo bytes')
        with mock.patch.object(qa, 'SKILL_ROOT', fake_skill):
            before = qa.dependency_digest(self.spec)
            logo.write_bytes(b'changed logo')
            self.assertNotEqual(before, qa.dependency_digest(self.spec))
            logo.unlink()
            with self.assertRaisesRegex(ValueError, 'missing or unreadable'):
                qa.dependency_digest(self.spec)

    def test_malformed_declared_paths_fail_closed(self):
        for field in ('article_asset_map', 'panel_crop_plan', 'extraction_manifest', 'source_pdf'):
            with self.subTest(field=field):
                self.spec.write_text(json.dumps({'meta': {field: ''}}))
                with self.assertRaises(ValueError):
                    self.record()

    def test_seam_report_overlay_and_source_mutations_invalidate(self):
        source = self.write('reviews/source.png', b'seam source')
        overlay = self.write('reviews/overlay.png', b'seam overlay')
        report = self.json('reviews/report.json', {
            'source': 'source.png', 'overlay': 'overlay.png',
            'findings': 'This arbitrary/prose must never be interpreted as a path.'})
        for field, binding in (
            ('seam_reviews', {'left': {'report': '../reviews/report.json'}}),
            ('seam_review', {'report': '../reviews/report.json'}),
        ):
            self.json('assets/figure.png.postprocess.json', {
                'source_inputs': ['panel.png'], field: binding})
            for path in (report, overlay, source):
                with self.subTest(field=field, dependency=path.name):
                    original = path.read_bytes()
                    self.record()
                    path.write_bytes(original + b' ')
                    self.assertFalse(self.status()['ok'])
                    path.write_bytes(original)
            self.record()
            report.unlink()
            self.assertFalse(self.status()['ok'])
            report.write_text(json.dumps({'source': 'source.png', 'overlay': 'overlay.png'}))

    def test_old_receipt_without_dependency_binding_is_stale(self):
        self.record()
        path = qa.receipt_path(self.pptx)
        record = json.loads(path.read_text())
        del record['dependencies_sha256']
        path.write_text(json.dumps(record))
        self.assertEqual(self.status()['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
