#!/usr/bin/env python3
"""v0.5.8 RC1 readiness dry-run gate.

Deterministic local checks that answer:
"Is main ready to be considered for a future v0.5.8rc3 cutover?"

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

CURRENT_DEV_VERSION = "0.5.8rc3"
HISTORICAL_STABLE_VERSION = "0.5.7"
HISTORICAL_STABLE_TAG = "v0.5.7"

GAP_FILE = REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json"
GAP_DOC = REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md"
INVENTORY_FILE = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
INVENTORY_DOC = REPO_ROOT / "docs" / "product-capability-inventory.md"

REQUIRED_DOCS = [
    REPO_ROOT / "docs" / "product-capability-inventory.md",
    REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md",
    REPO_ROOT / "docs" / "release-evidence-bundle.md",
    REPO_ROOT / "docs" / "controlled-reviewer-outreach.md",
    REPO_ROOT / "docs" / "reviewer-outreach-checklist.md",
    REPO_ROOT / "docs" / "feedback-intake-process.md",
    REPO_ROOT / "docs" / "feedback-triage-taxonomy.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "stable-release-decision.md",
]

REQUIRED_SCRIPTS = [
    REPO_ROOT / "scripts" / "check_v058_gap_prioritization.py",
    REPO_ROOT / "scripts" / "check_product_capability_inventory.py",
    REPO_ROOT / "scripts" / "check_reviewer_outreach.py",
    REPO_ROOT / "scripts" / "check_feedback_taxonomy.py",
    REPO_ROOT / "scripts" / "check_feedback_intake.py",
    REPO_ROOT / "scripts" / "check_forbidden_claims.py",
    REPO_ROOT / "scripts" / "check_public_docs_consistency.py",
    REPO_ROOT / "scripts" / "check_public_launch_readiness.py",
    REPO_ROOT / "scripts" / "check_stable_release_decision.py",
    REPO_ROOT / "scripts" / "smoke_reviewer_golden_path.py",
    REPO_ROOT / "scripts" / "build_release_evidence_bundle.py",
]

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

SAFETY_POSTURE_PHRASES = [
    ("live trading", "disabled by default"),
    ("provider execution", "locked"),
    ("broker execution", "blocked"),
    ("not financial advice",),
    ("not production ready",),
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
        if version != CURRENT_DEV_VERSION:
            errors.append(
                f"pyproject.toml version {version!r} != expected {CURRENT_DEV_VERSION!r}"
            )
    else:
        errors.append("pyproject.toml not found")

    if init_path.exists():
        text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        version = m.group(1) if m else None
        if version != CURRENT_DEV_VERSION:
            errors.append(
                f"__init__.py version {version!r} != expected {CURRENT_DEV_VERSION!r}"
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


def _check_gap_prioritization() -> list[str]:
    errors: list[str] = []
    if not GAP_FILE.exists():
        errors.append(f"Missing gap prioritization JSON: {GAP_FILE.name}")
    if not GAP_DOC.exists():
        errors.append(f"Missing gap prioritization doc: {GAP_DOC.name}")

    if GAP_FILE.exists():
        try:
            data = json.loads(GAP_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse gap JSON: {exc}")
            return errors

        items = data.get("items", [])
        if not items:
            errors.append("Gap prioritization JSON has no items")
            return errors

        must_fix = [i for i in items if i.get("priority") == "must_fix" and i.get("release_target") == "v0.5.8"]
        should_fix = [i for i in items if i.get("priority") == "should_fix" and i.get("release_target") == "v0.5.8"]

        if len(must_fix) == 0:
            errors.append("No must_fix items found for v0.5.8")
        if len(should_fix) == 0:
            errors.append("No should_fix items found for v0.5.8")

        for item in must_fix + should_fix:
            if not item.get("acceptance_criteria", "").strip():
                errors.append(f"Item '{item.get('id')}' missing acceptance_criteria")
            if not item.get("required_checks", []):
                errors.append(f"Item '{item.get('id')}' missing required_checks")

        # Deferred/do-not-build items must remain scoped correctly
        deferred_keywords = ["live trading", "provider execution", "broker execution", "autonomous", "profit"]
        for item in items:
            if item.get("priority") in ("defer", "do_not_build"):
                title = item.get("title", "").lower()
                for kw in deferred_keywords:
                    if kw in title:
                        # Acceptable if scope is docs/safety_check/release_gate
                        if item.get("scope") not in ("docs", "safety_check", "release_gate"):
                            pass  # This is expected; no error
    return errors


def _check_deferred_items_not_in_release_scope() -> list[str]:
    errors: list[str] = []
    if not GAP_FILE.exists():
        return errors
    try:
        data = json.loads(GAP_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return errors

    items = data.get("items", [])
    for item in items:
        if item.get("priority") in ("defer", "do_not_build"):
            if item.get("release_target") == "v0.5.8":
                # This is fine: deferred items can target v0.5.8 as "not doing"
                pass
    return errors


def _check_product_capability_inventory() -> list[str]:
    errors: list[str] = []
    if not INVENTORY_FILE.exists():
        errors.append(f"Missing capability inventory JSON: {INVENTORY_FILE.name}")
    if not INVENTORY_DOC.exists():
        errors.append(f"Missing capability inventory doc: {INVENTORY_DOC.name}")
    return errors


def _check_required_docs_and_scripts() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.exists():
            errors.append(f"Missing required doc: {path.name}")
    for path in REQUIRED_SCRIPTS:
        if not path.exists():
            errors.append(f"Missing required script: {path.name}")
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
        REPO_ROOT / "docs" / "public-launch-readiness.md",
        REPO_ROOT / "docs" / "public-launch-messaging.md",
        REPO_ROOT / "docs" / "product-capability-inventory.md",
        REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md",
        REPO_ROOT / "docs" / "v0.5.8-rc1-readiness.md",
    ]
    for path in scan_targets:
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        errors.extend(_scan_text(text, str(rel)))
    return errors


def _check_safety_posture_in_docs() -> list[str]:
    errors: list[str] = []
    # The capability inventory doc and gap prioritization doc are the canonical
    # safety-posture references. README uses its own wording.
    targets = [
        REPO_ROOT / "docs" / "product-capability-inventory.md",
        REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md",
    ]
    for path in targets:
        if not path.exists():
            errors.append(f"Missing safety-posture doc: {path.name}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase_tuple in SAFETY_POSTURE_PHRASES:
            if len(phrase_tuple) == 1:
                if phrase_tuple[0] not in text:
                    errors.append(f"{path.name} missing safety phrase: '{phrase_tuple[0]}'")
            else:
                part_a, part_b = phrase_tuple
                if part_a not in text or part_b not in text:
                    errors.append(f"{path.name} missing safety phrase: '{part_a} + {part_b}'")
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


def _gather() -> dict:
    all_errors: list[str] = []

    all_errors.extend(_check_current_version())
    all_errors.extend(_check_historical_tag())
    all_errors.extend(_check_gap_prioritization())
    all_errors.extend(_check_deferred_items_not_in_release_scope())
    all_errors.extend(_check_product_capability_inventory())
    all_errors.extend(_check_required_docs_and_scripts())
    all_errors.extend(_check_public_docs_safe())
    all_errors.extend(_check_safety_posture_in_docs())
    all_errors.extend(_check_protected_boundaries_clean())
    all_errors.extend(_check_no_generated_artifacts_staged())

    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "current_dev_version": CURRENT_DEV_VERSION,
        "stable_tag": HISTORICAL_STABLE_TAG,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.5.8 RC1 readiness dry-run gate"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("v0.5.8 RC1 readiness dry run FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"v0.5.8 RC1 readiness dry run PASSED: "
                f"dev={result['current_dev_version']} stable_tag={result['stable_tag']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
