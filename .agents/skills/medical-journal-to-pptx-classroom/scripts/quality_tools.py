#!/usr/bin/env python3
"""Install and verify the fixed LibreOffice + Poppler rendering toolchain.

Everything is kept inside the repository's .bootstrap directory. The script
never installs Homebrew/WinGet packages, never edits a shell profile, and never
changes a machine-wide PATH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
BOOTSTRAP = ROOT / ".bootstrap"
DOWNLOADS = BOOTSTRAP / "downloads"
PIXI_DIR = BOOTSTRAP / "pixi"
PIXI_HOME = BOOTSTRAP / "pixi-home"
PIXI_CACHE = BOOTSTRAP / "pixi-cache"
LIBREOFFICE_DIR = BOOTSTRAP / "libreoffice"
RECEIPT = BOOTSTRAP / "quality-tools.json"

LIBREOFFICE_VERSION = "26.8.0"
POPPLER_VERSION = "26.09.0"
PIXI_VERSION = "0.80.0"

PIXI_ASSETS = {
    ("Darwin", "arm64"): (
        "pixi-aarch64-apple-darwin",
        "e1af87edbd2ae2a986efe5b7716b80d35b0c99ac33b60d23ff232413b527ca8b",
    ),
    ("Darwin", "x86_64"): (
        "pixi-x86_64-apple-darwin",
        "e2c9b1950c217dbdd191e3248bc5629486cda5b9d6c092d32a942ddb0c8bf4de",
    ),
    ("Linux", "aarch64"): (
        "pixi-aarch64-unknown-linux-musl",
        "20e9fcfffa1ef02d10b7a5df79092110c1e4aa9caa13072f5008a2fd2ecd9436",
    ),
    ("Linux", "x86_64"): (
        "pixi-x86_64-unknown-linux-musl",
        "387a2d3052e656f61ccf735e6750255451366f45635a2da09116b1f8394b2837",
    ),
    ("Windows", "arm64"): (
        "pixi-aarch64-pc-windows-msvc.exe",
        "0bd4b7a87ed5814373b7c1f3b0d7d5ab5183035a9eb29696983b674ec71aa313",
    ),
    ("Windows", "x86_64"): (
        "pixi-x86_64-pc-windows-msvc.exe",
        "ebf870ab0be4abad5e3b1e083d4dd8aeecbbc37f84e3070da42a4db6be4c6c91",
    ),
}

LIBREOFFICE_ASSETS = {
    ("Darwin", "arm64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/mac/aarch64/LibreOffice_26.8.0_MacOS_aarch64.dmg",
        "8858d8058da4f862f47559486814e65efc27294da67c5e4bb56b006b1ee59f89",
        "LibreOffice_26.8.0_MacOS_aarch64.dmg",
    ),
    ("Darwin", "x86_64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/mac/x86_64/LibreOffice_26.8.0_MacOS_x86-64.dmg",
        "2dcbce4894e01bc1ecd594658e2cbda70ff7bfcd0b310f35d38887797172d09e",
        "LibreOffice_26.8.0_MacOS_x86-64.dmg",
    ),
    ("Windows", "x86_64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/win/x86_64/LibreOffice_26.8.0_Win_x86-64.msi",
        "4aa6c6e1895f4055104effcb556bd3362d20c6ad707c149543304f395ef9db95",
        "LibreOffice_26.8.0_Win_x86-64.msi",
    ),
    ("Windows", "arm64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/win/aarch64/LibreOffice_26.8.0_Win_aarch64.msi",
        "7ea33f771223a68c49538438e5f57e7805bc951edc8d22dcdf4ef26e3ab2fbe0",
        "LibreOffice_26.8.0_Win_aarch64.msi",
    ),
    ("Linux", "x86_64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/deb/x86_64/LibreOffice_26.8.0_Linux_x86-64_deb.tar.gz",
        "d0a6031a3837e48f9854e6d2da6489b9fadbd814afa4741fa32a197741663a22",
        "LibreOffice_26.8.0_Linux_x86-64_deb.tar.gz",
    ),
    ("Linux", "aarch64"): (
        "https://download.documentfoundation.org/libreoffice/stable/26.8.0/deb/aarch64/LibreOffice_26.8.0_Linux_aarch64_deb.tar.gz",
        "f989b73c31e7e16b3f99475bc5befaffdf42af75f83fe882293e1a0258cc9173",
        "LibreOffice_26.8.0_Linux_aarch64_deb.tar.gz",
    ),
}


def normalized_arch() -> str:
    value = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "aarch64" if platform.system() == "Linux" else "arm64",
    }
    return aliases.get(value, value)


def platform_key() -> tuple[str, str]:
    key = (platform.system(), normalized_arch())
    if key not in PIXI_ASSETS or key not in LIBREOFFICE_ASSETS:
        raise RuntimeError(f"unsupported quality-tool platform: {key[0]} {key[1]}")
    return key


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected_sha256:
        return destination
    destination.unlink(missing_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "medical-journal-pptx-classroom/4.6"}
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as source, temporary.open(
                "wb"
            ) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            actual = sha256(temporary)
            if actual != expected_sha256:
                raise RuntimeError(
                    f"checksum mismatch for {destination.name}: expected {expected_sha256}, got {actual}"
                )
            temporary.replace(destination)
            return destination
        except Exception as error:  # network errors vary by platform
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"download failed for {destination.name}: {type(last_error).__name__}"
    )


def run(
    command: list[str], *, timeout: int = 1800
) -> subprocess.CompletedProcess[str]:
    environment = quality_environment()
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-20:])
        raise RuntimeError(
            f"command failed ({result.returncode}): {Path(command[0]).name}\n{tail}"
        )
    return result


def pixi_path() -> Path:
    suffix = ".exe" if platform.system() == "Windows" else ""
    return PIXI_DIR / f"pixi{suffix}"


def pdftoppm_path() -> Path:
    suffix = ".exe" if platform.system() == "Windows" else ""
    direct = PIXI_HOME / "bin" / f"pdftoppm{suffix}"
    if direct.is_file():
        return direct
    matches = (
        sorted(PIXI_HOME.glob(f"**/pdftoppm{suffix}")) if PIXI_HOME.is_dir() else []
    )
    return matches[0] if matches else direct


def soffice_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return (
            LIBREOFFICE_DIR
            / "LibreOffice.app"
            / "Contents"
            / "MacOS"
            / "soffice"
        )
    suffix = ".exe" if system == "Windows" else ""
    return LIBREOFFICE_DIR / "program" / f"soffice{suffix}"


def quality_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "PIXI_HOME": str(PIXI_HOME),
            "PIXI_CACHE_DIR": str(PIXI_CACHE),
            "PIXI_NO_PATH_UPDATE": "1",
            "PIXI_COLOR": "never",
            "PIXI_NO_PROGRESS": "true",
            "PYTHONUTF8": "1",
        }
    )
    prefixes = [str(PIXI_HOME / "bin"), str(soffice_path().parent)]
    environment["PATH"] = os.pathsep.join([*prefixes, environment.get("PATH", "")])
    return environment


def ensure_pixi() -> Path:
    key = platform_key()
    asset, expected = PIXI_ASSETS[key]
    executable = pixi_path()
    url = f"https://github.com/prefix-dev/pixi/releases/download/v{PIXI_VERSION}/{asset}"
    download(url, executable, expected)
    if platform.system() != "Windows":
        executable.chmod(0o755)
    version = run([str(executable), "--version"], timeout=60).stdout
    if PIXI_VERSION not in version:
        raise RuntimeError(f"unexpected Pixi version: {version.strip()}")
    return executable


def tool_version(path: Path, arguments: list[str], expected: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    try:
        output = run([str(path), *arguments], timeout=90).stdout.strip()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        return False, type(error).__name__
    return expected in output, output.splitlines()[0] if output else "no version output"


def ensure_poppler() -> Path:
    executable = pdftoppm_path()
    ready, _ = tool_version(executable, ["-v"], POPPLER_VERSION)
    if ready:
        return executable
    pixi = ensure_pixi()
    # PIXI_HOME is owned by this repository, so removal cannot affect a user's
    # actual global Pixi installation.
    subprocess.run(
        [str(pixi), "--no-progress", "--color", "never", "global", "remove", "poppler"],
        cwd=ROOT,
        env=quality_environment(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=300,
    )
    run(
        [
            str(pixi),
            "--no-progress",
            "--color",
            "never",
            "global",
            "install",
            "--channel",
            "conda-forge",
            f"poppler={POPPLER_VERSION}",
        ]
    )
    executable = pdftoppm_path()
    ready, detail = tool_version(executable, ["-v"], POPPLER_VERSION)
    if not ready:
        raise RuntimeError(f"Poppler verification failed: {detail}")
    return executable


def replace_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))


def install_libreoffice_macos(archive: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="libreoffice-mount-", dir=BOOTSTRAP
    ) as temporary:
        mount = Path(temporary) / "mount"
        mount.mkdir()
        run(
            [
                "/usr/bin/hdiutil",
                "attach",
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(mount),
                str(archive),
            ]
        )
        try:
            app = mount / "LibreOffice.app"
            if not app.is_dir():
                matches = list(mount.glob("*.app"))
                if len(matches) != 1:
                    raise RuntimeError(
                        "LibreOffice DMG did not contain exactly one app bundle"
                    )
                app = matches[0]
            stage = Path(temporary) / "LibreOffice.app.stage"
            run(["/usr/bin/ditto", str(app), str(stage)])
            replace_directory(stage, LIBREOFFICE_DIR / "LibreOffice.app")
        finally:
            subprocess.run(
                ["/usr/bin/hdiutil", "detach", str(mount)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )


def locate_product_root(search_root: Path) -> Path:
    suffix = ".exe" if platform.system() == "Windows" else ""
    matches = sorted(search_root.glob(f"**/program/soffice{suffix}"))
    if not matches:
        raise RuntimeError("extracted LibreOffice did not contain program/soffice")
    return matches[0].parent.parent


def install_libreoffice_windows(archive: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="libreoffice-msi-", dir=BOOTSTRAP
    ) as temporary:
        target = Path(temporary) / "admin"
        target.mkdir()
        run(
            [
                "msiexec.exe",
                "/a",
                str(archive),
                "/qn",
                "/norestart",
                f"TARGETDIR={target}",
            ]
        )
        product_root = locate_product_root(target)
        stage = Path(temporary) / "product"
        shutil.copytree(product_root, stage, symlinks=True)
        replace_directory(stage, LIBREOFFICE_DIR)


def safe_extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        root = destination.resolve()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("unsafe path in LibreOffice archive")
        tar.extractall(destination)


def install_libreoffice_linux(archive: Path) -> None:
    dpkg_deb = shutil.which("dpkg-deb")
    if not dpkg_deb:
        raise RuntimeError(
            "dpkg-deb is required for project-local Linux LibreOffice extraction"
        )
    with tempfile.TemporaryDirectory(
        prefix="libreoffice-deb-", dir=BOOTSTRAP
    ) as temporary:
        temporary_path = Path(temporary)
        packages = temporary_path / "packages"
        packages.mkdir()
        safe_extract_tar(archive, packages)
        debs = sorted(packages.glob("**/*.deb"))
        if not debs:
            raise RuntimeError("LibreOffice archive contained no .deb packages")
        root = temporary_path / "root"
        root.mkdir()
        for package in debs:
            run([dpkg_deb, "-x", str(package), str(root)], timeout=300)
        product_root = locate_product_root(root)
        stage = temporary_path / "product"
        shutil.copytree(product_root, stage, symlinks=True)
        replace_directory(stage, LIBREOFFICE_DIR)


def ensure_libreoffice() -> Path:
    executable = soffice_path()
    ready, _ = tool_version(
        executable, ["--headless", "--version"], LIBREOFFICE_VERSION
    )
    if ready:
        return executable
    key = platform_key()
    url, expected, filename = LIBREOFFICE_ASSETS[key]
    archive = download(url, DOWNLOADS / filename, expected)
    if platform.system() == "Darwin":
        install_libreoffice_macos(archive)
    elif platform.system() == "Windows":
        install_libreoffice_windows(archive)
    else:
        install_libreoffice_linux(archive)
    executable = soffice_path()
    ready, detail = tool_version(
        executable, ["--headless", "--version"], LIBREOFFICE_VERSION
    )
    if not ready:
        raise RuntimeError(f"LibreOffice verification failed: {detail}")
    return executable


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def collect_report() -> dict[str, object]:
    soffice = soffice_path()
    pdftoppm = pdftoppm_path()
    libreoffice_ok, libreoffice_detail = tool_version(
        soffice, ["--headless", "--version"], LIBREOFFICE_VERSION
    )
    poppler_ok, poppler_detail = tool_version(
        pdftoppm, ["-v"], POPPLER_VERSION
    )
    return {
        "schema_version": 1,
        "state": (
            "FULL_QUALITY_TOOLS_READY"
            if libreoffice_ok and poppler_ok
            else "BLOCKED"
        ),
        "platform": {
            "system": platform.system(),
            "architecture": normalized_arch(),
        },
        "libreoffice": {
            "required_version": LIBREOFFICE_VERSION,
            "ok": libreoffice_ok,
            "detail": libreoffice_detail,
            "path": relative(soffice),
        },
        "poppler": {
            "required_version": POPPLER_VERSION,
            "ok": poppler_ok,
            "detail": poppler_detail,
            "path": relative(pdftoppm),
        },
        "scope": "repository",
    }


def save_receipt(report: dict[str, object]) -> None:
    BOOTSTRAP.mkdir(parents=True, exist_ok=True)
    temporary = RECEIPT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(RECEIPT)


def install() -> dict[str, object]:
    BOOTSTRAP.mkdir(parents=True, exist_ok=True)
    for directory in (BOOTSTRAP, DOWNLOADS, PIXI_DIR, PIXI_HOME, PIXI_CACHE):
        if directory.exists() and directory.is_symlink():
            raise RuntimeError(
                f"refusing symlink bootstrap directory: {directory.name}"
            )
        directory.mkdir(parents=True, exist_ok=True)
    ensure_libreoffice()
    ensure_poppler()
    report = collect_report()
    if report["state"] != "FULL_QUALITY_TOOLS_READY":
        raise RuntimeError("quality-tool verification did not pass")
    save_receipt(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = install() if args.command == "install" else collect_report()
    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
        tarfile.TarError,
    ) as error:
        print(f"QUALITY_TOOLS_BLOCKED: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["state"])
    return 0 if report["state"] == "FULL_QUALITY_TOOLS_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
