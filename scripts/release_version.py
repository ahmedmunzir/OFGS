#!/usr/bin/env python3
"""Validate an OFGS release tag and version a generated packaging tree."""

import argparse
from pathlib import Path
import re
import sys


TAG_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ReleaseVersionError(Exception):
    """Raised when release version preparation cannot be completed safely."""


def version_from_tag(tag: str) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ReleaseVersionError(
            f"invalid release tag {tag!r}; expected vMAJOR.MINOR.PATCH"
        )
    return ".".join(match.groups())


def replace_once(path: Path, pattern: str, replacement: str):
    text = path.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ReleaseVersionError(f"expected one version marker in {path}")
    path.write_text(updated)


def prepare_tree(tree: Path, version: str, package_format: str):
    if not tree.is_dir():
        raise ReleaseVersionError(f"release tree is not a directory: {tree}")

    replace_once(
        tree / "README.md",
        r"^# OFGS \(OpenFOAM Gnuplot Suite\) v[0-9]+\.[0-9]+\.[0-9]+$",
        f"# OFGS (OpenFOAM Gnuplot Suite) v{version}",
    )
    replace_once(
        tree / "docs" / "ofgs.1",
        r'^(\.TH OFGS 1 "[^"]+" "OFGS )[0-9]+\.[0-9]+\.[0-9]+(" "User Commands")$',
        rf"\g<1>{version}\g<2>",
    )

    if package_format == "debian":
        replace_once(
            tree / "debian" / "changelog",
            r"^ofgs \([0-9]+\.[0-9]+\.[0-9]+-[0-9]+\)( .*)$",
            rf"ofgs ({version}-1)\g<1>",
        )


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag in vMAJOR.MINOR.PATCH form")
    parser.add_argument("--prepare-tree", type=Path)
    parser.add_argument("--format", choices=("debian", "rpm"))
    arguments = parser.parse_args()
    if bool(arguments.prepare_tree) != bool(arguments.format):
        parser.error("--prepare-tree and --format must be used together")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        version = version_from_tag(arguments.tag)
        if arguments.prepare_tree:
            prepare_tree(arguments.prepare_tree, version, arguments.format)
    except (OSError, UnicodeError, ReleaseVersionError) as error:
        print(f"OFGS release version error: {error}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
