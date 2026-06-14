#!/usr/bin/env python3
"""Read-only v0.6.4 release prep checker.

Supports two modes:
- Planning mode (default): validates that v0.6.4 release artifacts do not
  exist prematurely while the source version remains 0.6.3.
- Release-prep mode (--release-prep): validates that v0.6.4 release prep
  artifacts are present after the version bump.

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


REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.4.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.4-status.md"
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.4-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.4-candidates.json"
PLAN_MD = REPO_ROOT / "docs" / "releases" / "v0.6.4-plan.md"
V063_RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.3.md"
V063_TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.3-status.md"

PLANNING_VERSION = "0.6.3"
RELEASE_VERSION = "0.6.4"
PUBLIC_TAG = "v0.6.4"

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
        "artifact_type": "v064_release_prep_report",
        "schema_version": 1,
        "valid": False,
        "mode": "unknown",
        "errors": [message],
        "warnings": [],
        "checks": [],
    }
    return 2, result


def _check_planning_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if PLANNING_VERSION not in text:
            errors.append(f"Version {PLANNING_VERSION} not found in {path}")
    return errors


def _check_release_prep_version() -> list[str]:
    errors: list[str] = []
    for path in (PYPROJECT, INIT_PY):
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if RELEASE_VERSION not in text and "0.6.5" not in text and "0.6.6" not in text and "0.6.7" not in text:
            errors.append(f"Version {RELEASE_VERSION}, 0.6.6, or 0.6.7 not found in {path}")
    return errors


def _check_no_release_notes() -> list[str]:
    errors: list[str] = []
    if RELEASE_NOTES.exists():
        errors.append(f"Release notes must not exist in planning mode: {RELEASE_NOTES}")
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


def _check_changelog_entry_planning() -> list[str]:
    errors: list[str] = []
    if not CHANGELOG.exists():
        errors.append(f"CHANGELOG missing: {CHANGELOG}")
        return errors
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"[{RELEASE_VERSION}]" in text:
        errors.append(
            f"CHANGELOG must not contain [{RELEASE_VERSION}] entry in planning mode"
        )
    return errors


def _check_changelog_entry_release_prep() -> list[str]:
    errors: list[str] = []
    if not CHANGELOG.exists():
        errors.append(f"CHANGELOG missing: {CHANGELOG}")
        return errors
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"[{RELEASE_VERSION}]" not in text:
        errors.append(f"CHANGELOG missing entry for [{RELEASE_VERSION}]")
    return errors


def _check_planning_docs_exist() -> list[str]:
    errors: list[str] = []
    if not PLAN_MD.exists():
        errors.append(f"Planning doc missing: {PLAN_MD}")
    if not CANDIDATES_MD.exists():
        errors.append(f"Candidate selection doc missing: {CANDIDATES_MD}")
    if not CANDIDATES_JSON.exists():
        errors.append(f"Candidate JSON inventory missing: {CANDIDATES_JSON}")
    return errors


def _check_all_selected_candidates_implemented() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_JSON.exists():
        return errors
    try:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in candidate inventory: {exc}")
        return errors
    candidates = data.get("candidates", [])
    selected_not_implemented = [
        c["id"]
        for c in candidates
        if c.get("selected") and not c.get("implemented")
    ]
    if selected_not_implemented:
        errors.append(
            f"Selected candidates not yet implemented: {', '.join(sorted(selected_not_implemented))}"
        )
    return errors


def _check_no_unsafe_candidates_selected() -> list[str]:
    errors: list[str] = []
    if not CANDIDATES_MD.exists():
        return errors
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    accepted_start = text.find("## Accepted Candidates")
    rejected_start = text.find("## Rejected / Out-of-Scope Candidates")
    if accepted_start == -1:
        return errors
    scan_text = text[accepted_start:rejected_start if rejected_start != -1 else len(text)]
    lower = scan_text.lower()
    unsafe_phrases = [
        "provider execution unlock",
        "broker execution unlock",
        "live trading enable",
        "live submit enable",
        "autonomous trading",
        "automatic skill activation",
        "automatic learning execution",
        "kill switch bypass",
        "risk limit weaken",
        "pypi publish",
    ]
    for phrase in unsafe_phrases:
        if phrase in lower:
            errors.append(f"Unsafe scope phrase in accepted candidates: {phrase}")
    return errors


def _check_no_publish_claim() -> list[str]:
    errors: list[str] = []
    paths_to_scan = [CANDIDATES_MD, RELEASE_NOTES, TRUST_STATUS]
    for path in paths_to_scan:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        # Check for positive PyPI publish claims
        if "pypi was not published" in lower:
            continue
        if "pypi publish was not performed" in lower:
            continue
        if "pyPI was not published" in lower:
            continue
        # Detect un-negated publish claims
        for phrase in ("pypi published", "publish to pypi", "published to pypi"):
            if phrase in lower:
                idx = lower.index(phrase)
                window_start = max(0, idx - 120)
                window_end = min(len(lower), idx + len(phrase) + 120)
                window = lower[window_start:window_end]
                if "not" in window or "no " in window or "was not" in window:
                    continue
                errors.append(f"Publish claim detected without negation in {path.name}: {phrase}")
    return errors


def _check_release_notes_safe() -> list[str]:
    errors: list[str] = []
    if not RELEASE_NOTES.exists():
        return errors
    text = RELEASE_NOTES.read_text(encoding="utf-8").lower()
    for claim in UNSAFE_CLAIMS:
        if claim.lower() in text:
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
    for path in (RELEASE_NOTES, TRUST_STATUS):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "tag created" in text and "not created" not in text:
            errors.append(f"{path.name} may claim tag was already created")
        if "github release created" in text and "not created" not in text:
            errors.append(f"{path.name} may claim GitHub release was already created")
    return errors


def _check_v063_history_intact() -> list[str]:
    errors: list[str] = []
    if not V063_RELEASE_NOTES.exists():
        errors.append(f"v0.6.3 history missing: {V063_RELEASE_NOTES}")
    if not V063_TRUST_STATUS.exists():
        errors.append(f"v0.6.3 trust status missing: {V063_TRUST_STATUS}")
    return errors


def run_check(*, json_output: bool = False, release_prep: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    mode = "release-prep" if release_prep else "planning"

    if release_prep:
        checks.append("release_prep_version")
        errors.extend(_check_release_prep_version())
        checks.append("release_notes_exist")
        errors.extend(_check_release_notes_exist())
        checks.append("trust_status_exists")
        errors.extend(_check_trust_status_exists())
        checks.append("changelog_entry")
        errors.extend(_check_changelog_entry_release_prep())
    else:
        checks.append("planning_version")
        errors.extend(_check_planning_version())
        checks.append("no_release_notes")
        errors.extend(_check_no_release_notes())
        checks.append("changelog_no_release_entry")
        errors.extend(_check_changelog_entry_planning())

    checks.append("planning_docs_exist")
    errors.extend(_check_planning_docs_exist())

    checks.append("all_selected_implemented")
    errors.extend(_check_all_selected_candidates_implemented())

    checks.append("no_unsafe_selected")
    errors.extend(_check_no_unsafe_candidates_selected())

    checks.append("no_publish_claim")
    errors.extend(_check_no_publish_claim())

    if release_prep:
        checks.append("release_notes_safe")
        errors.extend(_check_release_notes_safe())
        checks.append("no_tag_claim")
        errors.extend(_check_no_tag_claim())

    checks.append("v063_history_intact")
    errors.extend(_check_v063_history_intact())

    valid = len(errors) == 0
    result = {
        "artifact_type": "v064_release_prep_report",
        "schema_version": 1,
        "valid": valid,
        "mode": mode,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.4 release prep checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--release-prep",
        action="store_true",
        help="Validate release-prep state (version bumped, artifacts present)",
    )
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json, release_prep=args.release_prep)
    except Exception as exc:
        result = {
            "artifact_type": "v064_release_prep_report",
            "schema_version": 1,
            "valid": False,
            "mode": "unknown",
            "errors": [f"Operational error: {exc}"],
            "warnings": [],
            "checks": [],
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
        mode_label = "release-prep" if args.release_prep else "planning"
        print(f"v0.6.4 release prep check ({mode_label}) {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
