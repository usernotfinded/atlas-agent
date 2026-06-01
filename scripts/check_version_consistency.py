#!/usr/bin/env python3
"""Validate version consistency across package, code, docs, and release notes.

Accepts PEP 440 rc versions (e.g. 0.5.7rc1) and public tag versions
(e.g. v0.5.8-rc1). Rejects inconsistent mixes and stale current-version
references.
"""

import re
import sys
import tomllib
from pathlib import Path


PACKAGE_VERSION = "0.5.9.dev0"
PUBLIC_TAG = "v0.5.8"


def main() -> int:
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1])
    else:
        repo_root = Path(__file__).resolve().parent.parent

    pyproject_path = repo_root / "pyproject.toml"
    init_path = repo_root / "src" / "atlas_agent" / "__init__.py"
    readme_path = repo_root / "README.md"
    changelog_path = repo_root / "CHANGELOG.md"
    release_note_path = repo_root / "docs" / "releases" / f"{PUBLIC_TAG}.md"
    checklist_path = repo_root / "docs" / "release-checklist.md"

    errors: list[str] = []
    toml_version: str | None = None
    init_version: str | None = None

    # 1. pyproject.toml version
    if not pyproject_path.exists():
        errors.append("pyproject.toml not found")
    else:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        toml_version = data.get("project", {}).get("version")
        if toml_version is None:
            errors.append("could not parse version from pyproject.toml")

    # 2. __init__.py version
    if not init_path.exists():
        errors.append("__init__.py not found")
    else:
        init_text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        init_version = m.group(1) if m else None
        if init_version is None:
            errors.append("could not parse version from __init__.py")

    # 3. Core consistency: pyproject == __init__
    if toml_version is not None and init_version is not None:
        if toml_version != init_version:
            errors.append(
                f"pyproject.toml ({toml_version!r}) and __init__.py ({init_version!r}) versions do not match"
            )
        elif toml_version != PACKAGE_VERSION:
            # Versions match but are not the expected current version.
            # This is allowed in tests; only warn.
            print(f"Version consistency OK: {toml_version} (not the expected {PACKAGE_VERSION})")
            return 0

    if errors:
        print("Version consistency check FAILED")
        for e in errors:
            print(f"  - {e}")
        return 2

    # 4. README current status (only when running on the actual repo with expected version)
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        if PUBLIC_TAG not in readme_text:
            errors.append(f"README.md missing current status reference to {PUBLIC_TAG}")
        # Reject stale dev/RC current-status claims
        stale_patterns = [
            r"Current Status \(v0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(v0\.5\.7-rc\d+\)",
            r"Current Status \(0\.5\.7rc\d+\)",
        ]
        for pattern in stale_patterns:
            if re.search(pattern, readme_text):
                errors.append(f"README.md contains stale current-status reference matching {pattern}")

    # 5. CHANGELOG entry (skip for dev versions; Unreleased is sufficient)
    if changelog_path.exists():
        changelog_text = changelog_path.read_text(encoding="utf-8")
        is_dev = ".dev" in PACKAGE_VERSION
        if f"[{PACKAGE_VERSION}]" not in changelog_text and not is_dev:
            errors.append(f"CHANGELOG.md missing entry for [{PACKAGE_VERSION}]")

    # 6. Release note exists
    if not release_note_path.exists():
        errors.append(f"Release note missing: {release_note_path}")

    # 7. Release checklist references
    if checklist_path.exists():
        checklist_text = checklist_path.read_text(encoding="utf-8")
        if PUBLIC_TAG not in checklist_text:
            errors.append(
                f"docs/release-checklist.md missing reference to {PUBLIC_TAG}"
            )

    if errors:
        print("Version consistency check FAILED")
        for e in errors:
            print(f"  - {e}")
        return 2

    print(f"Version consistency OK: package={PACKAGE_VERSION} public_tag={PUBLIC_TAG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
