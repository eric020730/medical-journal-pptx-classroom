"""Fail-closed contracts for URL-driven onboarding, without network or model calls."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import codex_setup as setup
import classroom_preflight

VERSIONS = {'PyMuPDF':'1.28.2','python-pptx':'1.0.2','Pillow':'12.0.0','pdfplumber':'0.11.9','numpy':'2.0.0'}

class DependenciesTests(unittest.TestCase):
    def problems(self, versions=VERSIONS):
        with patch.object(setup.importlib.metadata, 'version', side_effect=lambda p: versions[p]), \
             patch.object(setup.importlib, 'import_module'):
            return setup.dependency_problems()

    def test_current_bounds_accepted(self):
        self.assertEqual(self.problems(), [])

    def test_lower_bound_enforced(self):
        self.assertIn('PyMuPDF', self.problems({**VERSIONS, 'PyMuPDF': '1.26.7'}))

    def test_upper_bound_enforced(self):
        self.assertIn('numpy', self.problems({**VERSIONS, 'numpy': '3.0.0'}))

    def test_prerelease_is_not_silently_accepted(self):
        self.assertIn('PyMuPDF', self.problems({**VERSIONS, 'PyMuPDF': '1.28.2rc1'}))

    def test_missing_requirement_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'requirements.txt').write_text('# empty\n')
            self.assertIn('missing_requirement_declarations', setup.dependency_problems(root))

    def test_numeric_equality(self):
        self.assertEqual(setup.numeric_version('1.0'), setup.numeric_version('1'))

class ReadinessTests(unittest.TestCase):
    def report(self, local=None, prefix=None):
        local=local or {'local_status':'LOCAL_PPTX_ONLY','doctor_passed':True,
                        'smoke_test':'passed','optional_missing':['LibreOffice','Poppler']}
        with patch.object(setup.sys, 'prefix', prefix or str(ROOT / '.venv')), \
             patch.object(setup, 'dependency_problems', return_value=[]), \
             patch.object(classroom_preflight, 'collect_report', return_value=local):
            return setup.build_report()

    def test_core_ready_still_requires_skill_read(self):
        report=self.report()
        self.assertEqual(report['state'], 'LOCAL_READY_SKILL_PENDING')
        self.assertEqual(report['skill_read_by_agent'], 'not_attested')
        self.assertEqual(report['account_quota'], 'not_checked')
        self.assertEqual(report['pdf_export'], 'not_tested')

    def test_wrong_environment_blocked(self):
        report=self.report(prefix=str(ROOT / 'not-the-project-venv'))
        self.assertEqual(report['state'], 'BLOCKED')
        self.assertIn('wrong_python_environment', report['issues'])

    def test_failed_pipeline_blocked(self):
        report=self.report({'local_status':'LOCAL_BLOCKED','doctor_passed':True,
                            'smoke_test':'failed','optional_missing':[]})
        self.assertEqual(report['state'], 'BLOCKED')

    def test_report_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as t:
            setup.save_report(self.report(), Path(t))
            r=json.loads((Path(t)/'.skill-work/codex-setup.json').read_text())
            self.assertNotIn(str(ROOT), json.dumps(r))
            self.assertFalse(list((Path(t)/'.skill-work').glob('*.tmp')))

class DistributionTests(unittest.TestCase):
    def test_both_installers_are_in_kit(self):
        from package_release import should_package
        for p in ['CODEX-START.md','setup-codex.sh','setup-codex.ps1','tools/codex_setup.py']:
            self.assertTrue(should_package(Path(p)))

    def test_no_system_install_or_policy_changes(self):
        for name in ('setup-codex.sh','setup-codex.ps1'):
            data=(ROOT/name).read_text().lower()
            for bad in ('sudo ', 'brew install', 'winget install', 'set-executionpolicy',
                        '-executionpolicy', 'invoke-expression', '--insecure', 'curl -k', 'pip install --system'):
                self.assertNotIn(bad, data)

    def test_bootstrap_not_in_release_whitelist(self):
        from package_release import should_package
        for path in ('.bootstrap/cache/private.bin','.bootstrap/python/python.exe'):
            self.assertFalse(should_package(Path(path)))

    def test_checksums_are_hex_and_not_placeholder(self):
        import re
        values=[]
        for name in ('setup-codex.sh','setup-codex.ps1'):
            values.extend(re.findall(r'[a-f0-9]{64}',(ROOT/name).read_text()))
        self.assertEqual(len(values),6)
        self.assertEqual(len(set(values)),6)

if __name__ == '__main__':
    unittest.main()
