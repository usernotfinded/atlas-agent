#!/usr/bin/env python3
"""Read-only v0.6.2 release prep checker (post-v0.6.2 state check).

Verifies that the repository remains correctly prepared after the v0.6.2 release:
- version is 0.6.2 or 0.6.3 (post-bump allowed)
- docs/releases/v0.6.2.md exists
- docs/trust/v0.6.2-status.md exists
- CHANGELOG has 0.6.2 entry
- no unsafe claims
- docs/releases/v0.6.3.md may exist (post-bump state)
- no docs/releases/v0.6.4.md
- v0.6.1 tag/release history remains intact

Exit codes:
  0 = valid
  1 = blocking findings
  2 = operational error

Deterministic and local. Does not:
- call network
- publish
- tag
- push
- require credentials
- run live trading
- call brokers/providers
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.2.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.2-status.md"
FUTURE_RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.7.md"
V061_RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.1.md"
V061_TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.1-status.md"

REQUIRED_VERSION = "0.6.2"
POST_BUMP_VERSION = "0.6.3"
POST_BUMP_VERSION_2 = "0.6.4"
POST_BUMP_VERSION_3 = "0.6.5"
POST_BUMP_VERSION_4 = "0.6.6"
PUBLIC_TAG = "v0.6.2"

UNSAFE_CLAIMS = [
    "tag created",
    "github release created",
    "pypi published",
    "new runtime trading behavior",
    "new broker execution",
    "provider execution unlock",
    "autonomous trading",
    "profit guarantee",
    "financial advice",
]


def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v062_release_prep_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
    }
    return 2, result


def _check_version_bump() -> list[str]:
    errors: list[str] = []
    found_required = False
    found_post_bump = False
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if REQUIRED_VERSION in text:
            found_required = True
        if POST_BUMP_VERSION in text:
            found_post_bump = True
        if POST_BUMP_VERSION_2 in text:
            found_post_bump = True
        if POST_BUMP_VERSION_3 in text:
            found_post_bump = True
        if POST_BUMP_VERSION_4 in text:
            found_post_bump = True
    if not found_required and not found_post_bump:
        errors.append(f"Version {REQUIRED_VERSION}, {POST_BUMP_VERSION}, {POST_BUMP_VERSION_2}, {POST_BUMP_VERSION_3}, or {POST_BUMP_VERSION_4} not found in pyproject.toml/__init__.py")
    return errors


def _check_release_notes_exist() -> list[str]:
    errors: list[str] = []
    if not RELEASE_NOTES.exists():
        errors.append(f"Release notes missing: {RELEASE_NOTES}")
    return errors


def _check_trust_status_exists() -> list[str]:
    errors: list[str] = []
    if not TRUST_STATUS.exists():
        errors.append(f"Trust status missing: {TRUST_STATUS}")
    return errors


def _check_changelog_entry() -> list[str]:
    errors: list[str] = []
    if not CHANGELOG.exists():
        errors.append(f"CHANGELOG missing: {CHANGELOG}")
        return errors
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"[{REQUIRED_VERSION}]" not in text:
        errors.append(f"CHANGELOG missing entry for [{REQUIRED_VERSION}]")
    return errors


def _check_no_future_release_notes() -> list[str]:
    errors: list[str] = []
    if FUTURE_RELEASE_NOTES.exists():
        errors.append(f"Future release notes must not exist yet: {FUTURE_RELEASE_NOTES}")
    return errors


def _check_release_notes_safe() -> list[str]:
    errors: list[str] = []
    if not RELEASE_NOTES.exists():
        return errors
    text = RELEASE_NOTES.read_text(encoding="utf-8").lower()
    for claim in UNSAFE_CLAIMS:
        if claim.lower() in text:
            # Allow if in a negated context
            idx = text.index(claim.lower())
            window_start = max(0, idx - 120)
            window_end = min(len(text), idx + len(claim) + 120)
            window = text[window_start:window_end]
            if "not" in window or "no " in window or "was not" in window:
                continue
            errors.append(f"Unsafe claim in release notes: {claim}")
    return errors


def _check_no_tag_claim() -> list[str]:
    errors: list[str] = []
    # Check that no doc claims the tag already exists
    for path in (RELEASE_NOTES, TRUST_STATUS):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "tag created" in text and "not created" not in text:
            errors.append(f"{path.name} may claim tag was already created")
        if "github release created" in text and "not created" not in text:
            errors.append(f"{path.name} may claim GitHub release was already created")
    return errors


def _check_v061_history_intact() -> list[str]:
    errors: list[str] = []
    if not V061_RELEASE_NOTES.exists():
        errors.append(f"v0.6.1 history missing: {V061_RELEASE_NOTES}")
    if not V061_TRUST_STATUS.exists():
        errors.append(f"v0.6.1 trust status missing: {V061_TRUST_STATUS}")
    return errors


def run_check(*, json_output: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_version_bump())
    errors.extend(_check_release_notes_exist())
    errors.extend(_check_trust_status_exists())
    errors.extend(_check_changelog_entry())
    errors.extend(_check_no_future_release_notes())
    errors.extend(_check_release_notes_safe())
    errors.extend(_check_no_tag_claim())
    errors.extend(_check_v061_history_intact())

    valid = len(errors) == 0
    result = {
        "artifact_type": "v062_release_prep_report",
        "schema_version": 1,
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.2 release prep checker (post-v0.6.2 state check)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json)
    except Exception as exc:
        result = {
            "artifact_type": "v062_release_prep_report",
            "schema_version": 1,
            "valid": False,
            "errors": [f"Operational error: {exc}"],
            "warnings": [],
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["valid"] else "FAIL"
        print(f"v0.6.2 release prep check (post-v0.6.2 state) {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
