"""Local, unsigned QA receipts bound to the exact deck, spec and validator code."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validator_digest(root: Path = SKILL_ROOT) -> str:
    files = sorted((root / "scripts").glob("*.py")) + [root / "VERSION", root / "requirements.txt"]
    data = [(path.relative_to(root).as_posix(), digest(path)) for path in files]
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def receipt_path(pptx: Path) -> Path:
    return pptx.with_name(pptx.name + ".qa.json")


def dependency_digest(spec: Path) -> str:
    """Hash the declared source graph without persisting paths or clinical text.

    References are resolved relative to their declaring JSON document, matching
    spec/manifest/provenance semantics. Inventory identities are normalized and
    deduplicated; intermediate sources and their sidecars are followed transitively.
    Optional sidecar absence is recorded too, so adding/removing one invalidates QA.
    This is a change detector; the existing validators still judge source fidelity.
    """
    spec = spec.expanduser().resolve()
    pending: list[tuple[Path, str]] = []
    visited: set[tuple[Path, str]] = set()
    inventory: dict[str, str] = {}

    def identity(path: Path) -> str:
        try:
            return Path(os.path.relpath(path, spec.parent)).as_posix()
        except ValueError:
            # Windows dependencies may live on another drive. The absolute
            # identity remains inside the hashed inventory, never the receipt.
            return path.as_posix()

    def reference(value: Any, base: Path, kind: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Declared QA dependency must be a nonempty path string.")
        path = Path(value).expanduser()
        path = (path if path.is_absolute() else base / path).resolve()
        if kind == "manifest" and path.is_dir():
            path /= "manifest.json"
        pending.append((path, kind))

    def fields(data: dict, base: Path, declarations: dict[str, str]) -> None:
        for key, kind in declarations.items():
            if key in data:
                reference(data[key], base, kind)

    def document(raw: bytes) -> dict:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Declared QA dependency JSON must be an object.")
        return value

    specification = document(spec.read_bytes())
    meta = specification.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("Spec metadata must be an object.")
    fields(meta, spec.parent, {
        "article_asset_map": "map", "panel_crop_plan": "plan", "source_crop_plan": "plan",
        "extraction_manifest": "manifest", "extracted_manifest": "manifest",
        "source_pdf": "file", "logo_path": "file",
    })
    if "logo_path" not in meta:
        pending.append((SKILL_ROOT / "assets" / "dr_leether_logo.png", "file"))
    # QA also supports these two canonical implicit manifest locations. Capture
    # whichever it would use, including later appearance/disappearance via the
    # resulting inventory, while an empty standalone spec remains valid.
    if not any(key in meta for key in ("extraction_manifest", "extracted_manifest")):
        for candidate in (spec.parent / "extracted/manifest.json",
                          spec.parent.parent / "extracted/manifest.json"):
            if candidate.is_file():
                pending.append((candidate.resolve(), "manifest"))
                break
    slides = specification.get("slides", [])
    if not isinstance(slides, list):
        raise ValueError("Spec slides must be a list.")
    for slide in slides:
        if not isinstance(slide, dict):
            raise ValueError("Spec slide must be an object.")
        fields(slide, spec.parent, {"image": "asset"})

    while pending:
        path, kind = pending.pop()
        key = (path, kind)
        if key in visited:
            continue
        visited.add(key)
        try:
            raw = path.read_bytes()
        except OSError as error:
            # Receipts and status diagnostics do not reveal private source names.
            raise ValueError("Declared QA dependency is missing or unreadable.") from error
        inventory[identity(path)] = hashlib.sha256(raw).hexdigest()
        if kind == "file":
            continue
        if kind == "asset":
            sidecar = path.with_name(path.name + ".postprocess.json")
            if sidecar.exists():
                pending.append((sidecar, "sidecar"))
            else:
                inventory[identity(sidecar)] = "absent"
            continue
        data = document(raw)
        if kind in ("map", "plan", "sidecar"):
            fields(data, path.parent, {
                "source_pdf": "file", "pdf": "file",
                "extraction_manifest": "manifest", "extracted_manifest": "manifest",
                "source_crop_plan": "plan", "panel_crop_plan": "plan",
            })
        if kind == "seam":
            fields(data, path.parent, {"source": "asset", "overlay": "file"})
        if kind == "sidecar":
            reviews = []
            if "seam_review" in data:
                reviews.append(data["seam_review"])
            if "seam_reviews" in data:
                edges = data["seam_reviews"]
                if not isinstance(edges, dict) or not set(edges).issubset({"left", "right", "top", "bottom"}):
                    raise ValueError("Provenance seam_reviews must contain known edge keys.")
                reviews.extend(edges.values())
            for review in reviews:
                if not isinstance(review, dict):
                    raise ValueError("Provenance seam review must be an object.")
                fields(review, path.parent, {"report": "seam", "overlay": "file", "source": "asset"})
            fields(data, path.parent, {"source": "asset"})
            if "source_inputs" in data:
                if not isinstance(data["source_inputs"], list):
                    raise ValueError("Provenance source_inputs must be a list.")
                for value in data["source_inputs"]:
                    reference(value, path.parent, "asset")
            if "plan" in data:
                if isinstance(data["plan"], dict):
                    fields(data["plan"], path.parent, {"pdf": "file", "source_pdf": "file"})
                else:
                    reference(data["plan"], path.parent, "plan")
        if kind == "manifest":
            fields(data, path.parent, {"pdf": "file", "source_pdf": "file",
                   "text_file": "file", "hidden_text_review": "file"})
            for collection in ("pages", "images", "figures", "unique_figures", "tables"):
                entries = data.get(collection, [])
                if not isinstance(entries, list):
                    raise ValueError("Extraction dependency collection must be a list.")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("Extraction dependency entry must be an object.")
                    fields(entry, path.parent, {"file": "asset", "render": "asset", "source": "asset"})
    encoded = json.dumps(sorted(inventory.items()), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def snapshot(pptx: Path, spec: Path) -> dict[str, str]:
    return {"pptx_sha256": digest(pptx), "spec_sha256": digest(spec),
            "validator_sha256": validator_digest(),
            "dependencies_sha256": dependency_digest(spec),
            "skill_version": (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()}


def atomic_write(path: Path, record: dict[str, Any]) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".qa-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record_qa(pptx: Path, spec: Path, *, mode: str, style: str,
              validate: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    path = receipt_path(pptx)
    base = {"schema": SCHEMA, "signed": False, "mode": mode, "style": style,
            "checked_at": datetime.now(timezone.utc).isoformat()}
    # Invalidate any earlier pass before running gates, including an interrupted
    # or failed retry on unchanged bytes. No clinical text or paths enter receipts.
    atomic_write(path, {**base, "result": "in_progress"})
    try:
        initial = snapshot(pptx, spec)
        report = validate()
        final = snapshot(pptx, spec)
        if initial != final:
            report["ok"] = False
            report.setdefault("failures", []).append("Files or validator changed during QA; run QA again.")
        record = {**base, **final, "result": "passed" if report["ok"] else "failed",
                  "slides": report.get("slides"), "warning_count": len(report.get("warnings", [])),
                  "failure_count": len(report.get("failures", []))}
        atomic_write(path, record)
        report["attestation"] = {"path": str(path), "result": record["result"], "signed": False}
        return report
    except Exception:
        atomic_write(path, {**base, "result": "failed"})
        raise


def _automatic_status(pptx: Path, spec: Path, *, mode: str = "full", style: str = "standard") -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "status": "unverified", "signed": False,
                              "reasons": [], "requires_full_qa": True}
    path = receipt_path(pptx)
    if not path.exists():
        result["reasons"] = ["No QA receipt; run qa with the original spec."]
        return result
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or type(record.get("schema")) is not int or record["schema"] != SCHEMA:
            raise ValueError("Unsupported receipt schema.")
        if record.get("result") != "passed":
            result.update(status="unverified", reasons=["The last QA did not finish successfully."])
            return result
        if record.get("signed") is not False or not isinstance(record.get("checked_at"), str):
            raise ValueError("Malformed receipt metadata.")
        for name in ("pptx_sha256", "spec_sha256", "validator_sha256"):
            value = record.get(name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Malformed receipt hash.")
        current = snapshot(pptx, spec)
        changed = [name for name, value in {**current, "mode": mode, "style": style}.items() if record.get(name) != value]
        if changed:
            result.update(status="stale", reasons=["Changed: " + ", ".join(changed)])
        else:
            result.update(ok=True, status="current", requires_full_qa=False, checked_at=record["checked_at"])
        return result
    except (OSError, ValueError, TypeError, KeyError) as error:
        result.update(status="unverified", reasons=[str(error)])
        return result


def status(pptx: Path, spec: Path, *, mode: str = "full", style: str = "standard",
           require_delivery: bool = False) -> dict[str, Any]:
    """Expose structural compatibility and a separate strict full-delivery gate."""
    # Also support callers loading this module directly by file location, without
    # placing the skill scripts directory on sys.path (e.g. release validators).
    import importlib.util
    module_spec = importlib.util.spec_from_file_location(
        "_delivery_render_attestation", Path(__file__).with_name("render_attestation.py")
    )
    rendering = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(rendering)
    render_status, review_status = rendering.status, rendering.review_status

    result = _automatic_status(pptx, spec, mode=mode, style=style)
    automatic = dict(result)
    rendered = render_status(pptx)
    reviewed = review_status(pptx, rendered)
    ready = automatic["ok"] and rendered["ok"] and rendered["complete"] and reviewed["ok"]
    result.update(automatic_qa=automatic, render=rendered, visual_review=reviewed,
                  delivery_ready=ready, requires_full_delivery=not ready)
    # Legacy structural receipts remain readable. Once rendering is attempted,
    # however, a stale/failed render cannot be hidden behind a structural pass.
    if rendered["present"] and not rendered["ok"]:
        result.update(ok=False, status="stale", reasons=result["reasons"] + rendered["reasons"])
    if require_delivery and not ready:
        reasons = result["reasons"] + ([] if rendered["complete"] else ["Complete current render/previews required."])
        if not reviewed["ok"]:
            reasons += ["Explicit approved visual review of every current preview page required."]
        result.update(ok=False, status="stale" if result["status"] == "stale" else "incomplete", reasons=reasons)
    return result
