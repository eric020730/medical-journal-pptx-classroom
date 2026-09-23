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


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "medical-journal-to-pptx-integrated"
SKILL_VERSION = (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
SEMANTIC_VERSION = re.search(r"v\d+\.\d+\.\d+", SKILL_VERSION).group(0)
MODES = {
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
    "source_crops": "source_crops.py",
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
    "article_asset_map": "article_asset_map.py",
    "qa_gate": "qa_gate.py",
    "deck_quality": "deck_quality.py",
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


def managed_binary_candidates(name: str, *, operating_system: str | None = None) -> list[Path]:
    system = operating_system or platform.system()
    configured = os.environ.get("MEDICAL_JOURNAL_PPTX_PROJECT_ROOT")
    repository = Path(configured).expanduser().resolve() if configured else SKILL_ROOT.parents[2]
    if not configured and not (repository / "journal").is_file():
        return []
    bootstrap = repository / ".bootstrap"
    if name == "soffice":
        if system == "Darwin":
            return [bootstrap / "libreoffice/LibreOffice.app/Contents/MacOS/soffice"]
        program = bootstrap / "libreoffice/program"
        return [program / "soffice.com", program / "soffice.exe"] if system == "Windows" else [program / "soffice"]
    if name == "pdftoppm":
        executable = "pdftoppm.exe" if system == "Windows" else "pdftoppm"
        home = bootstrap / "pixi-home"
        return [home / "bin" / executable, *sorted(home.glob(f"**/{executable}"))]
    return []


def find_binary(name: str) -> Path | None:
    managed = next((p for p in managed_binary_candidates(name) if p.is_file()), None)
    if managed:
        return managed.resolve()
    override = os.environ.get("MEDICAL_JOURNAL_PPTX_" + name.upper())
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"Configured rendering tool is missing: {candidate}")
        if name == "soffice" and platform.system() == "Windows" and candidate.with_suffix(".com").is_file():
            candidate = candidate.with_suffix(".com")
        return candidate.resolve()
    if name == "soffice" and platform.system() == "Windows":
        discovered = shutil.which("soffice.com") or shutil.which(name)
    else:
        discovered = shutil.which(name)
    candidate = Path(discovered) if discovered else next(
        (p for p in binary_candidates(name) if p.is_file()), None
    )
    if candidate and name == "soffice" and platform.system() == "Windows":
        console = candidate.with_suffix(".com")
        if console.is_file():
            candidate = console
    return candidate.resolve() if candidate else None


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
    import build_deck

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


def preview_contact_sheet(pdf: Path, destination: Path) -> dict[str, Any]:
    """Render every PDF page and build a compact review sheet."""
    from PIL import Image, ImageDraw
    import pymupdf as fitz

    poppler = find_binary("pdftoppm")
    if poppler is None:
        raise RuntimeError("Poppler is required for the final slide-preview quality gate.")
    destination.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as document:
        page_count = len(document)
    if page_count == 0:
        raise ValueError(f"PDF contains no pages: {pdf}")
    prefix = destination / "slide"
    run_checked([
        str(poppler), "-f", "1", "-l", str(page_count), "-r", "96", "-jpeg",
        str(pdf), str(prefix),
    ], capture=True)
    previews = sorted(destination.glob("slide-*.jpg"), key=lambda p: int(p.stem.split("-")[-1]))
    if len(previews) != page_count:
        raise RuntimeError(
            f"Preview page count mismatch: PDF={page_count}, previews={len(previews)}"
        )

    cell_width, cell_height = 360, 240
    columns = min(3, len(previews))
    rows = (len(previews) + columns - 1) // columns
    contact = Image.new("RGB", (columns * cell_width, rows * cell_height), "#edf1f6")
    drawer = ImageDraw.Draw(contact)
    for index, image_path in enumerate(previews):
        with Image.open(image_path) as source:
            thumbnail = source.copy()
            thumbnail.thumbnail((cell_width - 24, cell_height - 42))
        column, row = index % columns, index // columns
        x = column * cell_width + (cell_width - thumbnail.width) // 2
        y = row * cell_height + 10
        contact.paste(thumbnail, (x, y))
        drawer.text(
            (column * cell_width + 12, row * cell_height + cell_height - 24),
            f"Slide {index + 1}", fill="#172033",
        )
    contact_sheet = destination / "contact-sheet.jpg"
    contact.save(contact_sheet, quality=88)
    return {
        "preview_dir": str(destination),
        "contact_sheet": str(contact_sheet),
        "preview_pages": len(previews),
    }


def render_presentation(
    pptx: Path, *, overwrite: bool = False, preview: bool = False
) -> dict[str, Any]:
    import pymupdf
    import render_attestation as receipts
    from qa_attestation import atomic_write, digest, validator_digest

    presentation = pptx.expanduser().resolve()
    if not presentation.is_file():
        raise FileNotFoundError(f"PowerPoint file not found: {presentation}")
    output = presentation.with_suffix(".pdf")
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing PDF: {output}. Pass --overwrite to replace it."
        )
    path = receipts.receipt_path(presentation)
    atomic_write(path, {**receipts.metadata(), "result": "in_progress"})
    try:
        initial = {"pptx_sha256": digest(presentation), "validator_sha256": validator_digest()}
        soffice = find_binary("soffice")
        if soffice is None:
            raise RuntimeError("LibreOffice is unavailable; full rendered delivery is incomplete.")
        # A fresh conversion directory prevents a zero-exit converter from reusing
        # a stale sibling PDF. Keep the old deliverable until conversion succeeds.
        with tempfile.TemporaryDirectory(prefix="medical-journal-libreoffice-") as temporary:
            profile = (Path(temporary) / "profile").as_uri()
            run_checked([
                str(soffice), f"-env:UserInstallation={profile}", "--headless", "--convert-to",
                "pdf", "--outdir", temporary, str(presentation),
            ], capture=True)
            converted = Path(temporary) / output.name
            if not converted.is_file():
                raise RuntimeError("LibreOffice did not create a fresh PDF.")
            with pymupdf.open(converted) as document:
                pages = len(document)
            if pages <= 0 or pages != receipts.slide_count(presentation):
                raise RuntimeError("Rendered PDF page count does not match PPTX slides.")
            rendered_previews = {}
            if preview:
                parent = presentation.parent / ".skill-work" / "previews"
                parent.mkdir(parents=True, exist_ok=True)
                # Each generation owns an empty directory: stale/extra pages from
                # a previous render can never enter its inventory.
                preview_dir = Path(tempfile.mkdtemp(prefix="render-", dir=parent))
                rendered_previews = preview_contact_sheet(converted, preview_dir)
            if initial != {"pptx_sha256": digest(presentation), "validator_sha256": validator_digest()}:
                raise RuntimeError("PPTX or validator changed during rendering; render again.")
            # Copy beside destination first, then replace atomically across volumes.
            descriptor, name = tempfile.mkstemp(prefix=".render-", suffix=".pdf", dir=output.parent)
            os.close(descriptor)
            staged = Path(name)
            try:
                shutil.copyfile(converted, staged)
                staged.replace(output)
            finally:
                staged.unlink(missing_ok=True)
        record = receipts.record_render(presentation, output, initial=initial, pages=pages,
                                         previews=rendered_previews)
        return {"pptx": str(presentation), "pdf": str(output), **rendered_previews,
                "pdf_pages": pages, "preview_pages": record["preview_pages"],
                "render_receipt": str(path), "render_receipt_sha256": digest(path),
                "render_success": True, "visual_review": False, "delivery_ready": False}
    except Exception:
        atomic_write(path, {**receipts.metadata(), "result": "failed"})
        raise


