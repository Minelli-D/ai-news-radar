"""Build build/collector.zip for the python3.12 / arm64 Lambda runtime.

- installs the pinned runtime dependencies as manylinux aarch64 wheels (no compiler, no Docker);
- refuses compiled extensions (every dependency is pure Python today);
- writes a reproducible zip (sorted entries, fixed timestamps), so Terraform's
  source_code_hash only changes when the code or the dependencies change.

    .venv/bin/python scripts/build_lambda.py            # -> build/collector.zip
"""

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PACKAGE = BUILD / "lambda-package"
ZIP_PATH = BUILD / "collector.zip"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_FILES = {"requirements.txt"}


def install_dependencies() -> None:
    subprocess.run(  # noqa: S603 (fixed argument list, no shell)
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",  # requirements.txt pins every transitive dependency
            "--no-compile",
            "--only-binary=:all:",
            "--platform=manylinux2014_aarch64",
            "--implementation=cp",
            "--python-version=3.12",
            f"--target={PACKAGE}",
            f"--requirement={ROOT / 'collector' / 'requirements.txt'}",
        ],
        check=True,
    )


def copy_collector() -> None:
    shutil.copytree(
        ROOT / "collector",
        PACKAGE / "collector",
        ignore=shutil.ignore_patterns(*EXCLUDED_DIRS, *EXCLUDED_FILES, "*.pyc"),
    )


def reject_native_code() -> None:
    native = [p for p in PACKAGE.rglob("*") if p.suffix in {".so", ".pyd", ".dylib"}]
    if native:
        raise SystemExit(f"compiled extensions would need an arm64 build: {native}")


def write_zip() -> str:
    files = sorted(
        p for p in PACKAGE.rglob("*") if p.is_file() and not EXCLUDED_DIRS & set(p.parts)
    )
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(PACKAGE).as_posix(), FIXED_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()


def main() -> None:
    shutil.rmtree(PACKAGE, ignore_errors=True)
    PACKAGE.mkdir(parents=True)
    install_dependencies()
    copy_collector()
    reject_native_code()
    digest = write_zip()
    size_kb = ZIP_PATH.stat().st_size // 1024
    print(f"{ZIP_PATH.relative_to(ROOT)}  {size_kb} KiB  sha256={digest}")


if __name__ == "__main__":
    main()
