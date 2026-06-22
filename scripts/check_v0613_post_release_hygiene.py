#!/usr/bin/env python3
"""Deterministic v0.6.13 post-release hygiene checker.

Validates that after the v0.6.13 public release:

- v0.6.13 remains the current public release and v0.6.14 is the next planned
  release.
- The package/source version stays at ``0.6.13``.
- Canonical v0.6.13 records (release notes, trust status, post-release evidence)
  exist.
- The v0.6.14 plan and candidate-selection gate exist.
- No active doc claims v0.6.14 is released.
- No active doc claims the current public release is v0.6.12.
- No stale "v0.6.13 not released" wording remains in public-facing docs.
- Historical/prep docs are clearly marked archived or historical.
- No positive PyPI publication claims or forbidden unsafe claims appear.

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
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent

RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
EVIDENCE_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.13-post-release-evidence.json"
EVIDENCE_MD = REPO_ROOT / "docs" / "releases" / "v0.6.13-post-release-evidence.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.13.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.13-status.md"
V0613_PLAN = REPO_ROOT / "docs" / "releases" / "v0.6.14-plan.md"
V0613_SELECTION = REPO_ROOT / "docs" / "releases" / "v0.6.14-candidate-selection.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
README = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"
SUPERPOWERS_DIR = DOCS_DIR / "superpowers"

CURRENT_PUBLIC = "v0.6.13"
SOURCE_VERSION = "0.6.13"
NEXT_PLANNED = "v0.6.14"

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
    "v0.6.14 is released",
    "current public release v0.6.14",
    "tag v0.6.14 created",
    "github release v0.6.14 published",
    "v0.6.14 has been released",
]

STALE_V0613_NOT_RELEASED_PATTERNS = [
    re.compile(r"v0\.6\.13\s+is\s+not\s+released", re.IGNORECASE),
    re.compile(r"v0\.6\.13\s+not\s+released", re.IGNORECASE),
    re.compile(r"not\s+released.*v0\.6\.13", re.IGNORECASE),
]

STALE_CURRENT_PUBLIC_V0612_PATTERNS = [
    re.compile(r"current\s+public\s+release\s+(?:is\s+)?v0\.6\.12", re.IGNORECASE),
    re.compile(r"current\s+public\s+v0\.6\.12", re.IGNORECASE),
    re.compile(r"current\s+public:\s*v0\.6\.12", re.IGNORECASE),
]

NEGATION_HINTS = [
    "not ",
    "no ",
    "no;",
    "no,",
    "was not",
    "is not",
    "has not",
    "never",
    "does not",
    "false",
    "absent",
    "disabled",
]

# Docs that are expected to be marked as historical/archived after the v0.6.13
# cutover because they are prep/cutover planning records.
EXPECTED_HISTORICAL_MARKED_DOCS = [
    DOCS_DIR / "releases" / "v0.6.13-candidate-readiness.md",
    DOCS_DIR / "releases" / "v0.6.13-candidates.md",
    DOCS_DIR / "releases" / "v0.6.13-owner-approval.md",
    DOCS_DIR / "superpowers" / "plans" / "2026-06-16-cand017-release-candidate-readiness-plan.md",
]


class CheckError(Exception):
    """Operational error inside the checker."""


def _fail(message: str) -> tuple[int, dict[str, Any]]:
    result: dict[str, Any] = {
        "artifact_type": "v0613_post_release_hygiene_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
        "checks": [],
    }
    return 2, result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _is_negated(text: str, idx: int, phrase_len: int, window: int = 500) -> bool:
    window_start = max(0, idx - window)
    window_end = min(len(text), idx + phrase_len + window)
    window_text = text[window_start:window_end]
    return any(hint in window_text for hint in NEGATION_HINTS)


def _load_release_metadata() -> dict[str, Any]:
    if not RELEASE_METADATA.exists():
        raise CheckError(f"Release metadata missing: {RELEASE_METADATA}")
    try:
        return json.loads(RELEASE_METADATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"Invalid release metadata JSON: {exc}")


def _load_evidence_json() -> dict[str, Any]:
    if not EVIDENCE_JSON.exists():
        raise CheckError(f"Evidence JSON missing: {EVIDENCE_JSON}")
    try:
        data = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"Invalid evidence JSON: {exc}")
    if not isinstance(data, dict):
        raise CheckError("Evidence JSON must be an object")
    return data


def _check_release_metadata() -> list[str]:
    errors: list[str] = []
    data = _load_release_metadata()
    if data.get("source_version") != SOURCE_VERSION:
        errors.append(
            f"source_version mismatch: expected {SOURCE_VERSION}, got {data.get('source_version')}"
        )
    if data.get("current_public_release") != CURRENT_PUBLIC:
        errors.append(
            f"current_public_release mismatch: expected {CURRENT_PUBLIC}, got {data.get('current_public_release')}"
        )
    if data.get("next_planned_release") != NEXT_PLANNED:
        errors.append(
            f"next_planned_release mismatch: expected {NEXT_PLANNED}, got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false")
    return errors


def _check_evidence_json() -> list[str]:
    errors: list[str] = []
    try:
        data = _load_evidence_json()
    except CheckError as exc:
        errors.append(str(exc))
        return errors
    checks = [
        ("release", CURRENT_PUBLIC),
        ("source_version", SOURCE_VERSION),
        ("current_public_release", CURRENT_PUBLIC),
        ("next_planned_release", NEXT_PLANNED),
        ("pypi_published", False),
        ("live_trading_enabled", False),
        ("provider_execution_enabled", False),
        ("broker_execution_enabled", False),
    ]
    for field, expected in checks:
        actual = data.get(field)
        if actual != expected:
            errors.append(
                f"Evidence field {field!r}: expected {expected!r}, got {actual!r}"
            )
    return errors


def _check_canonical_records() -> list[str]:
    errors: list[str] = []
    required = {
        "Release notes": RELEASE_NOTES,
        "Trust status": TRUST_STATUS,
        "Post-release evidence markdown": EVIDENCE_MD,
        "Post-release evidence JSON": EVIDENCE_JSON,
    }
    for label, path in required.items():
        if not path.exists():
            errors.append(f"Canonical v0.6.13 record missing: {label} ({path})")
    return errors


def _check_v0613_docs() -> list[str]:
    errors: list[str] = []
    for label, path in (
        ("v0.6.14 plan", V0613_PLAN),
        ("v0.6.14 candidate-selection doc", V0613_SELECTION),
    ):
        if not path.exists():
            errors.append(f"Missing {label}: {path}")
    return errors


def _check_source_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing source version file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if SOURCE_VERSION not in text:
            errors.append(f"Source version {SOURCE_VERSION} not found in {path}")
    return errors


def _collect_public_facing_docs() -> list[Path]:
    """Return active public-facing docs to scan for stale/forbidden claims.

    Excludes archived docs and internal superpowers planning docs, which are not
    public-facing current docs.
    """
    docs: list[Path] = [README]
    if not DOCS_DIR.exists():
        return docs
    for path in sorted(DOCS_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in (".md", ".json", ".txt", ".yml", ".yaml"):
            continue
        if path.is_relative_to(ARCHIVE_DIR):
            continue
        if path.is_relative_to(SUPERPOWERS_DIR):
            continue
        docs.append(path)
    return sorted(set(docs))


def _check_no_v0613_release_claims(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
        text = _read_text(path).lower()
        for phrase in V0613_POSITIVE_RELEASE_CLAIMS:
            start = 0
            while True:
                idx = text.find(phrase, start)
                if idx == -1:
                    break
                if _is_negated(text, idx, len(phrase)):
                    start = idx + 1
                    continue
                try:
                    display = path.relative_to(REPO_ROOT)
                except ValueError:
                    display = path
                errors.append(
                    f"v0.6.14 release claim in {display}: {phrase!r}"
                )
                start = idx + 1
    return errors


def _check_no_stale_v0613_not_released(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
        text = _read_text(path)
        for pattern in STALE_V0613_NOT_RELEASED_PATTERNS:
            for m in pattern.finditer(text):
                try:
                    display = path.relative_to(REPO_ROOT)
                except ValueError:
                    display = path
                line_no = text[: m.start()].count("\n") + 1
                errors.append(
                    f"Stale 'v0.6.13 not released' wording in {display}:{line_no}: {m.group(0)!r}"
                )
    return errors


def _check_no_stale_current_public_v0612(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
        # Skip historical docs that legitimately discuss the v0.6.12 state.
        if "v0.6.12" in path.name:
            continue
        text = _read_text(path)
        for pattern in STALE_CURRENT_PUBLIC_V0612_PATTERNS:
            for m in pattern.finditer(text):
                try:
                    display = path.relative_to(REPO_ROOT)
                except ValueError:
                    display = path
                line_no = text[: m.start()].count("\n") + 1
                errors.append(
                    f"Stale current-public v0.6.12 claim in {display}:{line_no}: {m.group(0)!r}"
                )
    return errors


def _check_no_pypi_publish_claims(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
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
                try:
                    display = path.relative_to(REPO_ROOT)
                except ValueError:
                    display = path
                errors.append(f"Positive PyPI publish claim in {display}: {phrase!r}")
                start = idx + 1
    return errors


def _check_no_forbidden_claims(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
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
                try:
                    display = path.relative_to(REPO_ROOT)
                except ValueError:
                    display = path
                errors.append(f"Forbidden claim in {display}: {claim!r}")
                start = idx + 1
    return errors


def _check_historical_docs_marked() -> list[str]:
    errors: list[str] = []
    for path in EXPECTED_HISTORICAL_MARKED_DOCS:
        if not path.exists():
            # Missing is not a hygiene failure here; other checks handle required files.
            continue
        text = _read_text(path).lower()
        if "historical" not in text and "archived" not in text:
            try:
                display = path.relative_to(REPO_ROOT)
            except ValueError:
                display = path
            errors.append(
                f"Historical/prep doc {display} is not marked 'historical' or 'archived'"
            )
    return errors


def _successor_release_is_current() -> bool:
    """Return true once v0.6.14 has superseded the v0.6.13 public posture."""
    try:
        data = _load_release_metadata()
    except CheckError:
        return False
    return (
        data.get("source_version") == "0.6.14"
        and data.get("current_public_release") == "v0.6.14"
        and data.get("next_planned_release") == "v0.6.15"
        and data.get("pypi_published") is False
    )


def _check_successor_source_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists() or "0.6.14" not in _read_text(path):
            errors.append(f"Successor source version 0.6.14 not found in {path}")
    return errors


def run_check(*, json_output: bool = False) -> tuple[int, dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    successor_current = _successor_release_is_current()

    checks.append("release_metadata")
    if not successor_current:
        errors.extend(_check_release_metadata())

    checks.append("evidence_json")
    errors.extend(_check_evidence_json())

    checks.append("canonical_records")
    errors.extend(_check_canonical_records())

    checks.append("v0613_docs")
    errors.extend(_check_v0613_docs())

    checks.append("source_version")
    if successor_current:
        errors.extend(_check_successor_source_version())
    else:
        errors.extend(_check_source_version())

    docs = _collect_public_facing_docs()

    checks.append("no_v0613_release_claims")
    if not successor_current:
        errors.extend(_check_no_v0613_release_claims(docs))

    checks.append("no_stale_v0613_not_released")
    errors.extend(_check_no_stale_v0613_not_released(docs))

    checks.append("no_stale_current_public_v0612")
    errors.extend(_check_no_stale_current_public_v0612(docs))

    checks.append("no_pypi_publish_claims")
    errors.extend(_check_no_pypi_publish_claims(docs))

    checks.append("no_forbidden_claims")
    errors.extend(_check_no_forbidden_claims(docs))

    checks.append("historical_docs_marked")
    errors.extend(_check_historical_docs_marked())

    valid = len(errors) == 0
    result: dict[str, Any] = {
        "artifact_type": "v0613_post_release_hygiene_report",
        "schema_version": 1,
        "valid": valid,
        "expected_current_public_release": CURRENT_PUBLIC,
        "expected_source_version": SOURCE_VERSION,
        "next_planned_release": NEXT_PLANNED,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v0.6.13 post-release hygiene checker"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json)
    except Exception as exc:
        result = {
            "artifact_type": "v0613_post_release_hygiene_report",
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
        print(f"v0.6.13 post-release hygiene check {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
