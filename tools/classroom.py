#!/usr/bin/env python3
"""Cross-platform launcher, environment checks, and safe classroom run setup."""

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / ".classroom-project.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
SKILL_ROOT = PROJECT_ROOT / ".agents" / "skills" / CONFIG["skill_name"]
SKILL_SCRIPTS = SKILL_ROOT / "scripts"
PAPERS_DIR = PROJECT_ROOT / CONFIG["directories"]["papers"]
OUTPUTS_DIR = PROJECT_ROOT / CONFIG["directories"]["outputs"]
WORK_DIR = PROJECT_ROOT / CONFIG["directories"]["work"]

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
    "recompose_panels_aligned": "recompose_panels_aligned.py",
    "recompose_panels_banded": "recompose_panels_banded.py",
    "add_panel_labels": "add_panel_labels.py",
    "measure_label_gaps": "measure_label_gaps.py",
    "crop_vector_figure": "crop_vector_figure.py",
}

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def ensure_directories() -> None:
    for directory in (PAPERS_DIR, OUTPUTS_DIR, WORK_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def semantic_version() -> str:
    match = re.search(r"v\d+\.\d+\.\d+", CONFIG["upstream_version"])
    if match is None:
        raise ValueError("Project upstream_version has no semantic version.")
    return match.group(0)


def safe_filename(value: str, *, limit: int = 72) -> str:
    """Return a Unicode filename safe on both macOS and Windows."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip(" ._")
    if not normalized:
        normalized = "medical-journal"
    if normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        normalized = f"paper_{normalized}"
    return normalized[:limit].rstrip(" ._") or "medical-journal"


def binary_candidates(
    name: str,
    *,
    operating_system: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[Path]:
    """Find common package-manager locations without depending on a fresh PATH."""
    system = operating_system or platform.system()
    env = os.environ if environ is None else environ
    candidates: list[Path] = []

    if system == "Darwin":
        if name == "soffice":
            candidates.extend(
                [
                    Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
                    Path("/opt/homebrew/bin/soffice"),
                    Path("/usr/local/bin/soffice"),
                ]
            )
        else:
            candidates.extend(
                [Path("/opt/homebrew/bin") / name, Path("/usr/local/bin") / name]
            )

    if system == "Windows":
        executable = name if name.lower().endswith(".exe") else f"{name}.exe"
        if name == "soffice":
            for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
                base = env.get(variable)
                if base:
                    candidates.append(Path(base) / "LibreOffice" / "program" / executable)

        local_app_data = env.get("LOCALAPPDATA")
        if local_app_data:
            winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_root.is_dir():
                for package in sorted(winget_root.glob("oschwartz10612.Poppler*")):
                    candidates.extend(package.glob(f"**/Library/bin/{executable}"))

        program_data = env.get("ProgramData")
        if program_data:
            candidates.append(Path(program_data) / "chocolatey" / "bin" / executable)

        user_profile = env.get("USERPROFILE")
        if user_profile:
            candidates.append(Path(user_profile) / "scoop" / "shims" / executable)

    return candidates


def find_binary(name: str) -> Path | None:
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered).resolve()
    for candidate in binary_candidates(name):
        if candidate.is_file():
            return candidate.resolve()
    return None


def subprocess_environment() -> dict[str, str]:
    """Expose discovered native tools to upstream scripts that call them by name."""
    environment = dict(os.environ)
    prefixes: list[str] = []
    for name in ("soffice", "pdftoppm"):
        binary = find_binary(name)
        if binary is not None:
            directory = str(binary.parent)
            if directory not in prefixes:
                prefixes.append(directory)
    if prefixes:
        environment["PATH"] = os.pathsep.join(
            [*prefixes, environment.get("PATH", "")]
        )
    environment.setdefault("PYTHONUTF8", "1")
    return environment


def run_checked(
    command: list[str], *, capture: bool = False, forward: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=subprocess_environment(),
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=capture,
        )
    except subprocess.CalledProcessError as error:
        if capture:
            if error.stdout:
                print(error.stdout, file=sys.stderr, end="")
            if error.stderr:
                print(error.stderr, file=sys.stderr, end="")
        raise

    if capture and forward:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
    return result


def resolve_pdf(value: str) -> Path:
    requested = Path(value).expanduser()
    if requested.is_absolute():
        options = [requested]
    else:
        options = [PROJECT_ROOT / requested, Path.cwd() / requested, PAPERS_DIR / requested]

    for option in options:
        if not option.is_file():
            continue
        resolved = option.resolve()
        if resolved.suffix.lower() != ".pdf":
            raise ValueError(f"Input must have a .pdf extension: {resolved}")
        with resolved.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise ValueError(f"Input is not a readable PDF: {resolved}")
        return resolved
    raise FileNotFoundError(f"PDF not found: {value}")


def allocate_output(source_pdf: Path, mode: str) -> Path:
    ensure_directories()
    base = f"{safe_filename(source_pdf.stem)}_{mode}_{semantic_version()}"
    candidate = OUTPUTS_DIR / f"{base}.pptx"
    index = 2
    while candidate.exists():
        candidate = OUTPUTS_DIR / f"{base}-{index}.pptx"
        index += 1
    return candidate


def source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_run(source_pdf: Path, mode: str) -> dict[str, Any]:
    ensure_directories()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    run_id = f"{safe_filename(source_pdf.stem, limit=44)}-{timestamp}-{mode}"
    run_directory = WORK_DIR / run_id
    extracted_directory = run_directory / "extracted"
    assets_directory = run_directory / "final_assets"
    for directory in (run_directory, extracted_directory, assets_directory):
        directory.mkdir(parents=True, exist_ok=False)

    output = allocate_output(source_pdf, mode)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "source_pdf": str(source_pdf),
        "source_sha256": source_digest(source_pdf),
        "project_root": str(PROJECT_ROOT),
        "skill_root": str(SKILL_ROOT),
        "work_dir": str(run_directory),
        "extracted_dir": str(extracted_directory),
        "final_assets_dir": str(assets_directory),
        "deck_spec": str(run_directory / "deck_spec.json"),
        "output_pptx": str(output),
        "output_pdf": str(output.with_suffix(".pdf")),
        "upstream_version": CONFIG["upstream_version"],
        "slide_budget": CONFIG["modes"][mode],
    }

    (run_directory / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_lines = [
        "# Classroom Presentation Run",
        "",
        f"- run_id: {run_id}",
        f"- mode: {mode}",
        f"- upstream_version: {CONFIG['upstream_version']}",
        f"- source_pdf: {source_pdf}",
        f"- source_sha256: {payload['source_sha256']}",
        "- content_generation: fresh_full_regeneration",
        "- reused_content: none",
        "- omitted_figures: none recorded",
        "- omitted_tables: none recorded",
        "",
    ]
    (run_directory / "RUN_MANIFEST.md").write_text(
        "\n".join(manifest_lines), encoding="utf-8"
    )
    return payload


def check_result(label: str, status: str, detail: str) -> dict[str, str]:
    return {"label": label, "status": status, "detail": detail}


def detect_codex() -> str | None:
    command = shutil.which("codex")
    if command:
        return command
    if platform.system() == "Darwin":
        for candidate in (
            Path("/Applications/ChatGPT.app"),
            Path("/Applications/Codex.app"),
            Path.home() / "Applications" / "ChatGPT.app",
        ):
            if candidate.exists():
                return str(candidate)
    return None


def environment_report(strict: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    python_version = sys.version_info[:2]
    supported_python = (3, 11) <= python_version <= (3, 13)
    checks.append(
        check_result(
            "Python 3.11-3.13",
            "ok" if supported_python else "error",
            f"{platform.python_version()} ({sys.executable})",
        )
    )

    skill_file = SKILL_ROOT / "SKILL.md"
    checks.append(
        check_result(
            "Repository skill",
            "ok" if skill_file.is_file() else "error",
            str(skill_file),
        )
    )
    version_file = SKILL_ROOT / "VERSION"
    version_detail = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.is_file()
        else "VERSION file is missing"
    )
    checks.append(
        check_result(
            "Upstream v0.2.38",
            "ok" if version_detail == CONFIG["upstream_version"] else "error",
            version_detail,
        )
    )

    for distribution, module_name in PACKAGE_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            try:
                installed = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                installed = "importable"
            checks.append(check_result(distribution, "ok", installed))
        except Exception as error:  # A broken native wheel must also be reported.
            checks.append(check_result(distribution, "error", str(error)))

    ensure_directories()
    for label, directory in (
        ("Source papers", PAPERS_DIR),
        ("Presentation outputs", OUTPUTS_DIR),
        ("Private working files", WORK_DIR),
    ):
        checks.append(
            check_result(
                label,
                "ok" if directory.is_dir() and os.access(directory, os.W_OK) else "error",
                str(directory),
            )
        )

    for name, label, purpose in (
        ("soffice", "LibreOffice", "PDF export and slide rendering"),
        ("pdftoppm", "Poppler", "high-fidelity PDF slide previews"),
    ):
        binary = find_binary(name)
        status = "ok" if binary else ("error" if strict else "warning")
        detail = str(binary) if binary else f"Not found; optional for {purpose}."
        checks.append(check_result(label, status, detail))

    codex = detect_codex()
    checks.append(
        check_result(
            "Codex desktop or CLI",
            "ok" if codex else "warning",
            codex or "Not detected automatically; sign in to the ChatGPT desktop app.",
        )
    )

    errors = [check for check in checks if check["status"] == "error"]
    warnings = [check for check in checks if check["status"] == "warning"]
    return {
        "ok": not errors,
        "platform": platform.platform(),
        "project_root": str(PROJECT_ROOT),
        "python": sys.executable,
        "strict": strict,
        "checks": checks,
        "errors": len(errors),
        "warnings": len(warnings),
    }


def print_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"Medical Journal PPTX Classroom | {CONFIG['upstream_version']}")
    print(f"Platform: {report['platform']}")
    print(f"Project:  {report['project_root']}")
    print()
    for check in report["checks"]:
        tag = {"ok": " OK ", "warning": "WARN", "error": "FAIL"}[check["status"]]
        print(f"[{tag}] {check['label']}: {check['detail']}")
    print()
    print(f"Result: {report['errors']} error(s), {report['warnings']} warning(s)")


def paths_payload() -> dict[str, Any]:
    ensure_directories()
    return {
        "project_root": str(PROJECT_ROOT),
        "skill_name": CONFIG["skill_name"],
        "skill_root": str(SKILL_ROOT),
        "python": sys.executable,
        "papers": str(PAPERS_DIR),
        "outputs": str(OUTPUTS_DIR),
        "work": str(WORK_DIR),
        "soffice": str(binary) if (binary := find_binary("soffice")) else None,
        "pdftoppm": str(binary) if (binary := find_binary("pdftoppm")) else None,
        "upstream_version": CONFIG["upstream_version"],
    }


def resolve_upstream_script(name: str) -> Path:
    normalized = name[:-3] if name.endswith(".py") else name
    if normalized not in SCRIPT_ALIASES:
        valid = ", ".join(sorted(SCRIPT_ALIASES))
        raise ValueError(f"Unknown upstream script {name!r}; expected one of: {valid}")
    script = SKILL_SCRIPTS / SCRIPT_ALIASES[normalized]
    if not script.is_file():
        raise FileNotFoundError(f"Upstream script missing: {script}")
    return script


def preview_contact_sheet(pdf: Path, destination: Path) -> Path:
    from PIL import Image, ImageDraw
    import pymupdf as fitz

    destination.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as document:
        page_count = min(6, len(document))
    if page_count == 0:
        raise ValueError(f"PDF contains no pages: {pdf}")

    poppler = find_binary("pdftoppm")
    preview_images: list[Path] = []
    if poppler:
        prefix = destination / "slide"
        run_checked(
            [
                str(poppler),
                "-f",
                "1",
                "-l",
                str(page_count),
                "-r",
                "96",
                "-jpeg",
                str(pdf),
                str(prefix),
            ],
            capture=True,
        )
        preview_images = sorted(destination.glob("slide-*.jpg"))
    else:
        with fitz.open(pdf) as document:
            for index, page in enumerate(document):
                if index >= page_count:
                    break
                image_path = destination / f"slide-{index + 1:02d}.png"
                page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(image_path)
                preview_images.append(image_path)

    if not preview_images:
        raise RuntimeError("No slide previews were generated.")

    cell_width, cell_height = 360, 240
    columns = min(3, len(preview_images))
    rows = (len(preview_images) + columns - 1) // columns
    contact = Image.new("RGB", (columns * cell_width, rows * cell_height), "#edf1f6")
    drawer = ImageDraw.Draw(contact)
    for index, image_path in enumerate(preview_images):
        with Image.open(image_path) as source:
            thumbnail = source.copy()
            thumbnail.thumbnail((cell_width - 24, cell_height - 42))
        column, row = index % columns, index // columns
        x = column * cell_width + (cell_width - thumbnail.width) // 2
        y = row * cell_height + 10
        contact.paste(thumbnail, (x, y))
        drawer.text((column * cell_width + 12, row * cell_height + cell_height - 24),
                    f"Slide {index + 1}", fill="#172033")
    contact_sheet = destination / "contact-sheet.jpg"
    contact.save(contact_sheet, quality=88)
    return contact_sheet


def render_presentation(pptx: Path, *, preview: bool) -> dict[str, Any]:
    presentation = pptx.expanduser().resolve()
    if not presentation.is_file() or presentation.suffix.lower() != ".pptx":
        raise FileNotFoundError(f"PowerPoint file not found: {pptx}")

    soffice = find_binary("soffice")
    if soffice is None:
        raise RuntimeError(
            "LibreOffice was not found. The PPTX remains usable; rerun the system "
            "installer to enable optional PDF export."
        )

    with tempfile.TemporaryDirectory(prefix="libreoffice-profile-") as temporary:
        profile = (Path(temporary) / "profile").as_uri()
        run_checked(
            [
                str(soffice),
                f"-env:UserInstallation={profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(presentation.parent),
                str(presentation),
            ],
            capture=True,
        )

    output_pdf = presentation.with_suffix(".pdf")
    if not output_pdf.is_file():
        raise RuntimeError(f"LibreOffice did not create the expected PDF: {output_pdf}")

    result: dict[str, Any] = {"pptx": str(presentation), "pdf": str(output_pdf)}
    if preview:
        directory = WORK_DIR / "previews" / safe_filename(presentation.stem)
        result["contact_sheet"] = str(preview_contact_sheet(output_pdf, directory))
        result["preview_dir"] = str(directory)
    return result


def smoke_test(*, keep: bool, render: bool) -> dict[str, Any]:
    ensure_directories()
    smoke_directory = Path(tempfile.mkdtemp(prefix="smoke-", dir=WORK_DIR))
    try:
        from make_demo_paper import create_demo_paper

        paper = smoke_directory / "synthetic-smoke-paper.pdf"
        create_demo_paper(paper)
        extracted = smoke_directory / "extracted"
        run_checked(
            [
                sys.executable,
                str(resolve_upstream_script("extract_from_pdf")),
                str(paper),
                "--out",
                str(extracted),
            ],
            capture=True,
        )
        manifest = extracted / "manifest.json"
        if not manifest.is_file():
            raise RuntimeError("The PDF extractor did not produce manifest.json.")

        sources = [
            *sorted((extracted / "unique").glob("*.png")),
            *sorted((extracted / "figures").glob("*.png")),
            *sorted(extracted.glob("image_*.png")),
            *sorted(extracted.glob("page_*.png")),
        ]
        if not sources:
            raise RuntimeError("The PDF extractor did not produce any figure or page image.")

        asset_directory = smoke_directory / "final_assets"
        asset_directory.mkdir()
        figure = asset_directory / "Figure_1.png"
        run_checked(
            [
                sys.executable,
                str(resolve_upstream_script("postprocess_assets")),
                "trim",
                str(sources[0]),
                str(figure),
                "--asset-type",
                "figure",
            ],
            capture=True,
        )

        spec = {
            "meta": {"footer_label": "Synthetic Education Team — Classroom Demo 2026"},
            "slides": [
                {
                    "type": "title",
                    "title": "Synthetic Classroom Imaging Study",
                    "authors": "Classroom Education Team",
                    "citation": "Synthetic teaching example, 2026",
                    "notes": "📚 這是虛構的教學測試，不能視為真實臨床證據。",
                },
                {
                    "type": "part",
                    "number": 1,
                    "title": "Background and Study Design",
                    "notes": "🧭 本段介紹虛構研究的教學架構。",
                },
                {
                    "type": "content",
                    "title": "Study Design",
                    "body": [
                        "Study population:",
                        "• Synthetic imaging cases for classroom validation",
                        "",
                        "Clinical meaning:",
                        "→ Demonstrates the portable slide-building workflow",
                        "✅ Results are fictional and not clinical evidence",
                    ],
                    "notes": "🔍 **Synthetic study**（虛構研究）用於驗證簡報產生流程。",
                },
                {
                    "type": "figure",
                    "title": "Results: Synthetic Imaging Workflow",
                    "image": "final_assets/Figure_1.png",
                    "caption": "Figure 1. Synthetic classroom demonstration image.",
                    "notes": "🖼️【圖片說明 — Figure 1】此圖為自動產生的虛構教學圖片。",
                },
                {
                    "type": "thanks",
                    "title": "Thank You",
                    "citation": "Synthetic teaching example, 2026",
                    "notes": "🙏 測試完成，接下來可使用經授權的真實期刊論文。",
                },
            ],
        }
        spec_path = smoke_directory / "deck_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        run_checked(
            [
                sys.executable,
                str(resolve_upstream_script("postprocess_assets")),
                "audit-final",
                str(asset_directory),
                "--spec",
                str(spec_path),
            ],
            capture=True,
        )

        output = smoke_directory / "classroom-smoke-test.pptx"
        run_checked(
            [
                sys.executable,
                str(resolve_upstream_script("build_deck")),
                str(spec_path),
                "--out",
                str(output),
            ],
            capture=True,
        )
        run_checked(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "qa_check.py"),
                str(output),
                "--spec",
                str(spec_path),
                "--mode",
                "smoke",
            ],
            capture=True,
        )

        result: dict[str, Any] = {
            "ok": True,
            "pdf_extraction": True,
            "figure_postprocessing": True,
            "asset_audit": True,
            "pptx_generation": True,
            "speaker_notes_and_logo_qa": True,
            "slides": len(spec["slides"]),
            "work_dir": str(smoke_directory) if keep else None,
        }
        if render:
            result["render"] = render_presentation(output, preview=True)
        return result
    finally:
        if not keep:
            shutil.rmtree(smoke_directory, ignore_errors=True)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check Python packages and native tools")
    doctor.add_argument("--strict", action="store_true", help="Require LibreOffice and Poppler")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    paths = subparsers.add_parser("paths", help="Display project-relative runtime paths")
    paths.add_argument("--json", action="store_true")

    for name in ("init-run", "prepare"):
        run_parser = subparsers.add_parser(
            name,
            help="Create a private run" + (" and extract its PDF" if name == "prepare" else ""),
        )
        run_parser.add_argument("pdf")
        run_parser.add_argument("--mode", choices=("lite", "full"), default="lite")
        run_parser.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run", help="Run an upstream v0.2.38 helper script")
    run.add_argument("script")
    run.add_argument("arguments", nargs=argparse.REMAINDER)

    qa = subparsers.add_parser("qa", help="Validate a completed presentation")
    qa.add_argument("pptx")
    qa.add_argument("--spec")
    qa.add_argument("--mode", choices=("lite", "full", "smoke"), default="lite")
    qa.add_argument("--json", action="store_true")

    render = subparsers.add_parser("render", help="Export a presentation to PDF")
    render.add_argument("pptx")
    render.add_argument("--preview", action="store_true")
    render.add_argument("--json", action="store_true")

    smoke = subparsers.add_parser("smoke-test", help="Run an end-to-end synthetic test")
    smoke.add_argument("--keep", action="store_true", help="Keep temporary smoke-test files")
    smoke.add_argument("--render", action="store_true", help="Also verify LibreOffice PDF export")
    smoke.add_argument("--json", action="store_true")

    demo = subparsers.add_parser("demo", help="Create the bundled synthetic practice PDF")
    demo.add_argument("--out", type=Path, default=PAPERS_DIR / "classroom-demo-paper.pdf")

    package = subparsers.add_parser(
        "package", help="Create a privacy-safe classroom release ZIP"
    )
    package.add_argument("--out", type=Path, help="Optional ZIP destination")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)

    if args.command == "doctor":
        report = environment_report(strict=args.strict)
        print_report(report, as_json=args.json)
        return 0 if report["ok"] else 1

    if args.command == "paths":
        payload = paths_payload()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.command in ("init-run", "prepare"):
        source = resolve_pdf(args.pdf)
        payload = initialize_run(source, args.mode)
        if args.command == "prepare":
            run_checked(
                [
                    sys.executable,
                    str(resolve_upstream_script("extract_from_pdf")),
                    str(source),
                    "--out",
                    payload["extracted_dir"],
                ],
                capture=args.json,
            )
            payload["extraction_complete"] = True
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "run":
        arguments = args.arguments
        if arguments and arguments[0] == "--":
            arguments = arguments[1:]
        run_checked([sys.executable, str(resolve_upstream_script(args.script)), *arguments])
        return 0

    if args.command == "qa":
        command = [
            sys.executable,
            str(PROJECT_ROOT / "tools" / "qa_check.py"),
            args.pptx,
            "--mode",
            args.mode,
        ]
        if args.spec:
            command.extend(["--spec", args.spec])
        if args.json:
            command.append("--json")
        run_checked(command)
        return 0

    if args.command == "render":
        payload = render_presentation(Path(args.pptx), preview=args.preview)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "smoke-test":
        payload = smoke_test(keep=args.keep, render=args.render)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("End-to-end classroom smoke test passed.")
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "demo":
        from make_demo_paper import create_demo_paper

        output = args.out.expanduser().resolve()
        create_demo_paper(output)
        print(f"Created synthetic classroom PDF: {output}")
        return 0

    if args.command == "package":
        from package_release import create_release

        release = create_release(args.out)
        for key, value in release.items():
            print(f"{key}: {value}")
        return 0

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"ERROR: command exited with status {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
