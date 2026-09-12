#!/usr/bin/env python3
"""Use LibreOffice's Windows console launcher for reliable CLI automation."""
from __future__ import annotations

import platform
from pathlib import Path
import sys

import quality_tools


def windows_soffice_path() -> Path:
    """Return the console launcher; soffice.exe may detach and never report exit."""
    return quality_tools.LIBREOFFICE_DIR / "program" / "soffice.com"


def main() -> int:
    if platform.system() != "Windows":
        print(
            "QUALITY_TOOLS_BLOCKED: the Windows quality-tool wrapper was used "
            "on a non-Windows system.",
            file=sys.stderr,
        )
        return 1
    quality_tools.soffice_path = windows_soffice_path
    return quality_tools.main()


if __name__ == "__main__":
    raise SystemExit(main())
