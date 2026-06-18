#!/usr/bin/env python3
"""Read-only v0.6.12 public release cutover checker.

Validates that, after the CAND-019 public cutover:
- source/package version is 0.6.12;
- release metadata records v0.6.12 as the current public release and v0.6.13 as next;
- v0.6.11 is historical;
- the annotated tag and GitHub Release v0.6.12 exist;
- PyPI was not published;
- required docs exist and are public-release coherent;
- owner approval gate records that only tag/GitHub Release were approved;
- no unsafe claims appear in release-facing docs.

Exit codes:
  0 = pass
  1 = blocking findings
  2 = operational error

Deterministic and local except for optional GitHub Release visibility via `gh`,
which is treated as a warning if unavailable. Does not:
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

PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.12.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.12-status.md"
OWNER_APPROVAL = REPO_ROOT / "docs" / "releases" / "v0.6.12-owner-approval.md"
RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"

RELEASE_VERSION = "0.6.12"
PUBLIC_TAG = "v0.6.12"
PREVIOUS_PUBLIC_TAG = "v0.6.11"
NEXT_PLANNED_TAG = "v0.6.13"

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "no-risk",
    "safe live trading",
    "production trading readiness",
    "autonomous trading readiness",
]

UNSAFE_EXECUTION_PHRASES = [
    "live trading enabled",
    "live submit enabled",
    "provider execution enabled",
    "broker execution enabled",
    "autonomous trading enabled",
]

PYPI_PUBLISH_PHRASES = [
    "pypi published",
    "publish to pypi",
    "published to pypi",
]


def _fail(message: str) -> tuple[int, dict]:
    result = {
        "artifact_type": "v0612_release_cutover_report",
        "schema_version": 1,
        "valid": False,
        "errors": [message],
        "warnings": [],
        "checks": [],
    }
    return 2, result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


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

    releases = data.get("releases", [])
    v0612 = next((r for r in releases if r.get("tag") == PUBLIC_TAG), None)
    if v0612 is None:
        errors.append(f"Release metadata missing {PUBLIC_TAG} record")
    else:
        if v0612.get("status") != "current_public":
            errors.append(f"{PUBLIC_TAG} status must be 'current_public'")
        if v0612.get("github_release") is not True:
            errors.append(f"{PUBLIC_TAG} github_release must be true")
        if v0612.get("pypi_published") is not False:
            errors.append(f"{PUBLIC_TAG} pypi_published must be false")

    v0611 = next((r for r in releases if r.get("tag") == PREVIOUS_PUBLIC_TAG), None)
    if v0611 is not None and v0611.get("status") != "historical":
        errors.append(f"{PREVIOUS_PUBLIC_TAG} status must be 'historical'")
    return errors


def _check_required_docs() -> list[str]:
    errors: list[str] = []
    for path, label in (
        (RELEASE_NOTES, "Release notes"),
        (TRUST_STATUS, "Trust status"),
        (OWNER_APPROVAL, "Owner approval gate"),
        (CHANGELOG, "CHANGELOG"),
    ):
        if not path.exists():
            errors.append(f"{label} missing: {path}")
    return errors


def _check_owner_approval() -> list[str]:
    errors: list[str] = []
    text = _read_text(OWNER_APPROVAL).lower()
    if not text:
        errors.append("Owner approval gate is empty or missing")
        return errors
    if "public cutover" not in text:
        errors.append("Owner approval gate missing public cutover section")
    if "pypi" not in text or ("not" not in text and "no " not in text):
        # Require an explicit PyPI non-approval statement.
        errors.append("Owner approval gate does not clearly state PyPI is not approved")
    # Approval record table should show public cutover approved.
    if "public cutover" in text:
        # Look for the row containing "public cutover" and "yes".
        lines = text.splitlines()
        found = False
        for line in lines:
            if "public cutover" in line and "yes" in line:
                found = True
                break
        if not found:
            errors.append("Owner approval gate does not record public cutover as approved")
    return errors


def _check_trust_status_public() -> list[str]:
    errors: list[str] = []
    text = _read_text(TRUST_STATUS).lower()
    if not text:
        return errors
    # Must positively identify v0.6.12 as current public.
    if "current public release" not in text or PUBLIC_TAG not in text:
        errors.append("Trust status does not identify v0.6.12 as current public release")
    # Must not claim v0.6.12 is still prepared / not released.
    for phrase in ("prepared, not yet tagged or released", "not yet tagged", "not released"):
        if phrase in text:
            errors.append(f"Trust status still says v0.6.12 is {phrase!r}")
    return errors


def _check_no_pypi_claim(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in PYPI_PUBLISH_PHRASES:
            start = 0
            while True:
                idx = text.find(phrase, start)
                if idx == -1:
                    break
                window_start = max(0, idx - 120)
                window_end = min(len(text), idx + len(phrase) + 120)
                window = text[window_start:window_end]
                if "not" in window or "no " in window or "was not" in window:
                    start = idx + 1
                    continue
                errors.append(f"Positive PyPI publish claim in {path.name}: {phrase!r}")
                start = idx + 1
    return errors


def _check_no_forbidden_claims(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for claim in FORBIDDEN_CLAIMS:
            if claim in text:
                idx = text.index(claim)
                window_start = max(0, idx - 120)
                window_end = min(len(text), idx + len(claim) + 120)
                window = text[window_start:window_end]
                if "not" in window or "no " in window or "was not" in window:
                    continue
                errors.append(f"Forbidden claim in {path.name}: {claim!r}")
    return errors


def _check_safety_defaults(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    combined = ""
    for path in paths:
        if path.exists():
            combined += path.read_text(encoding="utf-8").lower() + "\n"
    for phrase in UNSAFE_EXECUTION_PHRASES:
        if phrase in combined:
            idx = combined.index(phrase)
            window_start = max(0, idx - 120)
            window_end = min(len(combined), idx + len(phrase) + 120)
            window = combined[window_start:window_end]
            if "not" in window or "no " in window or "was not" in window:
                continue
            errors.append(f"Unsafe execution enablement claim: {phrase!r}")
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
            warnings.append(f"Local git tag {PUBLIC_TAG} not found")
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
            warnings.append(f"GitHub Release {PUBLIC_TAG} not found")
    except Exception as exc:
        warnings.append(f"Could not query GitHub Release status: {exc}")
    return errors, warnings


def run_check(*, json_output: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    checks.append("source_version")
    errors.extend(_check_source_version())

    checks.append("release_metadata")
    errors.extend(_check_release_metadata())

    checks.append("required_docs")
    errors.extend(_check_required_docs())

    checks.append("owner_approval")
    errors.extend(_check_owner_approval())

    checks.append("trust_status_public")
    errors.extend(_check_trust_status_public())

    scanned_paths = [RELEASE_NOTES, TRUST_STATUS, OWNER_APPROVAL]

    checks.append("no_pypi_claim")
    errors.extend(_check_no_pypi_claim(scanned_paths))

    checks.append("no_forbidden_claims")
    errors.extend(_check_no_forbidden_claims(scanned_paths))

    checks.append("safety_defaults")
    errors.extend(_check_safety_defaults(scanned_paths))

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
        "artifact_type": "v0612_release_cutover_report",
        "schema_version": 1,
        "valid": valid,
        "public_tag": PUBLIC_TAG,
        "previous_public_tag": PREVIOUS_PUBLIC_TAG,
        "next_planned_tag": NEXT_PLANNED_TAG,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    code = 0 if valid else 1
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v0.6.12 public release cutover checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        code, result = run_check(json_output=args.json)
    except Exception as exc:
        result = {
            "artifact_type": "v0612_release_cutover_report",
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
        print(f"v0.6.12 release cutover check {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
