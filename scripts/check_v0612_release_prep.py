#!/usr/bin/env python3
"""Read-only v0.6.12 release prep checker.

Supports three modes:
- Planning mode (default): validates that v0.6.12 release artifacts do not
  exist prematurely while the source version remains 0.6.11.
- Release-prep mode (--release-prep): validates that v0.6.12 release prep
  artifacts are present and that v0.6.12 is prepared but not public (for use
  before cutover).
- Post-release mode (--post-release): validates that v0.6.12 is the current
  public release, v0.6.11 is historical, tag and GitHub Release exist, and
  PyPI was not published (for use after cutover).

Exit codes:
  0 = valid
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
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.12-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.12-candidates.json"
V0611_RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "v0.6.11.md"
V0611_TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.11-status.md"
README = REPO_ROOT / "README.md"
SECURITY = REPO_ROOT / "SECURITY.md"
TRUST_README = REPO_ROOT / "docs" / "trust" / "README.md"
RELEASE_METADATA = REPO_ROOT / "docs" / "releases" / "release-metadata.json"

PLANNING_VERSION = "0.6.11"
RELEASE_VERSION = "0.6.12"
PUBLIC_TAG = "v0.6.12"
CURRENT_PUBLIC_TAG = "v0.6.11"
NEXT_PLANNED_TAG = "v0.6.13"

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
        "artifact_type": "v0612_release_prep_report",
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
        if RELEASE_VERSION not in text:
            errors.append(f"Version {RELEASE_VERSION} not found in {path}")
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


def _check_planning_docs_exist() -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not CANDIDATES_MD.exists():
        errors.append(f"Candidate selection doc missing: {CANDIDATES_MD}")
    if not CANDIDATES_JSON.exists():
        warnings.append(f"Candidate JSON inventory missing: {CANDIDATES_JSON}")
    return errors, warnings


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
        if c.get("selected_for_v0612") and not c.get("implemented")
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
        if "pypi was not published" in lower:
            continue
        if "pypi publish was not performed" in lower:
            continue
        if "pypi was not published" in lower:
            continue
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


def _check_v0611_history_intact() -> list[str]:
    errors: list[str] = []
    if not V0611_RELEASE_NOTES.exists():
        errors.append(f"v0.6.11 history missing: {V0611_RELEASE_NOTES}")
    if not V0611_TRUST_STATUS.exists():
        errors.append(f"v0.6.11 trust status missing: {V0611_TRUST_STATUS}")
    return errors


def _check_readme_version() -> list[str]:
    errors: list[str] = []
    if not README.exists():
        errors.append(f"README missing: {README}")
        return errors
    text = README.read_text(encoding="utf-8")
    if "package/source version is `0.6.12`" not in text:
        errors.append("README does not state package/source version is 0.6.12")
    if "Current Status (v0.6.12)" not in text:
        errors.append("README does not contain Current Status (v0.6.12)")
    return errors


def _check_security_version() -> list[str]:
    errors: list[str] = []
    if not SECURITY.exists():
        errors.append(f"SECURITY.md missing: {SECURITY}")
        return errors
    text = SECURITY.read_text(encoding="utf-8")
    if "0.6.12 (main)" not in text:
        errors.append("SECURITY.md does not list 0.6.12 (main) as current source version")
    if "0.6.11" not in text:
        errors.append("SECURITY.md does not mention 0.6.11")
    return errors


def _check_trust_readme_version() -> list[str]:
    errors: list[str] = []
    if not TRUST_README.exists():
        errors.append(f"Trust README missing: {TRUST_README}")
        return errors
    text = TRUST_README.read_text(encoding="utf-8")
    if "Source package version on `main`: `0.6.12`" not in text:
        errors.append("Trust README does not state source package version on main is 0.6.12")
    if "Public v0.6.11" not in text:
        errors.append("Trust README does not mention public v0.6.11")
    return errors


def _check_release_metadata_release_prep() -> list[str]:
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
    if data.get("current_public_release") != CURRENT_PUBLIC_TAG:
        errors.append(
            f"current_public_release mismatch: expected {CURRENT_PUBLIC_TAG}, got {data.get('current_public_release')}"
        )
    if data.get("next_planned_release") != NEXT_PLANNED_TAG:
        errors.append(
            f"next_planned_release mismatch: expected {NEXT_PLANNED_TAG}, got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false in release-prep mode")
    releases = data.get("releases", [])
    v0612 = next((r for r in releases if r.get("tag") == PUBLIC_TAG), None)
    if v0612 is None:
        errors.append(f"Release metadata missing {PUBLIC_TAG} record")
    else:
        if v0612.get("status") != "prepared":
            errors.append(f"{PUBLIC_TAG} status must be 'prepared'")
        if v0612.get("github_release") is not False:
            errors.append(f"{PUBLIC_TAG} github_release must be false")
        if v0612.get("pypi_published") is not False:
            errors.append(f"{PUBLIC_TAG} pypi_published must be false")
    v0611 = next((r for r in releases if r.get("tag") == CURRENT_PUBLIC_TAG), None)
    if v0611 is not None and v0611.get("status") != "current_public":
        errors.append("v0.6.11 status must be 'current_public'")
    return errors


def _check_release_metadata_post_release() -> list[str]:
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
    if data.get("next_planned_release") != "v0.6.13":
        errors.append(
            f"next_planned_release mismatch: expected v0.6.13, got {data.get('next_planned_release')}"
        )
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false in post-release mode")
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
    v0611 = next((r for r in releases if r.get("tag") == CURRENT_PUBLIC_TAG), None)
    if v0611 is not None and v0611.get("status") != "historical":
        errors.append("v0.6.11 status must be 'historical'")
    return errors


def _check_no_v0612_local_tag() -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Check local git tag v0.6.12 does not exist."""
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
        elif PUBLIC_TAG in result.stdout.splitlines():
            errors.append(f"Local git tag {PUBLIC_TAG} already exists")
    except FileNotFoundError:
        warnings.append("git not available; cannot verify local tag absence")
    return errors, warnings


