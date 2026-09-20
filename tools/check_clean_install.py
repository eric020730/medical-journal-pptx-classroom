#!/usr/bin/env python3
"""Exercise the real installer and both deck styles in a new isolated runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "medical-journal-to-pptx-integrated"


def minimum_constraints(requirements: str) -> str:
    pins = []
    for line in requirements.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)>=(\d+(?:\.\d+)*),<[^\s]+", line)
        if not match:
            raise ValueError(f"Cannot derive an exact minimum for requirement: {line}")
        pins.append(f"{match[1]}=={match[2]}")
    return "\n".join(pins) + "\n"


def check(profile: str, base: Path) -> dict:
    # A unique child guarantees that a previous environment cannot mask missing
    # dependencies. All installer writes stay below the supplied test directory.
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"clean-{profile}-", dir=base) as directory:
        root = Path(directory).resolve()
        target = root / "skills"
        runtime = root / "runtime" / NAME / "venv"
        environment = dict(os.environ)
        for key in ("MEDICAL_JOURNAL_PPTX_PYTHON", "MEDICAL_JOURNAL_PPTX_RUNTIME", "PYTHONPATH", "PIP_CONSTRAINT", "PIP_REQUIREMENT", "PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
            environment.pop(key, None)
        environment.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1", MEDICAL_JOURNAL_PPTX_RUNTIME=str(runtime))
        if profile == "minimum":
            constraints = root / "minimum.txt"
            requirements = ROOT / ".agents" / "skills" / NAME / "requirements.txt"
            constraints.write_text(minimum_constraints(requirements.read_text(encoding="utf-8")), encoding="utf-8")
            # pip splits this environment option on whitespace. All child
            # processes run in root, so use the space-free relative filename.
            environment["PIP_CONSTRAINT"] = constraints.name

        def run(*args: object, capture: bool = False):
            return subprocess.run([str(arg) for arg in args], cwd=root, env=environment,
                                  check=True, text=True, encoding="utf-8", capture_output=capture)

        installer = ROOT / "install-global.py"
        unrelated = target / "unrelated-skill" / "keep.txt"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("preserve", encoding="utf-8")
        run(sys.executable, installer, "install", "--target", target, "--runtime-dir", runtime, "--json")
        python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(python, "-m", "pip", "check")
        packages = json.loads(run(python, "-m", "pip", "list", "--format=json", capture=True).stdout)
        runner = target / NAME / "scripts" / "run.py"
        for style in ("standard", "nice"):
            run(sys.executable, runner, "smoke-test", "--workspace", root, "--style", style, "--json")
        run(sys.executable, installer, "upgrade", "--target", target, "--runtime-dir", runtime, "--json")
        run(sys.executable, runner, "doctor", "--json")
        run(sys.executable, installer, "uninstall", "--target", target, "--runtime-dir", runtime, "--purge-runtime", "--json")
        if unrelated.read_text(encoding="utf-8") != "preserve" or (target / NAME).exists() or runtime.exists():
            raise RuntimeError("Uninstall did not preserve the unrelated skill or remove its own runtime.")
        return {"ok": True, "profile": profile, "python": sys.version.split()[0], "packages": packages,
                "styles": ["standard", "nice"], "real_install_upgrade_uninstall": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("minimum", "latest"), required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".skill-work" / "clean-install")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = check(args.profile, args.work_dir)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
