#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_v0611_planning.py
# PURPOSE: Read-only v0.6.11 planning baseline checker.
# DEPS:    argparse, json, sys, pathlib.
# ==============================================================================

"""Read-only v0.6.11 planning baseline checker.

Validates that the v0.6.11 candidate planning artifacts exist, are well-formed,
list only safe scope, and do not claim an immediate release cutover.

Exit codes:
  0 = valid planning baseline
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

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.11-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.11-candidates.json"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.11.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.11-status.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"

EXPECTED_RELEASE = "v0.6.11"
EXPECTED_ARTIFACT_TYPE = "v0611_candidate_inventory"
EXPECTED_SOURCE_VERSION = "0.6.10"
EXPECTED_CURRENT_PUBLIC = "v0.6.10"

REQUIRED_CANDIDATE_KEYS = [
    "id",
    "title",
    "summary",
    "user_value",
    "safety_boundary",
    "risk",
    "likely_files",
    "tests_checks",
    "recommendation",
    "ranking_reason",
]

ALLOWED_RECOMMENDATIONS = {"now", "later", "defer"}

UNSAFE_SCOPE_PHRASES = [
    "provider execution unlock",
    "provider execution enabled",
    "broker execution unlock",
    "broker execution enabled",
    "live trading enable",
    "enables live trading",
    "enable live trading",
    "live trading enabled by default",
    "live submit enable",
    "autonomous trading",
    "automatic skill activation",
    "automatic learning execution",
    "kill switch bypass",
    "risk limit weaken",
]

IMMEDIATE_CUTOVER_PHRASES = [
    "pypi publish",
    "publish to pypi",
    "tag v0.6.11",
    "github release v0.6.11",
    "release cutover",
    "version bump to 0.6.11",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v0611_planning_check_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
        "checks": [],
    }
    return 2, result


def _check_candidates_md_exists() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        errors.append(f"Missing candidate selection doc: {CANDIDATES_MD}")
    return errors


def _check_candidates_json_exists() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_JSON.exists():
        errors.append(f"Missing JSON candidate inventory: {CANDIDATES_JSON}")
    return errors


def _load_candidates_json() -> tuple[dict, list[str]]:
    """Return (data, errors)."""
    if not CANDIDATES_JSON.exists():
        return {}, []
    try:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"Invalid JSON in candidate inventory: {exc}"]
    return data, []


def _check_json_top_level(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ("artifact_type", "schema_version", "release", "candidates", "rejected"):
        if key not in data:
            errors.append(f"Missing key in JSON inventory: {key}")
    if data.get("release") != EXPECTED_RELEASE:
        errors.append(
            f"JSON inventory release mismatch: expected {EXPECTED_RELEASE}, got {data.get('release')}"
        )
    if data.get("artifact_type") != EXPECTED_ARTIFACT_TYPE:
        errors.append(
            f"JSON inventory artifact_type mismatch: expected {EXPECTED_ARTIFACT_TYPE}, "
            f"got {data.get('artifact_type')}"
        )
    return errors


def _check_candidate_structure(candidates: list[dict]) -> list[str]:
    errors: list[str] = []
    for candidate in candidates:
        cid = candidate.get("id", "<missing-id>")
        for key in REQUIRED_CANDIDATE_KEYS:
            if key not in candidate:
                errors.append(f"Candidate {cid} missing required key: {key}")
        rec = candidate.get("recommendation")
        if rec is not None and rec not in ALLOWED_RECOMMENDATIONS:
            errors.append(
                f"Candidate {cid} has invalid recommendation '{rec}'; "
                f"allowed: {', '.join(sorted(ALLOWED_RECOMMENDATIONS))}"
            )
        likely_files = candidate.get("likely_files")
        if likely_files is not None and not isinstance(likely_files, list):
            errors.append(f"Candidate {cid} 'likely_files' must be a list")
        tests_checks = candidate.get("tests_checks")
        if tests_checks is not None and not isinstance(tests_checks, list):
            errors.append(f"Candidate {cid} 'tests_checks' must be a list")
        # Every candidate must have safety_boundary and acceptance_criteria
        if not candidate.get("safety_boundary"):
            errors.append(f"Candidate {cid} missing or empty safety_boundary")
        if not candidate.get("acceptance_criteria"):
            errors.append(f"Candidate {cid} missing or empty acceptance_criteria")
    return errors


def _check_markdown_mentions_candidates(candidates: list[dict]) -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        return errors
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    for candidate in candidates:
        cid = candidate.get("id")
        if not cid:
            continue
        if cid not in text:
            errors.append(f"Candidate ID {cid} not mentioned in {CANDIDATES_MD.name}")
    return errors


def _check_no_unsafe_scope(candidates: list[dict]) -> list[str]:
    """Check ALL candidates (not just selected) for unsafe scope phrases."""
    errors: list[str] = []
    for candidate in candidates:
        cid = candidate.get("id", "<missing-id>")
        text = " ".join(
            str(candidate.get(k, "")) for k in ("title", "summary", "safety_boundary", "ranking_reason")
        ).lower()
        for phrase in UNSAFE_SCOPE_PHRASES:
            if phrase in text:
                errors.append(f"Unsafe scope phrase in candidate {cid}: {phrase}")
    return errors


def _check_no_immediate_cutover(candidates: list[dict]) -> list[str]:
    errors: list[str] = []
    for candidate in candidates:
        if candidate.get("recommendation") != "now":
            continue
        cid = candidate.get("id", "<missing-id>")
        text = " ".join(
            str(candidate.get(k, "")) for k in ("title", "summary", "ranking_reason")
        ).lower()
        for phrase in IMMEDIATE_CUTOVER_PHRASES:
            if phrase in text:
                errors.append(
                    f"Immediate cutover/PyPI phrase in candidate {cid}: {phrase}"
                )
    return errors


def _check_candidate_tracking(candidates: list[dict]) -> list[str]:
    """Validate incremental implementation tracking without implying release prep."""
    errors: list[str] = []
    for candidate in candidates:
        cid = candidate.get("id", "<missing-id>")
        selected = candidate.get("selected_for_v0611")
        implemented = candidate.get("implemented")
        if not isinstance(selected, bool):
            errors.append(f"Candidate {cid} selected_for_v0611 must be a boolean")
        if not isinstance(implemented, bool):
            errors.append(f"Candidate {cid} implemented must be a boolean")
        if implemented and not selected:
            errors.append(
                f"Candidate {cid} is marked implemented without selected_for_v0611=true"
            )
        if selected and candidate.get("recommendation") != "now":
            errors.append(
                f"Candidate {cid} is selected for v0.6.11 but recommendation is "
                f"'{candidate.get('recommendation')}'"
            )
    return errors


def _check_no_live_default_candidate(candidates: list[dict]) -> list[str]:
    """No candidate should propose enabling live execution by default."""
    errors: list[str] = []
    live_phrases = [
        "live trading by default",
        "enable live by default",
        "live execution by default",
        "default to live",
        "live mode default",
    ]
    for candidate in candidates:
        cid = candidate.get("id", "<missing-id>")
        text = " ".join(
            str(candidate.get(k, "")) for k in ("title", "summary", "safety_boundary")
        ).lower()
        for phrase in live_phrases:
            if phrase in text:
                errors.append(f"Candidate {cid} proposes live default execution: {phrase}")
    return errors


def _check_no_release_notes() -> list[str]:
    errors: list[str] = []
    if RELEASE_NOTES.exists():
        errors.append(f"Release notes must not exist in planning mode: {RELEASE_NOTES}")
    return errors


def _check_no_trust_status() -> list[str]:
    errors: list[str] = []
    if TRUST_STATUS.exists():
        errors.append(f"Trust status must not exist in planning mode: {TRUST_STATUS}")
    return errors


def _check_no_changelog_entry() -> list[str]:
    errors: list[str] = []
    if not CHANGELOG.exists():
        errors.append(f"CHANGELOG missing: {CHANGELOG}")
        return errors
    text = CHANGELOG.read_text(encoding="utf-8")
    if "[0.6.11]" in text:
        errors.append("CHANGELOG must not contain [0.6.11] entry in planning mode")
    return errors


def _check_source_version_not_bumped() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "0.6.11" in text:
            errors.append(f"Version bump to 0.6.11 detected in {path}")
    return errors


def _check_source_version_is_current() -> list[str]:
    """Source version should still be 0.6.10."""
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if EXPECTED_SOURCE_VERSION not in text:
            errors.append(f"Expected source version {EXPECTED_SOURCE_VERSION} not found in {path}")
    return errors


def _check_release_metadata() -> list[str]:
    errors: list[str] = []
    if not RELEASE_METADATA.exists():
        errors.append(f"Release metadata missing: {RELEASE_METADATA}")
        return errors
    try:
        data = json.loads(RELEASE_METADATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid release metadata JSON: {exc}")
        return errors
    if data.get("source_version") != EXPECTED_SOURCE_VERSION:
        errors.append(
            f"source_version mismatch: expected {EXPECTED_SOURCE_VERSION}, got {data.get('source_version')}"
        )
    if data.get("current_public_release") != EXPECTED_CURRENT_PUBLIC:
        errors.append(
            f"current_public_release mismatch: expected {EXPECTED_CURRENT_PUBLIC}, "
            f"got {data.get('current_public_release')}"
        )
    if data.get("next_planned_release") != EXPECTED_RELEASE:
        errors.append(
            f"next_planned_release mismatch: expected {EXPECTED_RELEASE}, "
            f"got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false in planning mode")
    # v0.6.10 must be current_public in the releases array
    releases = data.get("releases", [])
    v0610_found = False
    for rel in releases:
        if rel.get("tag") == EXPECTED_CURRENT_PUBLIC:
            if rel.get("status") != "current_public":
                errors.append(
                    f"v0.6.10 release entry status must be 'current_public', "
                    f"got '{rel.get('status')}'"
                )
            v0610_found = True
    if not v0610_found:
        errors.append("v0.6.10 release entry not found in release metadata")
    return errors


def _check_no_v0611_tag_claims() -> list[str]:
    """Check that no v0.6.11 tag or release claims exist in metadata."""
    errors: list[str] = []
    if not RELEASE_METADATA.exists():
        return errors
    try:
        data = json.loads(RELEASE_METADATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return errors
    releases = data.get("releases", [])
    for rel in releases:
        if rel.get("tag") == "v0.6.11":
            errors.append("v0.6.11 must not appear as a release entry in release metadata")
    return errors


def run_check(*, json_output: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    checks.append("candidates_md_exists")
    errors.extend(_check_candidates_md_exists())

    checks.append("candidates_json_exists")
    errors.extend(_check_candidates_json_exists())

    checks.append("json_parses")
    data, json_errors = _load_candidates_json()
    errors.extend(json_errors)

    candidates: list[dict] = []
    if data:
        checks.append("json_top_level")
        errors.extend(_check_json_top_level(data))
        candidates = data.get("candidates", [])
        if not isinstance(candidates, list):
            errors.append("JSON 'candidates' must be a list")
            candidates = []

    if isinstance(candidates, list):
        checks.append("candidate_structure")
        errors.extend(_check_candidate_structure(candidates))

        checks.append("markdown_mentions_candidates")
        errors.extend(_check_markdown_mentions_candidates(candidates))

        checks.append("no_unsafe_scope")
        errors.extend(_check_no_unsafe_scope(candidates))

        checks.append("no_immediate_cutover")
        errors.extend(_check_no_immediate_cutover(candidates))

        checks.append("candidate_tracking")
        errors.extend(_check_candidate_tracking(candidates))

        checks.append("no_live_default_candidate")
        errors.extend(_check_no_live_default_candidate(candidates))

    checks.append("no_release_notes")
    errors.extend(_check_no_release_notes())

    checks.append("no_trust_status")
    errors.extend(_check_no_trust_status())

    checks.append("no_changelog_entry")
    errors.extend(_check_no_changelog_entry())

    checks.append("source_version_not_bumped")
    errors.extend(_check_source_version_not_bumped())

    checks.append("source_version_is_current")
    errors.extend(_check_source_version_is_current())

    checks.append("release_metadata")
    errors.extend(_check_release_metadata())

    checks.append("no_v0611_tag_claims")
    errors.extend(_check_no_v0611_tag_claims())

    valid = len(errors) == 0
    result = {
        "artifact_type": "v0611_planning_check_report",
        "schema_version": 1,
        "valid": valid,
        "mode": "planning",
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.11 planning baseline checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json)
    except Exception as exc:
        result = {
            "artifact_type": "v0611_planning_check_report",
            "schema_version": 1,
            "valid": False,
            "mode": "unknown",
            "errors": [f"Operational error: {exc}"],
            "warnings": [],
            "checks": [],
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = "PASS" if result["valid"] else "FAIL"
        print(f"v0.6.11 planning baseline check ({result['mode']}) {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
