#!/usr/bin/env python3
"""Install the OFGS runtime into a configurable prefix and staging root."""

import argparse
import os
from pathlib import Path, PurePosixPath
import shlex
import sys
import tempfile
from typing import Dict


PLACEHOLDER = "@OFGS_INSTALL_DIR@"
CORE_FILES = (
    "__init__.py",
    "dataset_parser.py",
    "discovery.py",
    "generator.py",
    "parser.py",
)


class InstallationError(Exception):
    """Raised when the requested installation cannot be completed safely."""


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="/usr/local")
    parser.add_argument("--destdir", default="")
    return parser.parse_args()


def validate_prefix(value: str) -> PurePosixPath:
    prefix = PurePosixPath(value)
    if not prefix.is_absolute() or ".." in prefix.parts:
        raise InstallationError("PREFIX must be an absolute path without '..'.")
    return prefix


def staged_path(destdir: str, installed_path: PurePosixPath) -> Path:
    relative_path = Path(*installed_path.parts[1:])
    if destdir:
        return Path(destdir) / relative_path
    return Path("/") / relative_path


def read_source_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise InstallationError(f"unsafe or missing source file: {path}")
    return path.read_bytes()


def create_directory(path: Path):
    missing = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise InstallationError(f"cannot use broken symlink as directory: {current}")
        missing.append(current)
        current = current.parent
    if not current.is_dir():
        raise InstallationError(f"installation path is not a directory: {current}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)


def atomic_write(path: Path, content: bytes, mode: int):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
        temporary_path.chmod(mode)
        os.replace(str(temporary_path), str(path))
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def install(prefix_value: str, destdir: str):
    prefix = validate_prefix(prefix_value)
    installed_runtime = prefix / "share" / "ofgs"
    installed_wrapper = prefix / "bin" / "ofgs"
    runtime_target = staged_path(destdir, installed_runtime)
    wrapper_target = staged_path(destdir, installed_wrapper)

    project_root = Path(__file__).absolute().parents[1]
    wrapper_source = project_root / "wrapper" / "ofgs"
    generator_source = project_root / "ofgs_generate.py"
    core_source = project_root / "core"

    wrapper_template = read_source_file(wrapper_source).decode("utf-8")
    placeholder_count = wrapper_template.count(PLACEHOLDER)
    if placeholder_count != 1:
        raise InstallationError(
            f"expected one {PLACEHOLDER} placeholder, found {placeholder_count}"
        )
    wrapper_content = wrapper_template.replace(
        PLACEHOLDER, shlex.quote(str(installed_runtime))
    ).encode("utf-8")

    runtime_files: Dict[Path, bytes] = {
        runtime_target / "ofgs_generate.py": read_source_file(generator_source)
    }
    for filename in CORE_FILES:
        runtime_files[runtime_target / "core" / filename] = read_source_file(
            core_source / filename
        )

    create_directory(runtime_target / "core")
    create_directory(wrapper_target.parent)
    for target, content in runtime_files.items():
        atomic_write(target, content, 0o644)
    atomic_write(wrapper_target, wrapper_content, 0o755)


def main():
    arguments = parse_arguments()
    try:
        install(arguments.prefix, arguments.destdir)
    except (InstallationError, OSError, UnicodeError) as error:
        print(f"OFGS installation error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
