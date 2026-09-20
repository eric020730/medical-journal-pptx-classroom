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


def snapshot(pptx: Path, spec: Path) -> dict[str, str]:
    return {"pptx_sha256": digest(pptx), "spec_sha256": digest(spec),
            "validator_sha256": validator_digest(),
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


def status(pptx: Path, spec: Path, *, mode: str = "full", style: str = "standard") -> dict[str, Any]:
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
