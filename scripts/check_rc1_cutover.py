#!/usr/bin/env python3
"""Verify the historical v0.5.7 stable release record and current dev posture.

This script ensures:
- The historical v0.5.7 tag contains the expected stable version metadata.
- Current main is a post-v0.5.7 version (including stable 0.5.8).
- Public docs remain safe and do not contain forbidden claims or secrets.

Deterministic and local. Does not:
- tag
- push
- publish
- build packages
- call network
- load credentials
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORICAL_STABLE_VERSION = "0.5.7"
HISTORICAL_STABLE_TAG = "v0.5.7"
CURRENT_DEV_SERIES = "0.5.9.3"

# Forbidden positive claims about live trading / provider execution / broker execution / trust.
FORBIDDEN_POSITIVE_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
]

# Fragments that should not appear in public docs.
FORBIDDEN_FRAGMENTS = [
    "/Users/",
    "/private/var/",
]

# Secret-like patterns.
SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{10,}",
    r"\bAPCA-[A-Z0-9]{10,}",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}",
    r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]+",
]

# Absolute path patterns.
ABSOLUTE_PATH_PATTERNS = [
    r"/Users/[A-Za-z0-9_/-]+",
    r"/private/var/[A-Za-z0-9_/-]+",
]


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _git_show(tag: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{tag}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _check_version_consistency() -> list[str]:
    errors: list[str] = []
    pyproject_path = REPO_ROOT / "pyproject.toml"
    init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
    readme_path = REPO_ROOT / "README.md"
    changelog_path = REPO_ROOT / "CHANGELOG.md"
    release_note_path = REPO_ROOT / "docs" / "releases" / f"{HISTORICAL_STABLE_TAG}.md"
    checklist_path = REPO_ROOT / "docs" / "release-checklist.md"

    # 1. Current main version should be a dev version after 0.5.7
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        current_toml_version = data.get("project", {}).get("version")
        if current_toml_version != CURRENT_DEV_SERIES:
            # Allow dev, rc, or later series after 0.5.7
            if not (
                current_toml_version
                and (
                    current_toml_version == "0.5.8"
                    or current_toml_version == "0.5.8.1"
                    or current_toml_version.startswith("0.5.8.dev")
                    or current_toml_version.startswith("0.5.8rc")
                    or current_toml_version.startswith("0.5.9.")
                    or current_toml_version.startswith("0.5.9.dev")
                    or current_toml_version.startswith("0.6.")
                )
            ):
                errors.append(
                    f"pyproject.toml version {current_toml_version!r} is not a recognized post-0.5.7 version"
                )
    else:
        errors.append("pyproject.toml not found")

    if init_path.exists():
        init_text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        current_init_version = m.group(1) if m else None
        if current_init_version != CURRENT_DEV_SERIES:
            if not (
                current_init_version
                and (
                    current_init_version == "0.5.8"
                    or current_init_version == "0.5.8.1"
                    or current_init_version.startswith("0.5.8.dev")
                    or current_init_version.startswith("0.5.8rc")
                    or current_init_version.startswith("0.5.9.")
                    or current_init_version.startswith("0.5.9.dev")
                    or current_init_version.startswith("0.6.")
                )
            ):
                errors.append(
                    f"__init__.py version {current_init_version!r} is not a recognized post-0.5.7 version"
                )
    else:
        errors.append("__init__.py not found")

    # 2. Historical v0.5.7 tag must contain version 0.5.7
    tag_pyproject = _git_show(HISTORICAL_STABLE_TAG, "pyproject.toml")
    if not tag_pyproject:
        errors.append(
            f"Could not read pyproject.toml from tag {HISTORICAL_STABLE_TAG}. "
            "Run `git fetch --tags origin` locally, or ensure GitHub Actions checkout "
            "uses `fetch-depth: 0`, `fetch-tags: true`, and `git fetch --force --tags origin`."
        )
    else:
        tag_toml_version = None
        try:
            tag_toml_version = tomllib.loads(tag_pyproject).get("project", {}).get("version")
        except Exception:
            pass
        if tag_toml_version != HISTORICAL_STABLE_VERSION:
            errors.append(
                f"Tag {HISTORICAL_STABLE_TAG} pyproject.toml version {tag_toml_version!r} != {HISTORICAL_STABLE_VERSION!r}"
            )

    tag_init = _git_show(HISTORICAL_STABLE_TAG, "src/atlas_agent/__init__.py")
    if not tag_init:
        errors.append(
            f"Could not read __init__.py from tag {HISTORICAL_STABLE_TAG}. "
            "Run `git fetch --tags origin` locally, or ensure GitHub Actions checkout "
            "uses `fetch-depth: 0`, `fetch-tags: true`, and `git fetch --force --tags origin`."
        )
    else:
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', tag_init, re.MULTILINE)
        tag_init_version = m.group(1) if m else None
        if tag_init_version != HISTORICAL_STABLE_VERSION:
            errors.append(
                f"Tag {HISTORICAL_STABLE_TAG} __init__.py version {tag_init_version!r} != {HISTORICAL_STABLE_VERSION!r}"
            )

    # 3. README must reference the current stable tag and not contain stale dev wording
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        if "v0.5.8" not in readme_text:
            errors.append("README.md missing current status reference to v0.5.8")
        stale = [
            r"Current Status \(v0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(v0\.5\.7-rc\d+\)",
            r"Current Status \(0\.5\.7rc\d+\)",
        ]
        for pattern in stale:
            if re.search(pattern, readme_text):
                errors.append("README.md contains stale RC/dev current-status reference")
    else:
        errors.append("README.md not found")

    # 4. CHANGELOG must have both Unreleased and 0.5.7
    if changelog_path.exists():
        changelog_text = changelog_path.read_text(encoding="utf-8")
        if "[Unreleased]" not in changelog_text:
            errors.append("CHANGELOG.md missing [Unreleased] section")
        if f"[{HISTORICAL_STABLE_VERSION}]" not in changelog_text:
            errors.append("CHANGELOG.md missing stable release entry")
    else:
        errors.append("CHANGELOG.md not found")

    if not release_note_path.exists():
        errors.append(f"Release note missing: {release_note_path}")

    if checklist_path.exists():
        checklist_text = checklist_path.read_text(encoding="utf-8")
        if HISTORICAL_STABLE_TAG not in checklist_text:
            errors.append("release-checklist.md missing stable tag reference")
    else:
        errors.append("release-checklist.md not found")

    return errors


def _scan_text(text: str, rel_path: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()

    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
        for m in re.finditer(re.escape(phrase), lower):
            sentence_start = max(0, m.start() - 120)
            sentence_end = min(len(lower), m.end() + 120)
            sentence = lower[sentence_start:sentence_end]
            negative_indicators = (
                "not ", "does not", "never", "no ", "avoid",
                "disclaimer", "prohibited", "forbidden", "must not",
                "cannot", "do not", "is not", "are not", "without",
                "fail closed", "not yet", "not implemented", "not enabled",
                "not authorized", "not a ", "not ready", "remains disabled",
                "remains locked", "remains blocked",
            )
            if not any(ind in sentence for ind in negative_indicators):
                errors.append(
                    f"[{rel_path}] Forbidden positive claim '{phrase}'"
                )

    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            errors.append(f"[{rel_path}] Forbidden fragment '{frag}'")

    for pattern in SECRET_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            errors.append(
                f"[{rel_path}] Secret-like pattern matched: {m.group(0)[:40]}"
            )

    for pattern in ABSOLUTE_PATH_PATTERNS:
        for m in re.finditer(pattern, text):
            errors.append(
                f"[{rel_path}] Absolute path matched: {m.group(0)[:60]}"
            )

    return errors


def _check_no_package_artifacts_staged() -> list[str]:
    errors: list[str] = []
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden_prefixes = ("dist/", "build/", "*.egg-info")
    for f in staged:
        if f.startswith(forbidden_prefixes) or f.endswith(".egg-info/"):
            errors.append(f"Package artifact staged: {f}")
    return errors


def _gather() -> dict:
    all_errors: list[str] = []

    all_errors.extend(_check_version_consistency())

    public_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "releases" / f"{HISTORICAL_STABLE_TAG}.md",
        REPO_ROOT / "docs" / "release-checklist.md",
        REPO_ROOT / "docs" / "provider-safety-dossier.md",
        REPO_ROOT / "docs" / "examples" / "provider-safety-dossier-workflow.md",
        REPO_ROOT / "docs" / "release-candidate-readiness.md",
        REPO_ROOT / "docs" / "release-candidate-cutover.md",
    ]

    for path in public_docs:
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        all_errors.extend(_scan_text(text, str(rel)))

    all_errors.extend(_check_no_package_artifacts_staged())

    current_toml_version = None
    current_init_version = None
    pyproject_path = REPO_ROOT / "pyproject.toml"
    init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        current_toml_version = data.get("project", {}).get("version")
    if init_path.exists():
        init_text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        current_init_version = m.group(1) if m else None

    return {
        "passed": len(all_errors) == 0,
        "current_package_version": current_toml_version,
        "current_init_version": current_init_version,
        "stable_tag": HISTORICAL_STABLE_TAG,
        "stable_tag_version": HISTORICAL_STABLE_VERSION,
        "errors": all_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Historical v0.5.7 release record check"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("Historical v0.5.7 release record check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"Historical v0.5.7 release record check PASSED: "
                f"current={result['current_package_version']} stable_tag={result['stable_tag']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
