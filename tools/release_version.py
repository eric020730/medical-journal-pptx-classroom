#!/usr/bin/env python3
"""Keep the classroom and standalone integrated release metadata aligned."""
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
    project_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", project_version):
        raise ValueError("VERSION must contain one semantic version")
    skill = root / ".agents" / "skills" / SKILL_NAME
    skill_version = (skill / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(skill_version):
        raise ValueError("Integrated VERSION must contain a semantic version starting with v.")
    frontmatter = (skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    if not re.search(rf"^name:\s*{SKILL_NAME}\s*$", frontmatter, re.MULTILINE):
        raise ValueError("Integrated skill identity does not match the release.")
    semantic = skill_version
    if semantic != f"v{project_version}":
        raise ValueError(
            f"Classroom VERSION {project_version} and integrated VERSION {skill_version} differ."
        )
    return {
        "version": project_version,
        "tag": semantic,
        "archive": f"medical-journal-pptx-classroom-{semantic}.zip",
        "skill_version": skill_version,
        "skill_archive": f"{SKILL_NAME}-{semantic}.zip",
    }


def synchronize(root: Path = ROOT, *, write: bool = False) -> list[str]:
    info = metadata(root)
    config_path = root / ".classroom-project.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    changes: dict[Path, str] = {}
    if config.get("classroom_version") != info["version"]:
        config["classroom_version"] = info["version"]
    if config.get("integrated_skill_name") != SKILL_NAME:
        config["integrated_skill_name"] = SKILL_NAME
    if config.get("integrated_skill_version") != info["skill_version"]:
        config["integrated_skill_version"] = info["skill_version"]
    config["skill_name"] = SKILL_NAME
    config["classroom_skill_version"] = info["skill_version"]
    normalized_config = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if normalized_config != config_path.read_text(encoding="utf-8"):
        changes[config_path] = normalized_config
    for name in DOCUMENTS:
        path = root / name
        # The student distribution deliberately omits the standalone install guide.
        # Source checkouts must still contain it; only a shipped archive may omit it.
        if (name == "docs/GLOBAL-INSTALL.md" and not path.exists()
                and (root / "RELEASE-MANIFEST.txt").is_file()):
            continue
        original = path.read_text(encoding="utf-8")
        updated = re.sub(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9-]+(?:\.(?!(?:zip|sha256)\b)[A-Za-z0-9-]+)*)?", info["tag"], original)
        if original != updated:
            changes[path] = updated
    if write:
        for path, content in changes.items():
            path.write_text(content, encoding="utf-8")
    return [path.relative_to(root).as_posix() for path in changes]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    info = metadata()
    if args.tag and args.tag != info["tag"]:
        parser.error(f"Tag {args.tag} does not match VERSION {info['tag']}")
    changes = synchronize(write=args.write)
    print(json.dumps({**info, "updated" if args.write else "out_of_sync": changes}, indent=2))
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
