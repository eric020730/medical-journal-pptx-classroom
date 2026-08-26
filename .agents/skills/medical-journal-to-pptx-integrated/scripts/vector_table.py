#!/usr/bin/env python3
"""Generate and authenticate PDF-cropped vector tables as EMF assets."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from typing import Any

import pymupdf

import workflow


VECTOR_SUFFIXES = {".emf"}
SIDECAR_SCHEMA = "medical-journal-vector-table-sidecar/v1"
POSTPROCESS_SUFFIX = ".postprocess.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_PADDING_PT = 144.0


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _finite_number(value: Any, *, minimum: float | None = None) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and (minimum is None or float(value) >= minimum)
    )


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(_finite_number(item) for item in value):
        return None
    parsed = [float(item) for item in value]
    return parsed if parsed[2] > parsed[0] and parsed[3] > parsed[1] else None


def _resolve_soffice(explicit: str | Path | None = None) -> Path:
    if explicit is None:
        discovered = workflow.find_binary("soffice")
    else:
        raw = Path(explicit).expanduser()
        discovered = raw.resolve() if raw.is_file() else None
        if discovered is None and len(raw.parts) == 1:
            located = shutil.which(str(raw))
            discovered = Path(located).resolve() if located else None
    if discovered is None or not discovered.is_file():
        raise RuntimeError("LibreOffice soffice is required for vector-table generation/replay.")
    return discovered


def _converter_version(soffice: Path) -> str:
    result = subprocess.run(
        [str(soffice), "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (result.stdout or result.stderr).strip().splitlines()[0]


def canonical_svg(
    pdf_path: Path,
    *,
    page: int,
    requested_bbox: list[float],
    pad_x: float,
    pad_top: float,
    pad_bottom: float,
) -> tuple[bytes, list[float], float]:
    """Return the canonical white-backed SVG for one authenticated PDF crop."""
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.is_file():
        raise ValueError(f"Source PDF is missing: {pdf_path}")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("vector-table page must be a positive integer")
    parsed_bbox = _bbox(requested_bbox)
    if parsed_bbox is None:
        raise ValueError("vector-table requested_bbox_pt must be four finite increasing numbers")
    pads = (pad_x, pad_top, pad_bottom)
    if not all(
        _finite_number(value, minimum=0.0) and float(value) <= MAX_PADDING_PT
        for value in pads
    ):
        raise ValueError(
            f"vector-table padding values must be finite within 0..{MAX_PADDING_PT:g} points"
        )

    with pymupdf.open(pdf_path) as document:
        if page > len(document):
            raise ValueError(f"vector-table page {page} is outside the source PDF")
        pdf_page = document[page - 1]
        x0, y0, x1, y1 = parsed_bbox
        page_rect = pdf_page.rect
        if (
            x0 < page_rect.x0
            or y0 < page_rect.y0
            or x1 > page_rect.x1
            or y1 > page_rect.y1
        ):
            raise ValueError("vector-table requested bbox is outside the source PDF page")
        effective = [
            max(float(page_rect.x0), x0 - float(pad_x)),
            max(float(page_rect.y0), y0 - float(pad_top)),
            min(float(page_rect.x1), x1 + float(pad_x)),
            min(float(page_rect.y1), y1 + float(pad_bottom)),
        ]
        pdf_page.set_cropbox(pymupdf.Rect(*effective))
        svg_text = pdf_page.get_svg_image(matrix=pymupdf.Matrix(1, 1))

    match = re.search(r"<svg\b[^>]*>", svg_text)
    if match is None:
        raise RuntimeError("PyMuPDF did not produce a valid SVG root")
    white_background = (
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>'
    )
    svg_text = svg_text[: match.end()] + white_background + svg_text[match.end() :]
    aspect = (effective[2] - effective[0]) / (effective[3] - effective[1])
    return svg_text.encode("utf-8"), effective, aspect


def _validate_emf(payload: bytes) -> None:
    if len(payload) < 88:
        raise ValueError("EMF output is shorter than its 88-byte header")
    record_type, header_size = struct.unpack_from("<II", payload, 0)
    left, top, right, bottom = struct.unpack_from("<iiii", payload, 8)
    signature = struct.unpack_from("<I", payload, 40)[0]
    declared_size = struct.unpack_from("<I", payload, 48)[0]
    if record_type != 1 or header_size < 88 or signature != 0x464D4520:
        raise ValueError("EMF output has an invalid enhanced-metafile header")
    if declared_size != len(payload):
        raise ValueError("EMF output byte count does not match its header")
    if right <= left or bottom <= top:
        raise ValueError("EMF output has non-positive drawing bounds")


def convert_svg_to_emf(svg_payload: bytes, soffice: Path) -> bytes:
    """Convert canonical SVG bytes with an isolated LibreOffice user profile."""
    soffice = _resolve_soffice(soffice)
    with tempfile.TemporaryDirectory(prefix="mj-vector-table-") as temporary_value:
        temporary = Path(temporary_value)
        profile = temporary / "profile"
        profile.mkdir()
        svg_path = temporary / "vector-table.svg"
        svg_path.write_bytes(svg_payload)
        command = [
            str(soffice),
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--convert-to",
            "emf",
            "--outdir",
            str(temporary),
            str(svg_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        emf_path = temporary / "vector-table.emf"
        if result.returncode != 0 or not emf_path.is_file():
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"LibreOffice SVG-to-EMF conversion failed: {detail}")
        payload = emf_path.read_bytes()
    _validate_emf(payload)
    return payload


def generate_vector_table(
    pdf_path: Path,
    output_path: Path,
    *,
    page: int,
    requested_bbox: list[float],
    pad_x: float = 15.0,
    pad_top: float = 6.0,
    pad_bottom: float = 10.0,
    soffice: str | Path | None = None,
    write_sidecar: bool = True,
) -> dict[str, Any]:
    """Generate one EMF and its typed, replayable provenance sidecar."""
    pdf_path = Path(pdf_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    if output_path.suffix.lower() != ".emf":
        raise ValueError("vector-table output must use the .emf suffix")
    if output_path == pdf_path:
        raise ValueError("vector-table input and output paths must differ")
    soffice_path = _resolve_soffice(soffice)
    svg_payload, effective_bbox, aspect = canonical_svg(
        pdf_path,
        page=page,
        requested_bbox=requested_bbox,
        pad_x=pad_x,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
    )
    emf_payload = convert_svg_to_emf(svg_payload, soffice_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(emf_payload)
    try:
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)

    metadata: dict[str, Any] = {
        "schema": SIDECAR_SCHEMA,
        "command": "vector-table",
        "asset_type": "table",
        "intermediate": False,
        "source": str(pdf_path),
        "source_pdf_sha256": _sha256_file(pdf_path),
        "page": page,
        "requested_bbox_pt": [float(value) for value in requested_bbox],
        "padding_pt": {
            "x": float(pad_x),
            "top": float(pad_top),
            "bottom": float(pad_bottom),
        },
        "effective_bbox_pt": effective_bbox,
        "background_rgb": "#FFFFFF",
        "canonical_svg_sha256": _sha256_bytes(svg_payload),
        "output_sha256": _sha256_bytes(emf_payload),
        "output_size_bytes": len(emf_payload),
        "image_aspect": aspect,
        "converter": {
            "name": "LibreOffice",
            "version": _converter_version(soffice_path),
        },
    }
    if write_sidecar:
        sidecar_path = output_path.with_suffix(output_path.suffix + POSTPROCESS_SUFFIX)
        sidecar_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return metadata


def sidecar_structure_failures(sidecar: dict[str, Any]) -> list[str]:
    """Validate typed vector metadata without performing expensive replay."""
    failures: list[str] = []
    if sidecar.get("schema") != SIDECAR_SCHEMA:
        failures.append("unsupported vector-table sidecar schema")
    if sidecar.get("command") != "vector-table" or sidecar.get("asset_type") != "table":
        failures.append("vector sidecar must declare command='vector-table' and asset_type='table'")
    if sidecar.get("intermediate") is not False or sidecar.get("background_rgb") != "#FFFFFF":
        failures.append("vector table must be final and white-backed")
    if not isinstance(sidecar.get("source"), str) or not sidecar["source"].strip():
        failures.append("vector sidecar source must be a non-empty PDF path")
    if not isinstance(sidecar.get("source_pdf_sha256"), str) or SHA256_RE.fullmatch(
        sidecar["source_pdf_sha256"]
    ) is None:
        failures.append("vector sidecar source_pdf_sha256 must be lowercase SHA-256")
    if not isinstance(sidecar.get("page"), int) or isinstance(sidecar.get("page"), bool) or sidecar["page"] < 1:
        failures.append("vector sidecar page must be a positive integer")
    if _bbox(sidecar.get("requested_bbox_pt")) is None or _bbox(
        sidecar.get("effective_bbox_pt")
    ) is None:
        failures.append("vector sidecar requested/effective bbox metadata is malformed")
    padding = sidecar.get("padding_pt")
    if (
        not isinstance(padding, dict)
        or set(padding) != {"x", "top", "bottom"}
        or not all(
            _finite_number(padding[key], minimum=0.0)
            and float(padding[key]) <= MAX_PADDING_PT
            for key in ("x", "top", "bottom")
        )
    ):
        failures.append("vector sidecar padding_pt is malformed")
    for key in ("canonical_svg_sha256", "output_sha256"):
        if not isinstance(sidecar.get(key), str) or SHA256_RE.fullmatch(sidecar[key]) is None:
            failures.append(f"vector sidecar {key} must be lowercase SHA-256")
    if not isinstance(sidecar.get("output_size_bytes"), int) or isinstance(
        sidecar.get("output_size_bytes"), bool
    ) or sidecar.get("output_size_bytes", 0) <= 0:
        failures.append("vector sidecar output_size_bytes must be a positive integer")
    if not _finite_number(sidecar.get("image_aspect"), minimum=0.000001):
        failures.append("vector sidecar image_aspect must be finite and positive")
    converter = sidecar.get("converter")
    if (
        not isinstance(converter, dict)
        or converter.get("name") != "LibreOffice"
        or not isinstance(converter.get("version"), str)
        or not converter["version"].strip()
    ):
        failures.append("vector sidecar converter metadata is malformed")
    return failures


def replay_vector_table(
    asset: Path,
    sidecar: dict[str, Any],
    *,
    audited_pdf: Path,
    audited_pdf_sha256: str,
    authenticated_pages: set[int],
) -> list[str]:
    """Recompute PDF→SVG→EMF and require exact bytes from trusted inputs."""
    asset = Path(asset).expanduser().resolve()
    audited_pdf = Path(audited_pdf).expanduser().resolve()
    prefix = f"Vector table {asset.name}"
    failures: list[str] = []
    if sidecar.get("schema") != SIDECAR_SCHEMA:
        failures.append(f"{prefix} has an unsupported sidecar schema.")
    if sidecar.get("command") != "vector-table" or sidecar.get("asset_type") != "table":
        failures.append(f"{prefix} must use command='vector-table' and asset_type='table'.")
    if sidecar.get("intermediate") is not False or sidecar.get("background_rgb") != "#FFFFFF":
        failures.append(f"{prefix} must be a final white-backed vector table.")
    source = sidecar.get("source")
    source_path = (
        Path(source).expanduser().resolve()
        if isinstance(source, str) and source.strip()
        else None
    )
    if source_path != audited_pdf:
        failures.append(f"{prefix} source does not equal the audited source PDF.")
    source_hash = sidecar.get("source_pdf_sha256")
    if (
        not isinstance(source_hash, str)
        or SHA256_RE.fullmatch(source_hash) is None
        or source_hash != audited_pdf_sha256
    ):
        failures.append(f"{prefix} source PDF SHA-256 does not match the audited manifest.")
    page = sidecar.get("page")
    if (
        not isinstance(page, int)
        or isinstance(page, bool)
        or page not in authenticated_pages
    ):
        failures.append(f"{prefix} page is not an authenticated extraction page.")
    requested = _bbox(sidecar.get("requested_bbox_pt"))
    effective = _bbox(sidecar.get("effective_bbox_pt"))
    padding = sidecar.get("padding_pt")
    if requested is None or effective is None:
        failures.append(f"{prefix} has malformed requested/effective bbox metadata.")
    if not isinstance(padding, dict) or set(padding) != {"x", "top", "bottom"}:
        failures.append(f"{prefix} has malformed padding metadata.")
        padding = None
    elif not all(
        _finite_number(padding[key], minimum=0.0)
        and float(padding[key]) <= MAX_PADDING_PT
        for key in ("x", "top", "bottom")
    ):
        failures.append(f"{prefix} has invalid padding values.")
        padding = None
    for key in ("canonical_svg_sha256", "output_sha256"):
        if not isinstance(sidecar.get(key), str) or SHA256_RE.fullmatch(sidecar[key]) is None:
            failures.append(f"{prefix} has invalid {key} metadata.")
    if not isinstance(sidecar.get("output_size_bytes"), int) or isinstance(
        sidecar.get("output_size_bytes"), bool
    ) or sidecar.get("output_size_bytes", 0) <= 0:
        failures.append(f"{prefix} has invalid output_size_bytes metadata.")
    if not _finite_number(sidecar.get("image_aspect"), minimum=0.000001):
        failures.append(f"{prefix} has invalid image_aspect metadata.")
    converter = sidecar.get("converter")
    if not isinstance(converter, dict) or converter.get("name") != "LibreOffice" or not isinstance(
        converter.get("version"), str
    ):
        failures.append(f"{prefix} has invalid converter metadata.")
    try:
        actual_payload = asset.read_bytes()
        _validate_emf(actual_payload)
    except (OSError, ValueError) as error:
        failures.append(f"{prefix} is not a valid EMF: {error}.")
        actual_payload = b""
    if actual_payload:
        if sidecar.get("output_size_bytes") != len(actual_payload):
            failures.append(f"{prefix} size does not match its sidecar.")
        if sidecar.get("output_sha256") != _sha256_bytes(actual_payload):
            failures.append(f"{prefix} SHA-256 does not match its sidecar.")
    if failures or requested is None or effective is None or padding is None or not isinstance(page, int):
        return failures
    try:
        svg_payload, recomputed_bbox, recomputed_aspect = canonical_svg(
            audited_pdf,
            page=page,
            requested_bbox=requested,
            pad_x=float(padding["x"]),
            pad_top=float(padding["top"]),
            pad_bottom=float(padding["bottom"]),
        )
        if recomputed_bbox != effective:
            failures.append(f"{prefix} effective bbox does not match deterministic recomputation.")
        if not math.isclose(
            recomputed_aspect, float(sidecar["image_aspect"]), rel_tol=0.0, abs_tol=1e-12
        ):
            failures.append(f"{prefix} aspect ratio does not match deterministic recomputation.")
        if _sha256_bytes(svg_payload) != sidecar.get("canonical_svg_sha256"):
            failures.append(f"{prefix} canonical SVG SHA-256 does not match recomputation.")
        trusted_soffice = _resolve_soffice()
        regenerated = convert_svg_to_emf(svg_payload, trusted_soffice)
        if regenerated != actual_payload:
            failures.append(f"{prefix} fails exact deterministic PDF-to-EMF replay.")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        failures.append(f"{prefix} deterministic replay cannot be completed: {error}.")
    return failures
