#!/usr/bin/env python3.11
"""Validate the deterministic v0.6.14 GitHub-only post-release posture.

Exit codes: 0 pass, 1 findings, 2 operational error. This checker is local,
read-only, and performs no network, provider, broker, notification, order,
tagging, publishing, or credential operations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CURRENT_PUBLIC = "v0.6.14"
SOURCE_VERSION = "0.6.14"
PREVIOUS_PUBLIC = "v0.6.13"
NEXT_PLANNED = "v0.6.15"

METADATA = "docs/releases/release-metadata.json"
EVIDENCE_JSON = "docs/releases/v0.6.14-post-release-evidence.json"
EVIDENCE_MD = "docs/releases/v0.6.14-post-release-evidence.md"
RELEASE_NOTES = "docs/releases/v0.6.14.md"
TRUST_STATUS = "docs/trust/v0.6.14-status.md"

REQUIRED_FILES = [
    EVIDENCE_JSON,
    EVIDENCE_MD,
    RELEASE_NOTES,
    TRUST_STATUS,
    "docs/releases/v0.6.14-plan.md",
    "docs/releases/v0.6.14-candidates.md",
    "docs/releases/v0.6.14-candidates.json",
    "docs/releases/v0.6.14-candidate-selection.md",
    "docs/releases/v0.6.14-paper-portfolio-evidence.md",
    "docs/releases/v0.6.14-final-readiness-audit.md",
    "docs/releases/v0.6.15-plan.md",
    "docs/releases/v0.6.15-candidates.md",
    "docs/releases/v0.6.15-candidates.json",
    "docs/releases/v0.6.15-candidate-selection.md",
]

HISTORICAL_RECORDS = [
    "docs/releases/v0.6.14-plan.md",
    "docs/releases/v0.6.14-candidates.md",
    "docs/releases/v0.6.14-candidate-selection.md",
    "docs/releases/v0.6.14-paper-portfolio-evidence.md",
    "docs/releases/v0.6.14-final-readiness-audit.md",
]

PUBLIC_STATE_DOCS = [
    "README.md",
    "SECURITY.md",
    "docs/trust/README.md",
    "docs/public-launch-readiness.md",
    "docs/reviewer-checklist.md",
    "docs/autonomy-roadmap.md",
    "docs/release-checklist.md",
    "docs/development/main-health.md",
    "docs/public-repo-hygiene.md",
    "docs/public-faq.md",
    "docs/public-launch-messaging.md",
    "docs/security/release-readiness.md",
]

GATE_FILES = [
    "scripts/dev_check.sh",
    "scripts/ci_check.sh",
    "scripts/release_check.sh",
    ".github/workflows/ci.yml",
]

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "guaranteed returns",
    "risk-free trading",
    "zero-risk trading",
    "safe live trading",
    "production trading readiness",
    "autonomous live trading readiness",
    "ready for live",
    "will outperform the market",
]

POSITIVE_PYPI = [
    "pypi published",
    "published to pypi",
    "available on pypi",
]


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _load_json(root: Path, rel: str, errors: list[str]) -> dict[str, Any] | None:
    path = root / rel
    if not path.exists():
        errors.append(f"Missing required file: {rel}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid JSON in {rel}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {rel}")
        return None
    return value


def _check_required_files(root: Path, errors: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"Missing required file: {rel}")


def _check_metadata(root: Path, errors: list[str]) -> None:
    data = _load_json(root, METADATA, errors)
    if data is None:
        return
    expected = {
        "source_version": SOURCE_VERSION,
        "current_public_release": CURRENT_PUBLIC,
        "next_planned_release": NEXT_PLANNED,
        "pypi_published": False,
    }
    for field, value in expected.items():
        if data.get(field) != value:
            errors.append(f"release metadata {field} must be {value!r}")

    releases = data.get("releases")
    if not isinstance(releases, list):
        errors.append("release metadata releases must be a list")
        return
    records = {item.get("tag"): item for item in releases if isinstance(item, dict)}
    current = records.get(CURRENT_PUBLIC, {})
    previous = records.get(PREVIOUS_PUBLIC, {})
    current_expected = {
        "version": SOURCE_VERSION,
        "status": "current_public",
        "github_release": True,
        "pypi_published": False,
        "release_authorized": True,
        "release_type": "github_only",
        "tag_created": True,
        "github_release_created": True,
    }
    for field, value in current_expected.items():
        if current.get(field) != value:
            errors.append(f"v0.6.14 release record {field} must be {value!r}")
    if previous.get("status") != "historical":
        errors.append("v0.6.13 release record must be historical")
    if any(item.get("status") == "current_public" for tag, item in records.items() if tag != CURRENT_PUBLIC):
        errors.append("only v0.6.14 may be current_public")


def _check_source_version(root: Path, errors: list[str]) -> None:
    pyproject = _read(root, "pyproject.toml")
    init_py = _read(root, "src/atlas_agent/__init__.py")
    if not re.search(r'^version\s*=\s*"0\.6\.14"$', pyproject, re.M):
        errors.append("pyproject.toml project.version must be 0.6.14")
    if not re.search(r'^__version__\s*=\s*"0\.6\.14"$', init_py, re.M):
        errors.append("src/atlas_agent/__init__.py __version__ must be 0.6.14")


def _check_evidence(root: Path, errors: list[str]) -> None:
    data = _load_json(root, EVIDENCE_JSON, errors)
    if data is None:
        return
    expected = {
        "release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "release_type": "github_only",
        "current_public_release": CURRENT_PUBLIC,
        "next_planned_release": NEXT_PLANNED,
        "previous_public_release": PREVIOUS_PUBLIC,
        "pypi_published": False,
        "live_trading_enabled": False,
        "live_submit_enabled": False,
        "provider_execution_enabled": False,
        "broker_execution_enabled": False,
        "notifications_sent": False,
        "orders_generated_or_submitted": False,
        "protected_runtime_boundaries_changed": False,
        "created_for_github_only_cutover": True,
    }
    for field, value in expected.items():
        if data.get(field) != value:
            errors.append(f"post-release evidence {field} must be {value!r}")

    text = _read(root, EVIDENCE_MD).lower()
    for phrase in [
        "current public github-only release",
        "source/package version:** `0.6.14`",
        "pypi:** not published",
        "v0.6.15",
        "live trading and live submit remain disabled by default",
        "no orders are generated or submitted",
        "protected runtime boundaries are unchanged",
    ]:
        if phrase not in text:
            errors.append(f"post-release evidence markdown missing: {phrase}")


def _check_historical_and_planning_docs(root: Path, errors: list[str]) -> None:
    for rel in HISTORICAL_RECORDS:
        text = _read(root, rel).lower()
        if "historical" not in text:
            errors.append(f"pre-cutover record is not marked historical: {rel}")
    for rel in [
        "docs/releases/v0.6.15-plan.md",
        "docs/releases/v0.6.15-candidates.md",
        "docs/releases/v0.6.15-candidate-selection.md",
    ]:
        if "planning" not in _read(root, rel).lower():
            errors.append(f"next-line document is not planning-only: {rel}")


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 100): start + 180]
    return any(word in window for word in [
        "not ", "no ", "never ", "without ", "forbidden", "disabled",
        "does **not**", "do **not**",
        "unpublished", "does not", "do not", "isn't", "is not",
    ])


def _check_public_docs(root: Path, errors: list[str]) -> None:
    for rel in PUBLIC_STATE_DOCS:
        path = root / rel
        if not path.exists():
            errors.append(f"Missing public state doc: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        stale_patterns = [
            r"current public (?:github )?release (?:is )?`?v0\.6\.13",
            r"latest stable public github release is v0\.6\.13",
            r"next planning line (?:is )?`?v0\.6\.14",
            r"next planned release:?\s*`?v0\.6\.14",
        ]
        for pattern in stale_patterns:
            if re.search(pattern, lower):
                errors.append(f"stale release posture in {rel}: {pattern}")
        for phrase in FORBIDDEN_CLAIMS + POSITIVE_PYPI:
            for match in re.finditer(re.escape(phrase), lower):
                if not _is_negated(lower, match.start()):
                    errors.append(f"unsafe or publication claim in {rel}: {phrase}")

    readme = _read(root, "README.md")
    for phrase in [
        "Current Status (v0.6.14)",
        "`v0.6.14` is the current public GitHub release",
        "`v0.6.15` is the next planning line",
        "package/source version is `0.6.14`",
    ]:
        if phrase not in readme:
            errors.append(f"README missing post-release posture: {phrase}")


def _check_gate_integration(root: Path, errors: list[str]) -> None:
    for rel in GATE_FILES:
        text = _read(root, rel)
        if "scripts/check_v0614_post_release_hygiene.py" not in text:
            errors.append(f"{rel} missing v0.6.14 post-release hygiene checker")
        if rel != "scripts/release_check.sh" and "tests/test_v0614_post_release_hygiene.py" not in text:
            errors.append(f"{rel} missing v0.6.14 post-release hygiene tests")


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    _check_required_files(root, errors)
    if errors:
        return _payload(False, errors)
    _check_metadata(root, errors)
    _check_source_version(root, errors)
    _check_evidence(root, errors)
    _check_historical_and_planning_docs(root, errors)
    _check_public_docs(root, errors)
    _check_gate_integration(root, errors)
    return _payload(not errors, errors)


def _payload(valid: bool, errors: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": "v0614_post_release_hygiene_report",
        "schema_version": 1,
        "valid": valid,
        "current_public_release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "next_planned_release": NEXT_PLANNED,
        "pypi_published": False,
        "errors": errors,
        "warnings": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = check(Path(args.root).resolve())
    except Exception as exc:  # pragma: no cover
        result = _payload(False, [f"Operational error: {exc}"])
        code = 2
    else:
        code = 0 if result["valid"] else 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"v0.6.14 post-release hygiene check {'PASS' if result['valid'] else 'FAIL'}")
        for error in result["errors"]:
            print(f"  ERROR: {error}")
    return code


if __name__ == "__main__":
    sys.exit(main())
