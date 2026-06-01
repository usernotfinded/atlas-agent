#!/usr/bin/env python3
"""v0.5.8 stable release verification checker.

Deterministic local checks that verify the stable v0.5.8 release record remains
intact after main has moved on to the next development version.

Historical RC tags (v0.5.8rc1 through v0.5.8rc5) are allowed to exist and do not
need to match current HEAD. The stable tag (v0.5.8) is verified as a protected
historical release tag and is not expected to match current HEAD after the next
development cycle opens.

This script does NOT:
- create tags
- publish packages
- call GitHub API
- access the network
- load credentials
- modify repo files
- invoke subprocess via a shell interpreter

Exit codes:
  0  pass
  2  fail
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_VERSION = "0.5.9.dev0"
STABLE_RELEASE_VERSION = "0.5.8"
HISTORICAL_STABLE_VERSION = "0.5.7"
HISTORICAL_STABLE_TAG = "v0.5.7"
ACTIVE_RELEASE_TAG = "v0.5.8"

# Forbidden positive claims about live trading / profit / autonomy.
FORBIDDEN_POSITIVE_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
]


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _git_show(tag: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{tag}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _check_current_version() -> list[str]:
    errors: list[str] = []
    pyproject_path = REPO_ROOT / "pyproject.toml"
    init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version")
        if version != EXPECTED_VERSION:
            errors.append(
                f"pyproject.toml version {version!r} != expected {EXPECTED_VERSION!r}"
            )
    else:
        errors.append("pyproject.toml not found")

    if init_path.exists():
        text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        version = m.group(1) if m else None
        if version != EXPECTED_VERSION:
            errors.append(
                f"__init__.py version {version!r} != expected {EXPECTED_VERSION!r}"
            )
    else:
        errors.append("src/atlas_agent/__init__.py not found")

    return errors


def _check_historical_tag() -> list[str]:
    errors: list[str] = []
    tag_pyproject = _git_show(HISTORICAL_STABLE_TAG, "pyproject.toml")
    if not tag_pyproject:
        errors.append(
            f"Could not read pyproject.toml from tag {HISTORICAL_STABLE_TAG}. "
            "Run `git fetch --tags origin` locally, or ensure GitHub Actions checkout "
            "uses `fetch-depth: 0`, `fetch-tags: true`, and `git fetch --force --tags origin`."
        )
    else:
        try:
            version = tomllib.loads(tag_pyproject).get("project", {}).get("version")
        except Exception:
            version = None
        if version != HISTORICAL_STABLE_VERSION:
            errors.append(
                f"Tag {HISTORICAL_STABLE_TAG} pyproject.toml version {version!r} != {HISTORICAL_STABLE_VERSION!r}"
            )

    tag_init = _git_show(HISTORICAL_STABLE_TAG, "src/atlas_agent/__init__.py")
    if not tag_init:
        errors.append(
            f"Could not read __init__.py from tag {HISTORICAL_STABLE_TAG}. "
            "Run `git fetch --tags origin` locally, or ensure GitHub Actions checkout "
            "uses `fetch-depth: 0`, `fetch-tags: true`, and `git fetch --force --tags origin`."
        )
    else:
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', tag_init, re.MULTILINE)
        version = m.group(1) if m else None
        if version != HISTORICAL_STABLE_VERSION:
            errors.append(
                f"Tag {HISTORICAL_STABLE_TAG} __init__.py version {version!r} != {HISTORICAL_STABLE_VERSION!r}"
            )

    return errors


def _check_release_notes_exist() -> list[str]:
    errors: list[str] = []
    path = REPO_ROOT / "docs" / "releases" / f"{ACTIVE_RELEASE_TAG}.md"
    if not path.exists():
        errors.append(f"Missing release notes: {path.relative_to(REPO_ROOT)}")
    return errors


def _check_changelog_has_stable_section() -> list[str]:
    errors: list[str] = []
    path = REPO_ROOT / "CHANGELOG.md"
    if not path.exists():
        errors.append("CHANGELOG.md not found")
        return errors
    text = path.read_text(encoding="utf-8")
    if f"[{STABLE_RELEASE_VERSION}]" not in text:
        errors.append(f"CHANGELOG.md missing [{STABLE_RELEASE_VERSION}] section")
    return errors


def _check_readme_current_status() -> list[str]:
    errors: list[str] = []
    path = REPO_ROOT / "README.md"
    if not path.exists():
        errors.append("README.md not found")
        return errors
    text = path.read_text(encoding="utf-8")
    if EXPECTED_VERSION not in text:
        errors.append("README.md missing current development version reference")
    if ACTIVE_RELEASE_TAG not in text:
        errors.append("README.md missing current version reference")
    if "latest stable public release" not in text.lower():
        errors.append("README.md should indicate v0.5.8 is the latest stable public release")
    return errors


def _scan_text(text: str, rel_path: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()

    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
        for m in re.finditer(re.escape(phrase), lower):
            sentence_start = max(0, m.start() - 120)
            sentence_end = min(len(lower), m.end() + 120)
            sentence = lower[sentence_start:sentence_end]
            negative_indicators = (
                "not ", "does not", "never", "no ", "avoid",
                "disclaimer", "prohibited", "forbidden", "must not",
                "cannot", "do not", "is not", "are not", "without",
                "fail closed", "not yet", "not implemented", "not enabled",
                "not authorized", "not a ", "not ready", "remains disabled",
                "remains locked", "remains blocked",
            )
            if not any(ind in sentence for ind in negative_indicators):
                errors.append(
                    f"[{rel_path}] Forbidden positive claim '{phrase}'"
                )

    return errors


def _check_public_docs_safe() -> list[str]:
    errors: list[str] = []
    scan_targets = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "releases" / "v0.5.8.md",
        REPO_ROOT / "docs" / "public-launch-readiness.md",
        REPO_ROOT / "docs" / "public-launch-messaging.md",
        REPO_ROOT / "docs" / "product-capability-inventory.md",
    ]
    for path in scan_targets:
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        errors.extend(_scan_text(text, str(rel)))
    return errors


def _check_protected_boundaries_clean() -> list[str]:
    errors: list[str] = []
    protected_paths = [
        "src/atlas_agent/config",
        "src/atlas_agent/brokers",
        "src/atlas_agent/execution",
        "src/atlas_agent/safety",
        "src/atlas_agent/risk",
    ]
    for p in protected_paths:
        result = subprocess.run(
            ["git", "diff", "--", p],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            errors.append(f"Protected path '{p}' has uncommitted changes")
        result_cached = subprocess.run(
            ["git", "diff", "--cached", "--", p],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result_cached.stdout.strip():
            errors.append(f"Protected path '{p}' has staged changes")
    return errors


def _check_no_generated_artifacts_staged() -> list[str]:
    errors: list[str] = []
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for f in staged:
        if f.startswith("artifacts/release_evidence/"):
            errors.append(f"Generated evidence artifact staged: {f}")
    return errors


def _list_historical_rc_tags() -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list", "v0.5.8rc*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    all_tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    return sorted(all_tags)


def _check_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
    """Check whether the stable release tag exists and still contains v0.5.8.

    The stable release tag is allowed to differ from HEAD after main advances.

    Returns:
        (errors, tag_state, tag_commit, head_commit, tag_matches_head)
    """
    errors: list[str] = []

    head_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    head_commit = head_result.stdout.strip() if head_result.returncode == 0 else None

    tag_result = subprocess.run(
        ["git", "tag", "--list", ACTIVE_RELEASE_TAG],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    tag_exists = bool(tag_result.stdout.strip())

    if not tag_exists:
        errors.append(f"{ACTIVE_RELEASE_TAG} tag is missing.")
        return errors, "missing", None, head_commit, False

    # Tag exists; verify it resolves and has the stable release version.
    tag_rev_result = subprocess.run(
        ["git", "rev-parse", f"{ACTIVE_RELEASE_TAG}" + "^{}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    tag_commit = tag_rev_result.stdout.strip() if tag_rev_result.returncode == 0 else None

    if tag_commit is None:
        errors.append(
            f"{ACTIVE_RELEASE_TAG} tag exists locally but cannot be resolved."
        )
        return errors, "unresolvable", None, head_commit, False

    tag_pyproject = _git_show(ACTIVE_RELEASE_TAG, "pyproject.toml")
    try:
        tag_version = tomllib.loads(tag_pyproject).get("project", {}).get("version")
    except Exception:
        tag_version = None
    if tag_version != STABLE_RELEASE_VERSION:
        errors.append(
            f"Tag {ACTIVE_RELEASE_TAG} pyproject.toml version {tag_version!r} != {STABLE_RELEASE_VERSION!r}"
        )

    tag_init = _git_show(ACTIVE_RELEASE_TAG, "src/atlas_agent/__init__.py")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', tag_init, re.MULTILINE)
    init_version = m.group(1) if m else None
    if init_version != STABLE_RELEASE_VERSION:
        errors.append(
            f"Tag {ACTIVE_RELEASE_TAG} __init__.py version {init_version!r} != {STABLE_RELEASE_VERSION!r}"
        )

    tag_matches_head = tag_commit == head_commit
    if errors:
        return errors, "present_invalid", tag_commit, head_commit, tag_matches_head
    if not tag_matches_head:
        return errors, "present_historical", tag_commit, head_commit, False

    return errors, "present_matches_head", tag_commit, head_commit, True


def _gather() -> dict:
    all_errors: list[str] = []

    all_errors.extend(_check_current_version())
    all_errors.extend(_check_historical_tag())
    all_errors.extend(_check_release_notes_exist())
    all_errors.extend(_check_changelog_has_stable_section())
    all_errors.extend(_check_readme_current_status())
    all_errors.extend(_check_public_docs_safe())
    all_errors.extend(_check_protected_boundaries_clean())
    all_errors.extend(_check_no_generated_artifacts_staged())

    tag_errors, tag_state, tag_commit, head_commit, tag_matches_head = _check_tag_state()
    all_errors.extend(tag_errors)

    historical_rc_tags = _list_historical_rc_tags()

    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "expected_version": EXPECTED_VERSION,
        "stable_release_version": STABLE_RELEASE_VERSION,
        "stable_tag": HISTORICAL_STABLE_TAG,
        "active_release": ACTIVE_RELEASE_TAG,
        "historical_rc_tags": historical_rc_tags,
        "tag_state": tag_state,
        "tag_commit": tag_commit,
        "head_commit": head_commit,
        "tag_matches_head": tag_matches_head,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.5.8 stable cutover verification checker"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("v0.5.8 stable cutover check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"v0.5.8 stable cutover check PASSED: "
                f"current={result['expected_version']} stable_tag={result['active_release']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
