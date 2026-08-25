#!/usr/bin/env python3
"""Self-contained medical-journal workflow runnable from any user workspace."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import build_deck
import image_polarity
import qa_gate


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "medical-journal-to-pptx-integrated"
SKILL_VERSION = (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
SEMANTIC_VERSION = re.search(r"v\d+\.\d+\.\d+", SKILL_VERSION).group(0)
MODES = {
    "lite": {"minimum_slides": 8, "maximum_slides": 16},
    "full": {"minimum_slides": 40, "maximum_slides": 55},
}
STYLES = ("standard", "nice")
PACKAGE_IMPORTS = {
    "PyMuPDF": "pymupdf",
    "python-pptx": "pptx",
    "Pillow": "PIL",
    "pdfplumber": "pdfplumber",
    "numpy": "numpy",
}
SCRIPT_ALIASES = {
    "extract_from_pdf": "extract_from_pdf.py",
    "postprocess_assets": "postprocess_assets.py",
    "build_deck": "build_deck.py",
    "build_deck_standard": "build_deck_standard.py",
    "build_deck_nice": "build_deck_nice.py",
    "recompose_panels_aligned": "recompose_panels_aligned.py",
    "recompose_panels_banded": "recompose_panels_banded.py",
    "add_panel_labels": "add_panel_labels.py",
    "measure_label_gaps": "measure_label_gaps.py",
    "crop_vector_figure": "crop_vector_figure.py",
    "make_demo_paper": "make_demo_paper.py",
    "image_polarity": "image_polarity.py",
    "qa_gate": "qa_gate.py",
    "sonnet_gate": "sonnet_gate.py",
}
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_filename(value: str, *, limit: int = 72) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip(" ._") or "medical-journal"
    if normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        normalized = f"paper_{normalized}"
    return normalized[:limit].rstrip(" ._") or "medical-journal"


def binary_candidates(
    name: str, *, operating_system: str | None = None, environ: Mapping[str, str] | None = None
) -> list[Path]:
    system = operating_system or platform.system()
    values = os.environ if environ is None else environ
    candidates: list[Path] = []
    if system == "Darwin":
        if name == "soffice":
            candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
        candidates.extend(Path(base) / name for base in ("/opt/homebrew/bin", "/usr/local/bin"))
    elif system == "Windows":
        executable = name if name.lower().endswith(".exe") else f"{name}.exe"
        if name == "soffice":
            for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
                if values.get(variable):
                    candidates.append(Path(values[variable]) / "LibreOffice" / "program" / executable)
        if values.get("LOCALAPPDATA"):
            packages = Path(values["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages"
            if packages.is_dir():
                for package in sorted(packages.glob("oschwartz10612.Poppler*")):
                    candidates.extend(package.glob(f"**/Library/bin/{executable}"))
        if values.get("ProgramData"):
            candidates.append(Path(values["ProgramData"]) / "chocolatey" / "bin" / executable)
    return candidates


def find_binary(name: str) -> Path | None:
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered).resolve()
    return next((candidate.resolve() for candidate in binary_candidates(name) if candidate.is_file()), None)


def subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    prefixes = list(dict.fromkeys(
        str(binary.parent)
        for name in ("soffice", "pdftoppm")
        if (binary := find_binary(name)) is not None
    ))
    if prefixes:
        environment["PATH"] = os.pathsep.join([*prefixes, environment.get("PATH", "")])
    environment.setdefault("PYTHONUTF8", "1")
    return environment


def run_checked(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        env=subprocess_environment(),
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    if capture:
        if result.stdout:
            print(result.stdout, end="", file=sys.stderr)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    return result


def resolve_pdf(value: str | Path, workspace: Path) -> Path:
    requested = Path(value).expanduser()
    options = [requested] if requested.is_absolute() else [workspace / requested, Path.cwd() / requested]
    for candidate in options:
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if resolved.suffix.lower() != ".pdf":
            raise ValueError(f"Input must have a .pdf extension: {resolved}")
        with resolved.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise ValueError(f"Input is not a readable PDF: {resolved}")
        return resolved
    raise FileNotFoundError(f"PDF not found: {value}")


def allocate_output(source: Path, directory: Path, *, mode: str, style: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = f"{safe_filename(source.stem)}_{style}_{mode}_{SEMANTIC_VERSION}"
    candidate = directory / f"{base}.pptx"
    number = 2
    while candidate.exists():
        candidate = directory / f"{base}-{number}.pptx"
        number += 1
    return candidate


def initialize_run(
    source: Path, *, workspace: Path, output_dir: Path, mode: str, style: str
) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    run_id = f"{safe_filename(source.stem, limit=38)}-{timestamp}-{style}-{mode}"
    work = workspace / ".skill-work" / run_id
    extracted = work / "extracted"
    assets = work / "final_assets"
    for directory in (work, extracted, assets):
        directory.mkdir(parents=True, exist_ok=False)
    output = allocate_output(source, output_dir, mode=mode, style=style)
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    payload = {
        "run_id": run_id,
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "mode": mode,
        "style": style,
        "source_pdf": str(source),
        "source_sha256": digest,
        "workspace": str(workspace),
        "output_dir": str(output_dir),
        "skill_root": str(SKILL_ROOT),
        "work_dir": str(work),
        "extracted_dir": str(extracted),
        "final_assets_dir": str(assets),
        "deck_spec": str(work / "deck_spec.json"),
        "output_pptx": str(output),
        "output_pdf": str(output.with_suffix(".pdf")),
        "slide_budget": MODES[mode],
        "image_box": build_deck.STYLE_IMAGE_BOXES[style],
    }
    (work / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Integrated Medical Journal Presentation Run",
        "",
        f"- run_id: {run_id}",
        f"- skill_version: {SKILL_VERSION}",
        f"- mode: {mode}",
        f"- style: {style}",
        f"- source_pdf: {source}",
        f"- source_sha256: {digest}",
        "- content_generation: fresh_full_regeneration",
        "- reused_content: none",
        "- omitted_figures: none recorded",
        "- omitted_tables: none recorded",
        "",
    ]
    (work / "RUN_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def doctor(*, strict: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    supported = (3, 11) <= sys.version_info[:2] <= (3, 13)
    checks.append({
        "label": "Python 3.11-3.13",
        "status": "ok" if supported else "error",
        "detail": f"{platform.python_version()} ({sys.executable})",
    })
    for distribution, module in PACKAGE_IMPORTS.items():
        try:
            importlib.import_module(module)
            try:
                installed = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                installed = "importable"
            checks.append({"label": distribution, "status": "ok", "detail": installed})
        except Exception as error:
            checks.append({"label": distribution, "status": "error", "detail": str(error)})
    for executable, label in (("soffice", "LibreOffice"), ("pdftoppm", "Poppler")):
        binary = find_binary(executable)
        checks.append({
            "label": label,
            "status": "ok" if binary else ("error" if strict else "warning"),
            "detail": str(binary) if binary else "Optional PDF export/preview tool not found.",
        })
    errors = sum(check["status"] == "error" for check in checks)
    return {
        "ok": errors == 0,
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "skill_root": str(SKILL_ROOT),
        "python": sys.executable,
        "platform": platform.platform(),
        "checks": checks,
        "errors": errors,
        "warnings": sum(check["status"] == "warning" for check in checks),
    }


def resolve_script(name: str) -> Path:
    normalized = name[:-3] if name.endswith(".py") else name
    if normalized not in SCRIPT_ALIASES:
        raise ValueError(f"Unknown helper {name!r}; expected: {', '.join(sorted(SCRIPT_ALIASES))}")
    script = SKILL_ROOT / "scripts" / SCRIPT_ALIASES[normalized]
    if not script.is_file():
        raise FileNotFoundError(f"Bundled helper missing: {script}")
    return script


def render_presentation(pptx: Path) -> dict[str, Any]:
    presentation = pptx.expanduser().resolve()
    if not presentation.is_file():
        raise FileNotFoundError(f"PowerPoint file not found: {presentation}")
    soffice = find_binary("soffice")
    if soffice is None:
        raise RuntimeError("LibreOffice is unavailable; the verified editable PPTX remains usable.")
    with tempfile.TemporaryDirectory(prefix="medical-journal-libreoffice-") as temporary:
        profile = (Path(temporary) / "profile").as_uri()
        run_checked([
            str(soffice), f"-env:UserInstallation={profile}", "--headless", "--convert-to",
            "pdf", "--outdir", str(presentation.parent), str(presentation),
        ], capture=True)
    output = presentation.with_suffix(".pdf")
    if not output.is_file():
        raise RuntimeError(f"LibreOffice did not create the expected PDF: {output}")
    return {"pptx": str(presentation), "pdf": str(output)}


def _synthetic_spec(asset: Path, *, mode: str, manifest: Path) -> dict[str, Any]:
    target = 10 if mode == "lite" else 40
    slides: list[dict[str, Any]] = [{
        "type": "title", "title": "Synthetic Medical Imaging Study",
        "authors": "Synthetic Education Team", "citation": "Fictional Journal, 2026",
        "notes": "📚 此篇為虛構教學示例，不可作為臨床證據。",
    }]
    if mode == "full":
        slides.append({
            "type": "outline", "title": "Learning Outline",
            "items": ["1️⃣ Study design — Slides 3–20", "2️⃣ Results — Slides 21–39"],
            "notes": "🧭 本頁以繁體中文說明完整教學架構。",
        })
    slides.append({
        "type": "part", "number": 1, "title": "Study Design",
        "notes": "🔎 本段介紹虛構研究設計與影像判讀。",
    })
    trailing = 3 if mode == "full" else 2
    for index in range(target - len(slides) - trailing):
        slides.append({
            "type": "content", "title": f"Teaching Point {index + 1}",
            "body": ["Clinical context:", "Synthetic imaging findings", "→ Teaching takeaway"],
            "notes": "💡 **Synthetic study**（虛構研究）僅用於測試簡報流程。",
        })
    slides.append({
        "type": "figure", "title": "Imaging Findings",
        "image": f"final_assets/{asset.name}",
        "caption": "Figure 1. Fictional educational imaging example.",
        "notes": "【圖片說明 — Figure 1】🖼️ 此圖為虛構教學影像。",
    })
    if mode == "full":
        slides.append({
            "type": "references", "title": "References",
            "items": ["Synthetic Education Team. Fictional Journal, 2026."],
            "notes": "📖 本頁列出虛構文獻，僅供流程測試。",
        })
    slides.append({"type": "thanks", "title": "Thank You", "notes": "🙏 感謝聆聽虛構教學內容。"})
    return {
        "meta": {
            "footer_label": "Synthetic Education Team — Fictional Journal 2026",
            "extraction_manifest": str(manifest),
        },
        "slides": slides,
    }


def smoke_test(*, workspace: Path, mode: str, style: str, keep: bool = False) -> dict[str, Any]:
    from make_demo_paper import create_demo_paper

    private = workspace.expanduser().resolve() / ".skill-work"
    private.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="integrated-smoke-", dir=private)
    root = Path(temporary.name)
    try:
        paper = root / "synthetic-smoke-paper.pdf"
        create_demo_paper(paper)
        extracted = root / "extracted"
        run_checked([
            sys.executable, str(resolve_script("extract_from_pdf")), str(paper), "--out", str(extracted),
        ], capture=True)
        manifest = extracted / "manifest.json"
        polarity = image_polarity.audit_extraction(manifest)
        if not polarity["ok"]:
            raise RuntimeError("Synthetic PDF polarity audit failed: " + "; ".join(polarity["failures"]))
        candidates = [*sorted((extracted / "figures").glob("*.png")), *sorted(extracted.glob("page_*.png"))]
        if not candidates:
            raise RuntimeError("Synthetic extraction did not produce a safe rendered figure.")
        assets = root / "final_assets"
        assets.mkdir()
        figure = assets / "Figure_1.png"
        run_checked([
            sys.executable, str(resolve_script("postprocess_assets")), "trim", str(candidates[0]),
            str(figure), "--asset-type", "figure",
        ], capture=True)
        specification = _synthetic_spec(figure, mode=mode, manifest=manifest)
        spec_path = root / "deck_spec.json"
        spec_path.write_text(json.dumps(specification, ensure_ascii=False, indent=2), encoding="utf-8")
        run_checked([
            sys.executable, str(resolve_script("postprocess_assets")), "audit-final", str(assets),
            "--spec", str(spec_path),
        ], capture=True)
        before = qa_gate.check_specification(spec_path, mode=mode, style=style)
        if not before["ok"]:
            raise RuntimeError("Prebuild QA failed: " + "; ".join(before["failures"]))
        output = root / f"synthetic_{style}_{mode}.pptx"
        built = build_deck.build(spec_path, output, style=style)
        final = qa_gate.check_all(spec_path, output, mode=mode, style=style)
        if not final["ok"]:
            raise RuntimeError("Final QA failed: " + "; ".join(final["failures"]))
        return {
            "ok": True,
            "mode": mode,
            "style": style,
            "slides": built["slides"],
            "image_polarity": True,
            "sonnet_prebuild_qa": True,
            "sonnet_postbuild_qa": True,
            "work_dir": str(root) if keep else None,
        }
    finally:
        if keep:
            temporary._finalizer.detach()
        else:
            temporary.cleanup()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    health = commands.add_parser("doctor", help="Check the portable global runtime")
    health.add_argument("--strict", action="store_true")
    health.add_argument("--json", action="store_true")
    demo = commands.add_parser("demo", help="Generate a fictional, patient-free demonstration PDF")
    demo.add_argument("--out", type=Path, default=Path("synthetic-medical-journal-demo.pdf"))
    demo.add_argument("--json", action="store_true")
    for command in ("init-run", "prepare"):
        task = commands.add_parser(command, help="Initialize a workspace-safe presentation run")
        task.add_argument("pdf")
        task.add_argument("--workspace", type=Path, default=Path.cwd())
        task.add_argument("--output-dir", type=Path)
        task.add_argument("--mode", choices=tuple(MODES), default="full")
        task.add_argument("--style", choices=STYLES, default="standard")
        task.add_argument("--json", action="store_true")
    helper = commands.add_parser("run", help="Execute a bundled image-processing helper")
    helper.add_argument("script")
    helper.add_argument("arguments", nargs=argparse.REMAINDER)
    before = commands.add_parser("qa-spec", help="Run both mandatory prebuild quality gates")
    before.add_argument("spec", type=Path)
    completed = commands.add_parser("qa", help="Run both mandatory finished-deck quality gates")
    completed.add_argument("pptx", type=Path)
    completed.add_argument("--spec", type=Path, required=True)
    builder = commands.add_parser("build", help="Run prebuild QA and build the selected style")
    builder.add_argument("spec", type=Path)
    builder.add_argument("--out", type=Path, required=True)
    for command in (before, completed, builder):
        command.add_argument("--mode", choices=("lite", "full", "smoke"), default="full")
        command.add_argument("--style", choices=STYLES, default="standard")
        command.add_argument("--json", action="store_true")
    polarity = commands.add_parser("image-qa", help="Check PDF grayscale and image provenance")
    polarity.add_argument("manifest", type=Path)
    polarity.add_argument("--spec", type=Path)
    polarity.add_argument("--json", action="store_true")
    renderer = commands.add_parser("render", help="Optionally export a verified PowerPoint to PDF")
    renderer.add_argument("pptx", type=Path)
    renderer.add_argument("--json", action="store_true")
    smoke = commands.add_parser("smoke-test", help="Run a synthetic end-to-end style/mode test")
    smoke.add_argument("--workspace", type=Path, default=Path.cwd())
    smoke.add_argument("--mode", choices=tuple(MODES), default="lite")
    smoke.add_argument("--style", choices=STYLES, default="standard")
    smoke.add_argument("--keep", action="store_true")
    smoke.add_argument("--json", action="store_true")
    return root


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "doctor":
        payload = doctor(strict=args.strict)
        emit(payload, as_json=args.json)
        return 0 if payload["ok"] else 1
    if args.command == "demo":
        from make_demo_paper import create_demo_paper

        destination = args.out.expanduser().resolve()
        if destination.exists():
            raise FileExistsError(
                f"Demonstration PDF already exists: {destination}. Choose a different --out path."
            )
        paper = create_demo_paper(destination)
        emit({"pdf": str(paper), "synthetic": True, "patient_data": False}, as_json=args.json)
        return 0
    if args.command in {"init-run", "prepare"}:
        workspace = args.workspace.expanduser().resolve()
        source = resolve_pdf(args.pdf, workspace)
        output_dir = args.output_dir.expanduser().resolve() if args.output_dir else workspace
        payload = initialize_run(source, workspace=workspace, output_dir=output_dir, mode=args.mode, style=args.style)
        if args.command == "prepare":
            run_checked([
                sys.executable, str(resolve_script("extract_from_pdf")), str(source), "--out", payload["extracted_dir"],
            ], capture=args.json)
            report = image_polarity.audit_extraction(Path(payload["extracted_dir"]) / "manifest.json")
            if not report["ok"]:
                raise RuntimeError("PDF image polarity audit failed: " + "; ".join(report["failures"]))
            payload["extraction_complete"] = True
            payload["image_polarity_audit"] = {
                "checked_figures": report["checked_figures"],
                "unsafe_raw_streams": report["unsafe_raw_streams"],
                "report": report["report"],
            }
        emit(payload, as_json=args.json)
        return 0
    if args.command == "run":
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        return run_checked([sys.executable, str(resolve_script(args.script)), *arguments]).returncode
    if args.command == "qa-spec":
        report = qa_gate.check_specification(args.spec.resolve(), mode=args.mode, style=args.style)
        emit(report, as_json=True) if args.json else qa_gate.print_report(report)
        return 0 if report["ok"] else 1
    if args.command == "qa":
        report = qa_gate.check_all(args.spec.resolve(), args.pptx.resolve(), mode=args.mode, style=args.style)
        emit(report, as_json=True) if args.json else qa_gate.print_report(report)
        return 0 if report["ok"] else 1
    if args.command == "build":
        before = qa_gate.check_specification(args.spec.resolve(), mode=args.mode, style=args.style)
        if not before["ok"]:
            qa_gate.print_report(before)
            return 1
        payload = build_deck.build(args.spec, args.out, style=args.style)
        emit(payload, as_json=args.json)
        return 0
    if args.command == "image-qa":
        report = image_polarity.audit_extraction(args.manifest)
        if args.spec and report["ok"]:
            final = image_polarity.audit_final_assets(args.spec, report)
            report["final_assets"] = final
            report["failures"].extend(final["failures"])
            report["ok"] = not report["failures"]
        emit(report, as_json=args.json)
        return 0 if report["ok"] else 1
    if args.command == "render":
        emit(render_presentation(args.pptx), as_json=args.json)
        return 0
    if args.command == "smoke-test":
        emit(smoke_test(workspace=args.workspace, mode=args.mode, style=args.style, keep=args.keep), as_json=args.json)
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"ERROR: helper exited with status {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
