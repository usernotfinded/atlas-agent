#!/usr/bin/env python3
"""Read-only v0.6.12 post-release evidence bundle checker.

Validates the post-release evidence bundle at
``docs/releases/v0.6.12-post-release-evidence.json`` and the docs it references:

- Evidence JSON schema and exact field values.
- Evidence markdown doc exists.
- Release notes and trust status files exist.
- v0.6.13 plan exists and does not positively claim v0.6.13 is released.
- No forbidden unsafe claims in release-facing docs.
- No positive PyPI publish claims in release-facing docs.
- Source/package version is ``0.6.12`` in ``pyproject.toml`` and
  ``src/atlas_agent/__init__.py``.
- ``docs/releases/release-metadata.json`` top-level fields are coherent.

Exit codes:
  0 = pass
  1 = blocking findings
  2 = operational error

Deterministic and local by default. The optional ``--verify-github`` flag uses
``gh`` and ``git`` to confirm the tag/GitHub Release exist; unavailability of
those tools is treated as a warning, not an error. This checker does not:

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
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

EVIDENCE_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.12-post-release-evidence.json"
EVIDENCE_MD = REPO_ROOT / "docs" / "releases" / "v0.6.12-post-release-evidence.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.12.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.12-status.md"
V0613_PLAN = REPO_ROOT / "docs" / "releases" / "v0.6.13-plan.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"

RELEASE_VERSION = "0.6.12"
PUBLIC_TAG = "v0.6.12"
NEXT_PLANNED_TAG = "v0.6.13"
EXPECTED_MAIN_COMMIT_PREFIX = "c6f4ddc"
EXPECTED_MAIN_COMMIT_SHA = "c6f4ddc572902bbc04d8f8b4b262b626999a7abd"
EXPECTED_PUSH_CI_RUN_ID = "27696853914"

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "no-risk",
    "safe live trading",
    "production trading readiness",
    "autonomous trading readiness",
]

PYPI_PUBLISH_PHRASES = [
    "pypi published",
    "publish to pypi",
    "published to pypi",
]

V0613_POSITIVE_RELEASE_CLAIMS = [
    "v0.6.13 is released",
    "current public release v0.6.13",
    "tag v0.6.13 created",
    "github release v0.6.13 published",
]

SCANNED_DOC_PATHS = [
    EVIDENCE_MD,
    EVIDENCE_JSON,
    V0613_PLAN,
    RELEASE_NOTES,
    TRUST_STATUS,
]


def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v0612_post_release_evidence_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
        "checks": [],
        "evidence": {},
    }
    return 2, result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _is_negated(text: str, idx: int, phrase_len: int, window: int = 120) -> bool:
    """Return True if 'not', 'no ', or 'was not' appears near idx."""
    window_start = max(0, idx - window)
    window_end = min(len(text), idx + phrase_len + window)
    window_text = text[window_start:window_end]
    return "not" in window_text or "no " in window_text or "was not" in window_text


def _load_evidence() -> tuple[dict, list[str]]:
    """Load evidence JSON; return (data, errors)."""
    errors: list[str] = []
    if not EVIDENCE_JSON.exists():
        errors.append(f"Evidence JSON missing: {EVIDENCE_JSON}")
        return {}, errors
    try:
        data = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid evidence JSON: {exc}")
        return {}, errors
    if not isinstance(data, dict):
        errors.append("Evidence JSON must be an object")
        return {}, errors
    return data, errors


def _check_evidence_schema(data: dict) -> list[str]:
    """Validate exact expected values in the evidence JSON."""
    errors: list[str] = []

    def _expect(field: str, expected) -> None:
        actual = data.get(field)
        if actual != expected:
            errors.append(
                f"Evidence field {field!r}: expected {expected!r}, got {actual!r}"
            )

    _expect("schema_version", 1)
    _expect("release", PUBLIC_TAG)
    _expect("source_version", RELEASE_VERSION)
    _expect("tag", PUBLIC_TAG)
    _expect("github_release", PUBLIC_TAG)
    _expect("push_ci_run_id", EXPECTED_PUSH_CI_RUN_ID)
    _expect("current_public_release", PUBLIC_TAG)
    _expect("next_planned_release", NEXT_PLANNED_TAG)
    _expect("pypi_published", False)
    _expect("live_trading_enabled", False)
    _expect("provider_execution_enabled", False)
    _expect("broker_execution_enabled", False)
    _expect("protected_runtime_boundaries_changed", False)
    _expect("forbidden_claims_check", True)
    _expect("release_check_quick", True)
    _expect("created_after_cutover", True)

    main_commit = data.get("main_commit")
    if main_commit not in (EXPECTED_MAIN_COMMIT_SHA, EXPECTED_MAIN_COMMIT_PREFIX) and not (
        isinstance(main_commit, str) and main_commit.startswith(EXPECTED_MAIN_COMMIT_PREFIX)
    ):
        errors.append(
            f"Evidence field 'main_commit': expected to start with {EXPECTED_MAIN_COMMIT_PREFIX!r} "
            f"or equal full SHA, got {main_commit!r}"
        )

    release_notes_path = data.get("release_notes_path")
    if release_notes_path != "docs/releases/v0.6.12.md":
        errors.append(
            f"Evidence field 'release_notes_path': expected 'docs/releases/v0.6.12.md', "
            f"got {release_notes_path!r}"
        )
    elif not (REPO_ROOT / release_notes_path).exists():
        errors.append(f"Release notes file does not exist: {release_notes_path}")

    trust_status_path = data.get("trust_status_path")
    if trust_status_path != "docs/trust/v0.6.12-status.md":
        errors.append(
            f"Evidence field 'trust_status_path': expected 'docs/trust/v0.6.12-status.md', "
            f"got {trust_status_path!r}"
        )
    elif not (REPO_ROOT / trust_status_path).exists():
        errors.append(f"Trust status file does not exist: {trust_status_path}")

    return errors


def _check_required_docs() -> list[str]:
    errors: list[str] = []
    for path, label in (
        (EVIDENCE_MD, "Post-release evidence markdown"),
        (V0613_PLAN, "v0.6.13 plan"),
    ):
        if not path.exists():
            errors.append(f"{label} missing: {path}")
    return errors


def _check_v0613_plan_no_release_claims() -> list[str]:
    """Ensure v0.6.13 plan does not positively claim v0.6.13 is released."""
    errors: list[str] = []
    if not V0613_PLAN.exists():
        return errors
    text = V0613_PLAN.read_text(encoding="utf-8").lower()
    for phrase in V0613_POSITIVE_RELEASE_CLAIMS:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx == -1:
                break
            if _is_negated(text, idx, len(phrase)):
                start = idx + 1
                continue
            errors.append(f"v0.6.13 plan has positive release claim: {phrase!r}")
            start = idx + 1
    return errors


def _check_no_forbidden_claims(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = _read_text(path).lower()
        for claim in FORBIDDEN_CLAIMS:
            start = 0
            while True:
                idx = text.find(claim, start)
                if idx == -1:
                    break
                if _is_negated(text, idx, len(claim)):
                    start = idx + 1
                    continue
                errors.append(f"Forbidden claim in {path.name}: {claim!r}")
                start = idx + 1
    return errors


def _check_no_pypi_publish_claims(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = _read_text(path).lower()
        for phrase in PYPI_PUBLISH_PHRASES:
            start = 0
            while True:
                idx = text.find(phrase, start)
                if idx == -1:
                    break
                if _is_negated(text, idx, len(phrase)):
                    start = idx + 1
                    continue
                errors.append(f"Positive PyPI publish claim in {path.name}: {phrase!r}")
                start = idx + 1
    return errors


def _check_source_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if RELEASE_VERSION not in text:
            errors.append(f"Version {RELEASE_VERSION} not found in {path}")
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

    if data.get("source_version") != RELEASE_VERSION:
        errors.append(
            f"source_version mismatch: expected {RELEASE_VERSION}, got {data.get('source_version')}"
        )
    if data.get("current_public_release") != PUBLIC_TAG:
        errors.append(
            f"current_public_release mismatch: expected {PUBLIC_TAG}, got {data.get('current_public_release')}"
        )
    if data.get("next_planned_release") != "v0.6.14"_TAG:
        errors.append(
            f"next_planned_release mismatch: expected {NEXT_PLANNED_TAG}, got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false")
    return errors


def _check_local_tag_exists() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        result = subprocess.run(
            ["git", "tag", "--list", PUBLIC_TAG],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            warnings.append(f"Could not list local git tags: {result.stderr.strip()}")
        elif PUBLIC_TAG not in result.stdout.splitlines():
            errors.append(f"Local git tag {PUBLIC_TAG} not found")
    except FileNotFoundError:
        warnings.append("git not available; cannot verify local tag existence")
    return errors, warnings


def _check_github_release_exists() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if shutil.which("gh") is None:
        warnings.append("GitHub CLI (gh) not available; cannot verify GitHub Release existence")
        return errors, warnings
    try:
        result = subprocess.run(
            ["gh", "release", "view", PUBLIC_TAG, "--repo", "usernotfinded/atlas-agent"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            errors.append(f"GitHub Release {PUBLIC_TAG} not found")
    except Exception as exc:
        warnings.append(f"Could not query GitHub Release status: {exc}")
    return errors, warnings


def run_check(*, json_output: bool = False, verify_github: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    checks.append("load_evidence")
    evidence, load_errors = _load_evidence()
    errors.extend(load_errors)

    if evidence:
        checks.append("evidence_schema")
        errors.extend(_check_evidence_schema(evidence))

    checks.append("required_docs")
    errors.extend(_check_required_docs())

    checks.append("v0613_plan_no_release_claims")
    errors.extend(_check_v0613_plan_no_release_claims())

    checks.append("no_forbidden_claims")
    errors.extend(_check_no_forbidden_claims(SCANNED_DOC_PATHS))

    checks.append("no_pypi_publish_claims")
    errors.extend(_check_no_pypi_publish_claims(SCANNED_DOC_PATHS))

    checks.append("source_version")
    errors.extend(_check_source_version())

    checks.append("release_metadata")
    errors.extend(_check_release_metadata())

    if verify_github:
        checks.append("local_tag_exists")
        tag_errors, tag_warnings = _check_local_tag_exists()
        errors.extend(tag_errors)
        warnings.extend(tag_warnings)

        checks.append("github_release_exists")
        gh_errors, gh_warnings = _check_github_release_exists()
        errors.extend(gh_errors)
        warnings.extend(gh_warnings)

    valid = len(errors) == 0
    result = {
        "artifact_type": "v0612_post_release_evidence_report",
        "schema_version": 1,
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "evidence": evidence,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.12 post-release evidence checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--verify-github",
        action="store_true",
        help="Optionally verify tag/GitHub Release exist via git and gh (not run in local gates)",
    )
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json, verify_github=args.verify_github)
    except Exception as exc:
        result = {
            "artifact_type": "v0612_post_release_evidence_report",
            "schema_version": 1,
            "valid": False,
            "errors": [f"Operational error: {exc}"],
            "warnings": [],
            "checks": [],
            "evidence": {},
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
        print(f"v0.6.12 post-release evidence check {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
