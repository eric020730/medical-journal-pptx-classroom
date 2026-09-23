#!/usr/bin/env python3
"""Windows adaptations for the repository-local LibreOffice toolchain."""
from __future__ import annotations

import platform
from pathlib import Path
import shutil
import tempfile
import sys

import quality_tools


def windows_soffice_path() -> Path:
    """Return the console launcher; soffice.exe may detach and never report exit."""
    return quality_tools.LIBREOFFICE_DIR / "program" / "soffice.com"


def install_libreoffice_windows_short_stage(archive: Path) -> None:
    """Stage MSI extraction under the short system temp path.

    The release ZIP verification intentionally nests the project several levels
    deep. Windows Installer can return 1603 when an administrative image is
    expanded beneath that long repository path, so only the disposable staging
    directory uses the system temp root. The verified final product is still
    moved into this repository's .bootstrap/libreoffice directory.
    """
    with tempfile.TemporaryDirectory(prefix="mjpc-lo-") as temporary:
        temporary_path = Path(temporary)
        target = temporary_path / "admin"
        target.mkdir()
        quality_tools.run(
            [
                "msiexec.exe",
                "/a",
                str(archive),
                "/qn",
                "/norestart",
                f"TARGETDIR={target}",
            ]
        )
        product_root = quality_tools.locate_product_root(target)
        stage = temporary_path / "product"
        shutil.copytree(product_root, stage, symlinks=True)
        quality_tools.replace_directory(stage, quality_tools.LIBREOFFICE_DIR)


def main() -> int:
    if platform.system() != "Windows":
        print(
            "QUALITY_TOOLS_BLOCKED: the Windows quality-tool wrapper was used "
            "on a non-Windows system.",
            file=sys.stderr,
        )
        return 1
    quality_tools.soffice_path = windows_soffice_path
    quality_tools.install_libreoffice_windows = install_libreoffice_windows_short_stage
    return quality_tools.main()


if __name__ == "__main__":
    raise SystemExit(main())
