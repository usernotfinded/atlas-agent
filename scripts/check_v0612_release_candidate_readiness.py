#!/usr/bin/env python3
"""Deterministic static checker for v0.6.12 release-candidate / release-prep readiness.

Validates that the v0.6.12 candidate consolidation docs exist, cite every
CAND-001..CAND-016 candidate, keep v0.6.11 as the current public release, accept
the 0.6.12 source/package version bump and release-prep artifacts, and preserve
safety invariants.

Exit codes:
  0 = pass
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

READINESS_MD = REPO_ROOT / "docs" / "releases" / "v0.6.12-candidate-readiness.md"
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.12-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.12-candidates.json"
RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.12.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.12-status.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
README = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

EXPECTED_CURRENT_PUBLIC = "v0.6.12"
EXPECTED_SOURCE_VERSION = "0.6.12"
NEXT_PLANNED = "v0.6.14"

CAND_IDS = [f"CAND-{i:03d}" for i in range(1, 17)]

FORBIDDEN_PUBLIC_CLAIMS = [
    "published to pypi",
]

NEGATION_HINTS = [
    "not",
    "no ",
    "no\n",
    "was not",
    "is not",
    "has not been",
    "avoid",
    "next planning line",
    "not released",
    "planned",
    "candidate",
    "readiness",
    "preparation",
    "preparing",
    "prepared",
    "owner approval",
]

REQUIRED_SAFETY_PHRASES = [
    (
        "live trading disabled",
        [
            "live trading disabled",
            "live trading is disabled",
            "live trading remains disabled",
            "live trading disabled by default",
            "live trading remains disabled by default",
            "live trading is not the default",
        ],
    ),
    (
        "broker execution disabled",
        [
            "broker execution disabled",
            "broker execution is disabled",
            "broker execution remains disabled",
            "broker execution disabled by default",
            "broker execution remains disabled by default",
        ],
    ),
    (
        "provider execution disabled",
        [
            "provider execution disabled",
            "provider execution is disabled",
            "provider execution remains disabled",
            "provider execution disabled by default",
            "provider execution remains disabled by default",
        ],
    ),
    (
        "no PyPI publish",
        [
            "no pypi publish",
            "pypi publish disabled",
            "no pypi",
            "not published to pypi",
            "pypi was not published",
            "pypi publish was not performed",
            "pypi not published",
            "pypi published | false",
            "not published on pypi",
        ],
    ),
    (
        "tag and release created",
        [
            "tag: created",
            "github release: created",
            "tag and github release",
            "tag created",
            "github release created",
        ],
    ),
]

REQUIRED_LINK_SUBSTRINGS = [
    "reviewer-trust-snapshot",
    "release-assurance-bundle-demo",
    "release-assurance-diagnostics",
    "release-assurance-diagnostics-artifact-validate",
    "release-assurance-artifact-retention-audit",
    "v0.6.12-owner-approval",
]

FORBIDDEN_READINESS_CLAIMS = [
    "guaranteed profit",
    "no-risk",
    "safe live trading",
    "production trading readiness",
    "autonomous trading readiness",
]


def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v0612_release_candidate_readiness_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
        "checks": [],
    }
    return 2, result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _check_readiness_md_exists() -> list[str]:
    errors: list[str] = []
    if not READINESS_MD.exists():
        errors.append(f"Missing readiness doc: {READINESS_MD}")
    return errors


def _check_candidates_md_exists() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        errors.append(f"Missing candidate index doc: {CANDIDATES_MD}")
    return errors


def _check_candidates_json_exists_and_valid() -> tuple[list[str], dict]:
    errors: list[str] = []
    data: dict = {}
    if not CANDIDATES_JSON.exists():
        errors.append(f"Missing candidate JSON index: {CANDIDATES_JSON}")
        return errors, data
    try:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in candidate index: {exc}")
    return errors, data


def _check_cand_coverage(readiness_text: str, candidates_text: str) -> list[str]:
    errors: list[str] = []
    combined = f"{readiness_text}\n{candidates_text}".lower()
    missing = [cid for cid in CAND_IDS if cid.lower() not in combined]
    if missing:
        errors.append(
            f"Candidate IDs not mentioned in readiness doc or candidate index: {', '.join(missing)}"
        )
    return errors


def _check_release_metadata() -> list[str]:
    errors: list[str] = []
    if not RELEASE_METADATA.exists():
        errors.append(f"Missing release metadata: {RELEASE_METADATA}")
        return errors
    try:
        data = json.loads(RELEASE_METADATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid release metadata JSON: {exc}")
        return errors
    current_public = data.get("current_public_release")
    if current_public != EXPECTED_CURRENT_PUBLIC:
        errors.append(
            f"current_public_release mismatch: expected {EXPECTED_CURRENT_PUBLIC}, got {current_public}"
        )
    source_version = data.get("source_version")
    if source_version != EXPECTED_SOURCE_VERSION:
        errors.append(
            f"source_version mismatch: expected {EXPECTED_SOURCE_VERSION}, got {source_version}"
        )
    if data.get("next_planned_release") != "v0.6.14":
        errors.append(
            f"next_planned_release should be {NEXT_PLANNED}, got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false")
    releases = data.get("releases", [])
    v0612 = next((r for r in releases if r.get("tag") == "v0.6.12"), None)
    if v0612 is None:
        errors.append("Release metadata missing v0.6.12 record")
    else:
        if v0612.get("status") != "current_public":
            errors.append("v0.6.12 release metadata status must be 'current_public'")
        if v0612.get("github_release") is not True:
            errors.append("v0.6.12 github_release must be true")
        if v0612.get("pypi_published") is not False:
            errors.append("v0.6.12 pypi_published must be false")

    v0611 = next((r for r in releases if r.get("tag") == "v0.6.11"), None)
    if v0611 is not None and v0611.get("status") != "historical":
        errors.append("v0.6.11 release metadata status must be 'historical'")
    return errors


def _scan_public_docs_for_premature_claims() -> list[str]:
    """Scan README.md and docs/ for forbidden v0.6.12 public-release claims.

    Internal agent planning docs under docs/superpowers/ are excluded because
    they describe checker requirements and naturally echo forbidden phrases.
    """
    errors: list[str] = []
    paths: list[Path] = [README] if README.exists() else []
    if DOCS_DIR.exists():
        paths.extend(
            p
            for p in DOCS_DIR.rglob("*")
            if p.is_file()
            and p.suffix in (".md", ".json", ".txt", ".yml", ".yaml")
            and "docs/superpowers" not in str(p)
        )

    for path in paths:
        text = _read_text(path)
        lower = text.lower()
        for phrase in FORBIDDEN_PUBLIC_CLAIMS:
            phrase_lower = phrase.lower()
            start = 0
            while True:
                idx = lower.find(phrase_lower, start)
                if idx == -1:
                    break
                window_start = max(0, idx - 160)
                window_end = min(len(lower), idx + len(phrase_lower) + 160)
                window = lower[window_start:window_end]
                if not any(hint in window for hint in NEGATION_HINTS):
                    try:
                        display_path = path.relative_to(REPO_ROOT)
                    except ValueError:
                        display_path = path
                    errors.append(
                        f"Premature public-release claim in {display_path}: {phrase!r}"
                    )
                start = idx + 1
    return errors


def _check_source_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing source version file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if EXPECTED_SOURCE_VERSION not in text:
            errors.append(
                f"Expected active source version {EXPECTED_SOURCE_VERSION} not found in {path}"
            )
    return errors


def _check_release_prep_artifacts() -> list[str]:
    errors: list[str] = []
    if not RELEASE_NOTES.exists():
        errors.append(f"Release notes missing: {RELEASE_NOTES}")
    if not TRUST_STATUS.exists():
        errors.append(f"Trust status missing: {TRUST_STATUS}")
    if CHANGELOG.exists():
        if f"[{EXPECTED_SOURCE_VERSION}]" not in CHANGELOG.read_text(encoding="utf-8"):
            errors.append(f"CHANGELOG missing entry for [{EXPECTED_SOURCE_VERSION}]")
    else:
        errors.append(f"CHANGELOG missing: {CHANGELOG}")
    return errors


def _check_required_safety_phrases(readiness_text: str, candidates_text: str) -> list[str]:
    """Check required safety phrases are present in readiness doc or candidate index."""
    errors: list[str] = []
    combined = f"{readiness_text}\n{candidates_text}".lower()
    for label, variants in REQUIRED_SAFETY_PHRASES:
        if not any(variant in combined for variant in variants):
            errors.append(f"Missing required safety phrase: {label}")
    return errors


def _check_required_links(readiness_text: str, candidates_text: str) -> list[str]:
    errors: list[str] = []
    combined = f"{readiness_text}\n{candidates_text}".lower()
    for substr in REQUIRED_LINK_SUBSTRINGS:
        if substr.lower() not in combined:
            errors.append(
                f"Required workflow/checker doc link missing: {substr}"
            )
    return errors


def _check_forbidden_claims_in_readiness(readiness_text: str) -> list[str]:
    errors: list[str] = []
    lower = readiness_text.lower()
    for claim in FORBIDDEN_READINESS_CLAIMS:
        claim_lower = claim.lower()
        start = 0
        while True:
            idx = lower.find(claim_lower, start)
            if idx == -1:
                break
            window_start = max(0, idx - 80)
            window_end = min(len(lower), idx + len(claim_lower) + 80)
            window = lower[window_start:window_end]
            if not any(hint in window for hint in NEGATION_HINTS):
                errors.append(f"Forbidden claim in readiness doc: {claim!r}")
            start = idx + 1
    return errors


def _check_no_stale_wording(readiness_text: str) -> list[str]:
    errors: list[str] = []
    lower = readiness_text.lower()
    stale = "current public v0.6.11"
    if stale in lower:
        errors.append(f"Stale wording found in readiness doc: {stale!r}")
    return errors


def run_check(*, json_output: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    checks.append("readiness_md_exists")
    errors.extend(_check_readiness_md_exists())

    checks.append("candidates_md_exists")
    errors.extend(_check_candidates_md_exists())

    checks.append("candidates_json_exists_and_valid")
    json_errors, _ = _check_candidates_json_exists_and_valid()
    errors.extend(json_errors)

    readiness_text = _read_text(READINESS_MD)
    candidates_text = _read_text(CANDIDATES_MD)

    checks.append("cand_coverage")
    errors.extend(_check_cand_coverage(readiness_text, candidates_text))

    checks.append("release_metadata")
    errors.extend(_check_release_metadata())

    checks.append("no_premature_public_claims")
    errors.extend(_scan_public_docs_for_premature_claims())

    checks.append("source_version_matches_expected")
    errors.extend(_check_source_version())

    checks.append("release_prep_artifacts_present")
    errors.extend(_check_release_prep_artifacts())

    checks.append("required_safety_phrases")
    errors.extend(_check_required_safety_phrases(readiness_text, candidates_text))

    checks.append("required_workflow_links")
    errors.extend(_check_required_links(readiness_text, candidates_text))

    checks.append("no_forbidden_claims")
    errors.extend(_check_forbidden_claims_in_readiness(readiness_text))

    checks.append("no_stale_wording")
    errors.extend(_check_no_stale_wording(readiness_text))

    valid = len(errors) == 0
    result = {
        "artifact_type": "v0612_release_candidate_readiness_report",
        "schema_version": 1,
        "valid": valid,
        "expected_current_public_release": EXPECTED_CURRENT_PUBLIC,
        "expected_source_version": EXPECTED_SOURCE_VERSION,
        "next_planned_release": NEXT_PLANNED,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v0.6.12 release-candidate / release-prep readiness checker"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json)
    except Exception as exc:
        result = {
            "artifact_type": "v0612_release_candidate_readiness_report",
            "schema_version": 1,
            "valid": False,
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
        print(f"v0.6.12 release candidate readiness check {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
