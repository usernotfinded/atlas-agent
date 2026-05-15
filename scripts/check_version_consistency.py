#!/usr/bin/env python3
"""Validate that pyproject.toml version matches src/atlas_agent/__init__.py __version__."""

import re
import sys
import tomllib
from pathlib import Path


def main() -> int:
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1])
    else:
        repo_root = Path(__file__).resolve().parent.parent

    pyproject_path = repo_root / "pyproject.toml"
    init_path = repo_root / "src" / "atlas_agent" / "__init__.py"

    if not pyproject_path.exists():
        print("Version consistency check failed: pyproject.toml not found.")
        return 2
    if not init_path.exists():
        print("Version consistency check failed: __init__.py not found.")
        return 2

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    toml_version = data.get("project", {}).get("version")

    init_text = init_path.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    init_version = m.group(1) if m else None

    if toml_version is None or init_version is None:
        print("Version consistency check failed: could not parse version from one or both files.")
        return 2

    if toml_version == init_version:
        print(f"Version consistency OK: {toml_version}")
        return 0

    print("Version consistency check failed: pyproject.toml and __init__.py versions do not match.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
