#!/usr/bin/env python3
"""Single project VERSION; engine provenance is not a second install route."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def metadata(root: Path = ROOT) -> dict[str, str]:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("VERSION must contain one stable major.minor.patch version")
    return {"version": version, "tag": "v" + version,
            "archive": "medical-journal-pptx-classroom-v" + version + ".zip"}


def synchronize(root: Path = ROOT, *, write: bool = False) -> list[str]:
    version = metadata(root)["version"]
    path = root / ".classroom-project.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    changed = []
    if config.get("classroom_version") != version:
        config["classroom_version"] = version
        changed.append(path.name)
        if write:
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    info = metadata()
    if args.tag and args.tag != info["tag"]:
        parser.error("Tag does not match VERSION")
    changed = synchronize(write=args.write)
    print(json.dumps({**info, "out_of_sync": changed}, indent=2))
    return 1 if changed and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
