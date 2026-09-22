"""Unsigned local render and human/agent review evidence, separate from automatic QA.

Full delivery requires all three current records: automatic QA, complete rendered
pages, and explicit approved review of the exact render receipt SHA-256. These
records detect changes; they are not signatures or independent proof of inspection.
"""
from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

# Load our exact sibling, even when callers import by file location or another
# installed version happens to be present on sys.path.
import importlib.util
_qa_spec = importlib.util.spec_from_file_location(
    "_render_qa_primitives", Path(__file__).with_name("qa_attestation.py")
)
_qa = importlib.util.module_from_spec(_qa_spec)
_qa_spec.loader.exec_module(_qa)
atomic_write, digest, validator_digest = _qa.atomic_write, _qa.digest, _qa.validator_digest


def receipt_path(pptx: Path) -> Path:
    return pptx.with_name(pptx.name + '.render.json')


def review_path(pptx: Path) -> Path:
    return pptx.with_name(pptx.name + '.visual-review.json')


def metadata() -> dict:
    return {'schema': 1, 'signed': False, 'checked_at': datetime.now(timezone.utc).isoformat()}


def slide_count(pptx: Path) -> int:
    with zipfile.ZipFile(pptx) as archive:
        root = ElementTree.fromstring(archive.read('ppt/presentation.xml'))
    return len(root.findall('./{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/*'))


def artifact(path: Path, base: Path) -> dict:
    return {'path': path.relative_to(base).as_posix(), 'sha256': digest(path)}


def local_path(base: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Invalid render artifact path.')
    path = (base / value).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('Render artifact path escapes deliverable directory.')
    return path


def load_record(path: Path) -> dict:
    record = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(record, dict) or type(record.get('schema')) is not int
            or record['schema'] != 1 or record.get('signed') is not False
            or not isinstance(record.get('checked_at'), str)):
        raise ValueError('Malformed render/review receipt.')
    return record


def verified_artifact(base: Path, entry: object) -> Path:
    if not isinstance(entry, dict) or not re.fullmatch('[0-9a-f]{64}', str(entry.get('sha256', ''))):
        raise ValueError('Malformed render artifact hash.')
    path = local_path(base, entry.get('path'))
    if digest(path) != entry['sha256']:
        raise ValueError('Rendered artifact changed: ' + entry['path'])
    return path


def record_render(pptx: Path, pdf: Path, *, initial: dict, pages: int, previews: dict) -> dict:
    if initial != {'pptx_sha256': digest(pptx), 'validator_sha256': validator_digest()}:
        raise RuntimeError('PPTX or validator changed during rendering; render again.')
    slides = slide_count(pptx)
    if type(pages) is not int or pages <= 0 or pages != slides:
        raise RuntimeError(f'Render page count mismatch: PPTX={slides}, PDF={pages}')
    base = pptx.parent
    images = []
    contact = None
    directory = None
    if previews:
        directory_path = Path(previews['preview_dir'])
        paths = sorted(directory_path.glob('slide-*.jpg'), key=lambda p: int(p.stem.split('-')[-1]))
        if [int(p.stem.split('-')[-1]) for p in paths] != list(range(1, pages + 1)):
            raise RuntimeError('Preview pages must cover every slide exactly once.')
        if previews['preview_pages'] != pages:
            raise RuntimeError('Preview page count mismatch.')
        images = [artifact(path, base) for path in paths]
        contact = artifact(Path(previews['contact_sheet']), base)
        directory = directory_path.relative_to(base).as_posix()
    record = {**metadata(), **initial, 'result': 'passed', 'slides': slides,
              'pdf_pages': pages, 'pdf': artifact(pdf, base), 'preview_pages': len(images),
              'previews': images, 'preview_dir': directory, 'contact_sheet': contact}
    atomic_write(receipt_path(pptx), record)
    return record