def _check_v0612_local_tag_exists() -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Check local git tag v0.6.12 exists."""
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


def _check_no_v0612_github_release() -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Check GitHub Release v0.6.12 does not exist."""
    errors: list[str] = []
    warnings: list[str] = []
    if shutil.which("gh") is None:
        warnings.append("GitHub CLI (gh) not available; cannot verify GitHub Release absence")
        return errors, warnings
    try:
        result = subprocess.run(
            ["gh", "release", "view", PUBLIC_TAG, "--repo", "usernotfinded/atlas-agent"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode == 0:
            errors.append(f"GitHub Release {PUBLIC_TAG} already exists")
    except Exception as exc:
        warnings.append(f"Could not query GitHub Release status: {exc}")
    return errors, warnings


def _check_v0612_github_release_exists() -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Check GitHub Release v0.6.12 exists."""
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


def _check_no_premature_public_claims() -> list[str]:
    """Scan release notes and trust status for premature public-release claims."""
    errors: list[str] = []
    for path in (RELEASE_NOTES, TRUST_STATUS):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        # Positive claims that v0.6.12 is public/tagged/published
        if f"{PUBLIC_TAG} is the current public" in text:
            errors.append(f"{path.name} claims {PUBLIC_TAG} is current public release")
        if f"{PUBLIC_TAG} is the latest stable public" in text:
            errors.append(f"{path.name} claims {PUBLIC_TAG} is latest stable public release")
        if f"github release: {PUBLIC_TAG} (current public)" in text:
            errors.append(f"{path.name} claims GitHub release {PUBLIC_TAG} is current public")
        # Check for "tagged and published" applied to v0.6.12
        if f"{PUBLIC_TAG} (tagged" in text and "published" in text:
            errors.append(f"{path.name} may claim {PUBLIC_TAG} is tagged and published")
    return errors


def run_check(
    *,
    json_output: bool = False,
    release_prep: bool = False,
    post_release: bool = False,
) -> tuple[int, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    if release_prep and post_release:
        mode = "unknown"
        errors.append("Cannot use --release-prep and --post-release together")
    elif release_prep:
        mode = "release-prep"
    elif post_release:
        mode = "post-release"
    else:
        mode = "planning"

    if release_prep or post_release:
        checks.append("release_prep_version")
        errors.extend(_check_release_prep_version())
        checks.append("release_notes_exist")
        errors.extend(_check_release_notes_exist())
        checks.append("trust_status_exists")
        errors.extend(_check_trust_status_exists())
        checks.append("changelog_entry")
        errors.extend(_check_changelog_entry_release_prep())
        checks.append("readme_version")
        errors.extend(_check_readme_version())
        checks.append("security_version")
        errors.extend(_check_security_version())
        checks.append("trust_readme_version")
        errors.extend(_check_trust_readme_version())
        checks.append("release_metadata")
        if post_release:
            errors.extend(_check_release_metadata_post_release())
        else:
            errors.extend(_check_release_metadata_release_prep())
        if release_prep:
            checks.append("no_v0612_local_tag")
            tag_errors, tag_warnings = _check_no_v0612_local_tag()
            errors.extend(tag_errors)
            warnings.extend(tag_warnings)
        else:
            checks.append("v0612_local_tag_exists")
            tag_errors, tag_warnings = _check_v0612_local_tag_exists()
            errors.extend(tag_errors)
            warnings.extend(tag_warnings)
        if release_prep:
            checks.append("no_premature_public_claims")
            errors.extend(_check_no_premature_public_claims())
        if release_prep:
            checks.append("no_v0612_github_release")
            gh_errors, gh_warnings = _check_no_v0612_github_release()
            errors.extend(gh_errors)
            warnings.extend(gh_warnings)
        else:
            checks.append("v0612_github_release_exists")
            gh_errors, gh_warnings = _check_v0612_github_release_exists()
            errors.extend(gh_errors)
            warnings.extend(gh_warnings)
    else:
        checks.append("planning_version")
        errors.extend(_check_planning_version())
        checks.append("no_release_notes")
        errors.extend(_check_no_release_notes())
        checks.append("changelog_no_release_entry")
        errors.extend(_check_changelog_entry_planning())

    checks.append("planning_docs_exist")
    doc_errors, doc_warnings = _check_planning_docs_exist()
    errors.extend(doc_errors)
    warnings.extend(doc_warnings)

    checks.append("all_selected_implemented")
    errors.extend(_check_all_selected_candidates_implemented())

    checks.append("no_unsafe_selected")
    errors.extend(_check_no_unsafe_candidates_selected())

    checks.append("no_publish_claim")
    errors.extend(_check_no_publish_claim())

    if release_prep or post_release:
        checks.append("release_notes_safe")
        errors.extend(_check_release_notes_safe())
        if release_prep:
            checks.append("no_tag_claim")
            errors.extend(_check_no_tag_claim())

    checks.append("v0611_history_intact")
    errors.extend(_check_v0611_history_intact())

    valid = len(errors) == 0
    result = {
        "artifact_type": "v0612_release_prep_report",
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
    parser = argparse.ArgumentParser(description="v0.6.12 release prep checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--release-prep",
        action="store_true",
        help="Validate release-prep state (version bumped, artifacts present, not public)",
    )
    parser.add_argument(
        "--post-release",
        action="store_true",
        help="Validate post-release state (v0.6.12 is current public release)",
    )
    args = parser.parse_args(argv)

    try:
        code, result = run_check(
            json_output=args.json,
            release_prep=args.release_prep,
            post_release=args.post_release,
        )
    except Exception as exc:
        result = {
            "artifact_type": "v0612_release_prep_report",
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
        mode_label = result["mode"]
        print(f"v0.6.12 release prep check ({mode_label}) {status}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}")
        if result["warnings"]:
            for warn in result["warnings"]:
                print(f"  WARN: {warn}")

    return code


if __name__ == "__main__":
    sys.exit(main())