def _synthetic_spec(asset: Path, *, mode: str, manifest: Path) -> dict[str, Any]:
    target = MODES[mode]["minimum_slides"]
    slides: list[dict[str, Any]] = [{
        "type": "title", "title": "Synthetic Medical Research Study",
        "authors": "Synthetic Education Team", "citation": "Fictional Journal, 2026",
        "notes": "📚 此篇為虛構教學示例，不可作為臨床證據。",
    }]
    slides.append({
        "type": "outline", "title": "Learning Outline",
        "items": [
            "1️⃣ Study design — Slides 3–20",
            "2️⃣ Results — Slides 21–37",
            "3️⃣ Figure interpretation and references — Slides 38–39",
        ],
        "notes": "🧭 本頁以繁體中文說明完整教學架構，並提示研究設計、主要結果與臨床應用。",
    })
    slides.append({
        "type": "part", "number": 1, "title": "Study Design",
        "notes": "🔎 本段介紹虛構研究設計與圖表判讀。",
    })
    teaching_topics = [
        "研究問題界定", "疾病負擔評估", "既有治療缺口", "研究假說形成",
        "試驗設計選擇", "收案族群界定", "納入條件判讀", "排除條件判讀",
        "介入措施細節", "對照策略合理性", "隨機分派流程", "盲法執行品質",
        "主要終點定義", "次要終點定義", "樣本數估算", "統計模型選擇",
        "缺失資料處理", "敏感度分析", "基線平衡判讀", "主要結果解讀",
        "次要結果解讀", "效果量臨床意義", "信賴區間判讀", "亞組分析限制",
        "不良事件比較", "依從性與交叉", "追蹤完整程度", "偏差風險評估",
        "外部效度判讀", "證據確定性", "研究優勢整理", "研究限制整理",
        "臨床決策轉譯", "共享決策應用", "未來研究方向", "實務監測需求",
        "資源配置考量", "病人價值整合", "指南一致程度", "結論適用邊界",
    ]
    trailing = 3
    for index in range(target - len(slides) - trailing):
        topic = teaching_topics[index]
        slides.append({
            "type": "content", "title": f"Teaching Point {index + 1}",
            "body": ["Clinical context:", "Synthetic research findings", "→ Teaching takeaway"],
            "notes": (
                f"💡 **Synthetic study**（虛構研究）本頁聚焦{topic}，"
                "僅用於測試完整簡報流程；請說明對應的研究背景與結果方向。"
                " ✅ 教學結論必須結合限制並避免當作臨床證據。"
            ),
        })
    slides.append({
        "type": "figure", "title": "Research Findings",
        "image": f"final_assets/{asset.name}",
        "caption": "Figure 1. Synthetic educational research illustration.",
        "notes": "【圖片說明 — Figure 1】🖼️ 此圖為完全合成的教學圖表，請依序說明視覺元素、比較方向與限制。",
    })
    slides.append({
        "type": "references", "title": "References",
        "items": [
            "Synthetic Education Team. Fictional Journal, 2026;1:1-10.",
            "Example Methods Group. Imaginary Trials, 2025;2:11-20.",
            "Demo Statistics Unit. Teaching Metrics, 2024;3:21-30.",
            "Fictional Review Board. Safe Examples, 2023;4:31-40.",
            "Synthetic Quality Network. Reproducible Demos, 2022;5:41-50.",
        ],
        "notes": "📖 本頁列出五筆完全虛構的參考文獻，僅供端到端流程與版面驗證使用。",
    })
    slides.append({
        "type": "thanks",
        "title": "Thank You",
        "citation": "Synthetic Education Team. Fictional Journal, 2026.",
        "notes": "🙏 感謝聆聽此份完全虛構的教學內容，歡迎提出問題與討論。",
    })
    return {
        "meta": {
            "footer_label": (
                "Synthetic Team et al — Fictional Journal 2026 | Reproducible demo"
            ),
            "extraction_manifest": str(manifest),
        },
        "slides": slides,
    }


