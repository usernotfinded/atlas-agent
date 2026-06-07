#!/usr/bin/env python3
"""Read-only v0.6.1 patch candidate selection checker.

Verifies that the patch candidate selection document exists, contains
required sections, respects safety boundaries, and does not claim
unsafe runtime scope.

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
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.1-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.1-candidates.json"
RELEASE_NOTES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.1.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

REQUIRED_MD_SECTIONS = [
    "## Selection criteria",
    "## Candidate table",
    "## Accepted candidates",
    "## Rejected / deferred candidates",
    "## Safety boundaries",
    "## Non-goals",
]

FORBIDDEN_SELECTED_PHRASES = [
    "provider execution unlock",
    "broker execution unlock",
    "live trading enable",
    "live submit enable",
    "autonomous trading",
    "automatic skill activation",
    "kill switch bypass",
    "risk limit weaken",
    "pypi publish",
    "pyPI publish",
]

FORBIDDEN_CLAIM_PHRASES = [
    "publish to pypi",
    "publish to PyPI",
    "pypi published",
    "pyPI published",
    "tag v0.6.1",
    "release v0.6.1",
    "github release v0.6.1",
]


def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v061_candidate_check_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
    }
    return 2, result


def _check_candidates_md_exists() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        errors.append(f"Missing candidate selection doc: {CANDIDATES_MD}")
    return errors


def _check_candidates_md_sections() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        return errors
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    for section in REQUIRED_MD_SECTIONS:
        if section not in text:
            errors.append(f"Missing section in candidate doc: {section}")
    return errors


def _check_no_release_notes() -> list[str]:
    errors: list[str] = []
    if RELEASE_NOTES_MD.exists():
        errors.append(f"Release notes file must not exist yet: {RELEASE_NOTES_MD}")
    return errors


def _check_no_version_bump() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "0.6.1" in text:
            errors.append(f"Version bump to 0.6.1 detected in {path}")
    return errors


def _check_no_unsafe_selected() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        return errors
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    # Only scan the "Accepted candidates" section; rejected/deferred items may
    # mention unsafe scope for explicit exclusion.
    accepted_start = text.find("## Accepted candidates")
    rejected_start = text.find("## Rejected / deferred candidates")
    if accepted_start == -1:
        return errors  # missing section is caught elsewhere
    scan_text = text[accepted_start:rejected_start if rejected_start != -1 else len(text)]
    lower = scan_text.lower()
    for phrase in FORBIDDEN_SELECTED_PHRASES:
        if phrase.lower() in lower:
            errors.append(f"Unsafe scope phrase detected in accepted candidates: {phrase}")
    return errors


def _check_no_publish_claim() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        return errors
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        if phrase in text:
            # Allow the phrase if it appears in a rejection or non-goals context
            # by checking the surrounding sentence for negation
            idx = text.find(phrase)
            window_start = max(0, idx - 120)
            window_end = min(len(text), idx + len(phrase) + 120)
            window = text[window_start:window_end].lower()
            if "not" in window or "no " in window or "defer" in window or "reject" in window:
                continue
            errors.append(f"Publish/release claim detected without negation: {phrase}")
    return errors


def _check_json_exists() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_JSON.exists():
        errors.append(f"Missing JSON candidate inventory: {CANDIDATES_JSON}")
    return errors


def _check_json_schema() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_JSON.exists():
        return errors
    try:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in candidate inventory: {exc}")
        return errors
    for key in ("artifact_type", "schema_version", "release", "candidates", "rejected"):
        if key not in data:
            errors.append(f"Missing key in JSON inventory: {key}")
    return errors


def run_check(*, json_output: bool = False, release_prep: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_candidates_md_exists())
    errors.extend(_check_candidates_md_sections())
    if not release_prep:
        errors.extend(_check_no_release_notes())
        errors.extend(_check_no_version_bump())
    else:
        # In release-prep mode, verify the expected files exist
        if not RELEASE_NOTES_MD.exists():
            errors.append(f"Release notes file must exist in release-prep mode: {RELEASE_NOTES_MD}")
        for path in (PYPROJECT, INIT_PY):
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if "0.6.1" not in text and "0.6.2" not in text and "0.6.3" not in text and "0.6.4" not in text:
                    errors.append(f"Version bump to 0.6.1 or later missing in {path}")
    errors.extend(_check_no_unsafe_selected())
    errors.extend(_check_no_publish_claim())
    errors.extend(_check_json_exists())
    errors.extend(_check_json_schema())

    valid = len(errors) == 0
    result = {
        "artifact_type": "v061_candidate_check_report",
        "schema_version": 1,
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.1 patch candidate selection checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--release-prep", action="store_true", help="Allow version bump and release notes (release-prep mode)")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json, release_prep=args.release_prep)
    except Exception as exc:
        result = {
            "artifact_type": "v061_candidate_check_report",
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
        print(f"v0.6.1 candidate check {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