def status(pptx: Path) -> dict:
    result = {'ok': False, 'status': 'unverified', 'present': receipt_path(pptx).exists(),
              'preview_pages': 0, 'complete': False, 'visual_review': False, 'reasons': []}
    if not result['present']:
        result['reasons'] = ['No render receipt.']
        return result
    try:
        record = load_record(receipt_path(pptx))
        if record.get('result') != 'passed':
            raise ValueError('The last rendering did not finish successfully.')
        if record.get('pptx_sha256') != digest(pptx) or record.get('validator_sha256') != validator_digest():
            raise ValueError('PPTX or validator changed since rendering.')
        pdf = verified_artifact(pptx.parent, record.get('pdf'))
        if pdf != pptx.with_suffix('.pdf').resolve():
            raise ValueError('Render PDF is not the sibling deliverable.')
        pages = record.get('pdf_pages')
        if type(pages) is not int or pages <= 0 or record.get('slides') != pages:
            raise ValueError('Invalid rendered page counts.')
        previews = record.get('previews')
        if not isinstance(previews, list) or type(record.get('preview_pages')) is not int or record['preview_pages'] != len(previews):
            raise ValueError('Invalid preview count.')
        if previews:
            if len(previews) != pages:
                raise ValueError('Preview coverage is incomplete.')
            directory = local_path(pptx.parent, record.get('preview_dir'))
            paths = [verified_artifact(pptx.parent, item) for item in previews]
            if (len(set(paths)) != pages or any(p.parent != directory for p in paths)
                    or [int(p.stem.split('-')[-1]) for p in paths] != list(range(1, pages + 1))
                    or set(directory.glob('slide-*.jpg')) != set(paths)):
                raise ValueError('Preview inventory changed or is malformed.')
            contact = verified_artifact(pptx.parent, record.get('contact_sheet'))
            if contact != directory / 'contact-sheet.jpg':
                raise ValueError('Invalid contact sheet.')
        elif record.get('preview_dir') is not None or record.get('contact_sheet') is not None:
            raise ValueError('Malformed empty preview inventory.')
        result.update(ok=True, status='current', preview_pages=len(previews), complete=bool(previews),
                      render_receipt_sha256=digest(receipt_path(pptx)))
    except (OSError, ValueError, TypeError, KeyError) as error:
        result.update(status='stale', reasons=[str(error)])
    return result


def validate_evidence(evidence: object, rendered: dict) -> None:
    if not isinstance(evidence, dict):
        raise ValueError('Review evidence must be a JSON object.')
    if evidence.get('render_receipt_sha256') != rendered['render_receipt_sha256']:
        raise ValueError('Review evidence does not bind the current render receipt SHA-256.')
    pages = evidence.get('reviewed_pages')
    if (not isinstance(pages, list) or any(type(page) is not int for page in pages)
            or sorted(pages) != list(range(1, rendered['preview_pages'] + 1))):
        raise ValueError('Review evidence must cover every preview page exactly once.')
    for field in ('reviewer', 'findings'):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            raise ValueError(f'Review evidence requires nonempty {field}.')
    if type(evidence.get('approved')) is not bool:
        raise ValueError('Review evidence requires an explicit boolean approved decision.')


def record_review(pptx: Path, evidence_path: Path) -> dict:
    # Rejected/interrupted review retries cannot leave an earlier approval current.
    atomic_write(review_path(pptx), {**metadata(), 'result': 'in_progress'})
    rendered = status(pptx)
    if not rendered['ok'] or not rendered['complete']:
        raise ValueError('Visual review requires current PDF and all rendered previews.')
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    validate_evidence(evidence, rendered)
    if status(pptx) != rendered:
        raise ValueError('Rendered artifacts changed during visual review recording.')
    record = {**metadata(), 'result': 'passed' if evidence['approved'] else 'failed',
              'evidence': evidence, 'evidence_sha256': digest(evidence_path)}
    atomic_write(review_path(pptx), record)
    return {'ok': evidence['approved'], 'visual_review': evidence['approved'],
            'render_receipt_sha256': rendered['render_receipt_sha256'], 'signed': False}


def review_status(pptx: Path, rendered: dict) -> dict:
    try:
        if not rendered['ok'] or not rendered['complete']:
            raise ValueError('Current complete render is required before visual review.')
        record = load_record(review_path(pptx))
        validate_evidence(record.get('evidence'), rendered)
        if record.get('result') != 'passed' or record['evidence']['approved'] is not True:
            raise ValueError('Visual review is not approved.')
        return {'ok': True, 'status': 'current', 'signed': False}
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {'ok': False, 'status': 'unverified', 'signed': False, 'reasons': [str(error)]}