def smoke_test(*, workspace: Path, mode: str, style: str, keep: bool = False, render: bool = False) -> dict[str, Any]:
    import build_deck
    import image_polarity
    import qa_gate

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
        figure_sidecar = json.loads(
            Path(str(figure) + ".postprocess.json").read_text(encoding="utf-8")
        )
        if figure_sidecar.get("safety_margin_px") != 16:
            raise RuntimeError("Synthetic final Figure did not receive the default 16 px margin.")
        from PIL import Image

        with Image.open(figure) as rendered_figure:
            expected = figure_sidecar.get("padding_background")
            if (
                rendered_figure.size != tuple(figure_sidecar.get("padded_size_px", []))
                or figure_sidecar.get("padded_size_px", [0, 0])[0]
                != figure_sidecar.get("unpadded_size_px", [0, 0])[0] + 32
                or figure_sidecar.get("padded_size_px", [0, 0])[1]
                != figure_sidecar.get("unpadded_size_px", [0, 0])[1] + 32
                or list(rendered_figure.convert("RGB").getpixel((0, 0))) != expected
            ):
                raise RuntimeError("Synthetic final Figure safety canvas is not exactly 16 px.")
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
        rendered = render_presentation(output, preview=True) if render else None
        return {
            "ok": True,
            "render": rendered,
            "output_pptx": str(output) if keep else None,
            "mode": mode,
            "style": style,
            "slides": built["slides"],
            "image_polarity": True,
            "prebuild_qa": True,
            "postbuild_qa": True,
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
    receipt = commands.add_parser("qa-status", help="Check whether the last local QA receipt is still current")
    receipt.add_argument("pptx", type=Path)
    receipt.add_argument("--spec", type=Path, required=True)
    receipt.add_argument("--require-delivery", action="store_true",
                         help="Require current automatic QA, complete render, and explicit approved visual review")
    builder = commands.add_parser("build", help="Run prebuild QA and build the selected style")
    builder.add_argument("spec", type=Path)
    builder.add_argument("--out", type=Path, required=True)
    for command in (before, completed, builder, receipt):
        command.add_argument("--mode", choices=tuple(MODES), default="full")
        command.add_argument("--style", choices=STYLES, default="standard")
        command.add_argument("--json", action="store_true")
    polarity = commands.add_parser("image-qa", help="Check PDF grayscale and image provenance")
    polarity.add_argument("manifest", type=Path)
    polarity.add_argument("--spec", type=Path)
    polarity.add_argument("--json", action="store_true")
    renderer = commands.add_parser("render", help="Export to PDF and optionally render every slide for review")
    renderer.add_argument("pptx", type=Path)
    renderer.add_argument(
        "--overwrite", action="store_true", help="Replace an existing sibling PDF explicitly"
    )
    renderer.add_argument(
        "--preview", action="store_true", help="Require Poppler previews and a contact sheet"
    )
    renderer.add_argument("--json", action="store_true")
    review = commands.add_parser("visual-review", help="Record explicit review of an exact rendered snapshot")
    review.add_argument("pptx", type=Path)
    review.add_argument("--evidence", type=Path, required=True)
    review.add_argument("--json", action="store_true")
    smoke = commands.add_parser("smoke-test", help="Run a synthetic end-to-end full-deck style test")
    smoke.add_argument("--workspace", type=Path, default=Path.cwd())
    smoke.add_argument("--mode", choices=tuple(MODES), default="full")
    smoke.add_argument("--style", choices=STYLES, default="standard")
    smoke.add_argument("--keep", action="store_true")
    smoke.add_argument("--render", action="store_true", help="Render all slides; does not approve visual quality")
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
    if args.command == "visual-review":
        from render_attestation import record_review

        report = record_review(args.pptx.expanduser().resolve(), args.evidence.expanduser().resolve())
        emit(report, as_json=args.json)
        return 0 if report["ok"] else 1
    if args.command == "qa-status":
        from qa_attestation import status

        report = status(args.pptx.resolve(), args.spec.resolve(), mode=args.mode, style=args.style,
                        require_delivery=args.require_delivery)
        emit(report, as_json=args.json)
        return 0 if report["ok"] else 1
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
            import image_polarity

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
        import qa_gate

        report = qa_gate.check_specification(args.spec.resolve(), mode=args.mode, style=args.style)
        emit(report, as_json=True) if args.json else qa_gate.print_report(report)
        return 0 if report["ok"] else 1
    if args.command == "qa":
        import qa_gate

        report = qa_gate.check_all(args.spec.resolve(), args.pptx.resolve(), mode=args.mode, style=args.style)
        emit(report, as_json=True) if args.json else qa_gate.print_report(report)
        return 0 if report["ok"] else 1
    if args.command == "build":
        import build_deck
        import qa_gate

        before = qa_gate.check_specification(args.spec.resolve(), mode=args.mode, style=args.style)
        if not before["ok"]:
            qa_gate.print_report(before)
            return 1
        payload = build_deck.build(args.spec, args.out, style=args.style)
        emit(payload, as_json=args.json)
        return 0
    if args.command == "image-qa":
        import image_polarity

        report = image_polarity.audit_extraction(args.manifest)
        if args.spec and report["ok"]:
            final = image_polarity.audit_final_assets(args.spec, report)
            report["final_assets"] = final
            report["failures"].extend(final["failures"])
            report["ok"] = not report["failures"]
        emit(report, as_json=args.json)
        return 0 if report["ok"] else 1
    if args.command == "render":
        emit(
            render_presentation(args.pptx, overwrite=args.overwrite, preview=args.preview),
            as_json=args.json,
        )
        return 0
    if args.command == "smoke-test":
        emit(smoke_test(workspace=args.workspace, mode=args.mode, style=args.style, keep=args.keep, render=args.render), as_json=args.json)
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
