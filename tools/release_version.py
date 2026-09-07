#!/usr/bin/env python3
"""Keep current release metadata aligned with the integrated skill VERSION."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "medical-journal-to-pptx-integrated"
SEMVER = re.compile(r"v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?")
DOCUMENTS = ("README.md", "docs/GLOBAL-INSTALL.md")


def metadata(root: Path = ROOT) -> dict[str, str]:
    skill = root / ".agents" / "skills" / SKILL_NAME
    version = (skill / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise ValueError("VERSION must contain a semantic version starting with v.")
    frontmatter = (skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    if not re.search(rf"^name:\s*{SKILL_NAME}\s*$", frontmatter, re.MULTILINE):
        raise ValueError("Integrated skill identity does not match the release.")
    semantic = re.match(r"v\d+\.\d+\.\d+", version).group(0)
    return {"version": version, "tag": semantic, "archive": f"{SKILL_NAME}-{semantic}.zip"}


def synchronize(root: Path = ROOT, *, write: bool = False) -> list[str]:
    info = metadata(root)
    version = info["version"]
    changes: dict[Path, str] = {}
    config_path = root / ".classroom-project.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("integrated_skill_version") != version:
        config["integrated_skill_version"] = version
        changes[config_path] = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    # These two guides describe only the current integrated release. Historical
    # changelogs, classroom versions, and existing deliverables are not rewritten.
    for name in DOCUMENTS:
        path = root / name
        original = path.read_text(encoding="utf-8")
        updated = SEMVER.sub(info["tag"], original)
        if original != updated:
            changes[path] = updated
    if write:
        for path, content in changes.items():
            path.write_text(content, encoding="utf-8")
    return [path.relative_to(root).as_posix() for path in changes]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Update current docs and config")
    parser.add_argument("--tag", help="Require this release tag to equal VERSION")
    args = parser.parse_args()
    info = metadata()
    if args.tag and args.tag != info["tag"]:
        parser.error(f"Tag {args.tag} does not match VERSION {info['tag']}")
    changes = synchronize(write=args.write)
    print(json.dumps({**info, "updated" if args.write else "out_of_sync": changes}, indent=2))
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
