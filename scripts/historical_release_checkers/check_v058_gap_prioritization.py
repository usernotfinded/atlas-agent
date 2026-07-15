#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/historical_release_checkers/check_v058_gap_prioritization.py
# PURPOSE: Verify the v0.5.8 gap prioritization JSON and docs.
# DEPS:    argparse, json, re, sys, pathlib.
# ==============================================================================

"""Verify the v0.5.8 gap prioritization JSON and docs.

Deterministic and local. Does not call the GitHub API, load credentials,
access the network, or modify repo files.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parents[2]
GAP_FILE = REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json"
GAP_DOC = REPO_ROOT / "docs" / "archive" / "legacy-plans" / "v0.5.8-gap-prioritization.md"
INVENTORY_FILE = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"

ALLOWED_PRIORITIES = {
    "must_fix",
    "should_fix",
    "could_fix",
    "defer",
    "do_not_build",
}

ALLOWED_SCOPES = {
    "docs",
    "tests",
    "cli_ux",
    "safety_check",
    "release_gate",
    "runtime_feature",
    "research_artifact",
    "ops",
}

ALLOWED_RELEASE_TARGETS = {
    "v0.5.8",
    "post_v0.5.8",
    "never",
}

ALLOWED_SAFETY_CLASSES = {
    "safe",
    "safety_sensitive",
    "protected_boundary",
    "out_of_scope",
}

REQUIRED_FIELDS = [
    "id",
    "capability_id",
    "title",
    "priority",
    "scope",
    "release_target",
    "safety_class",
    "reason",
    "acceptance_criteria",
    "non_goals",
    "required_checks",
    "protected_paths_touched",
    "reviewer_notes",
]

LIVE_PROFIT_AUTONOMOUS_KEYWORDS = [
    "live trading",
    "provider execution",
    "broker execution",
    "profit",
    "autonomous",
    "real-money",
]

SAFETY_POSTURE_PHRASES = [
    ("live trading", "disabled by default"),
    ("provider execution", "locked"),
    ("broker execution", "blocked"),
    ("not financial advice",),
    ("not production ready",),
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _check_files_exist() -> list[str]:
    errors: list[str] = []
    if not GAP_FILE.exists():
        errors.append(f"Missing gap file: {GAP_FILE.relative_to(REPO_ROOT)}")
    if not GAP_DOC.exists():
        errors.append(f"Missing gap doc: {GAP_DOC.relative_to(REPO_ROOT)}")
    if not INVENTORY_FILE.exists():
        errors.append(f"Missing inventory file: {INVENTORY_FILE.relative_to(REPO_ROOT)}")
    return errors


def _check_required_fields(gaps: dict) -> list[str]:
    errors: list[str] = []
    items = gaps.get("items", [])
    if not items:
        errors.append("No gap items found")
        return errors
    for item in items:
        item_id = item.get("id", "<unknown>")
        for field in REQUIRED_FIELDS:
            if field not in item:
                errors.append(f"Gap item '{item_id}' missing required field: {field}")
    return errors


def _check_allowed_values(gaps: dict) -> list[str]:
    errors: list[str] = []
    for item in gaps.get("items", []):
        item_id = item.get("id", "<unknown>")
        priority = item.get("priority", "")
        if priority not in ALLOWED_PRIORITIES:
            errors.append(f"Gap item '{item_id}' has invalid priority: '{priority}'")
        scope = item.get("scope", "")
        if scope not in ALLOWED_SCOPES:
            errors.append(f"Gap item '{item_id}' has invalid scope: '{scope}'")
        release_target = item.get("release_target", "")
        if release_target not in ALLOWED_RELEASE_TARGETS:
            errors.append(f"Gap item '{item_id}' has invalid release_target: '{release_target}'")
        safety_class = item.get("safety_class", "")
        if safety_class not in ALLOWED_SAFETY_CLASSES:
            errors.append(f"Gap item '{item_id}' has invalid safety_class: '{safety_class}'")
    return errors


def _check_must_fix_acceptance(gaps: dict) -> list[str]:
    errors: list[str] = []
    for item in gaps.get("items", []):
        if item.get("priority") == "must_fix":
            item_id = item.get("id", "<unknown>")
            if not item.get("acceptance_criteria", "").strip():
                errors.append(f"must_fix item '{item_id}' missing acceptance_criteria")
            if not item.get("required_checks", []):
                errors.append(f"must_fix item '{item_id}' missing required_checks")
    return errors


def _check_do_not_build_rationale(gaps: dict) -> list[str]:
    errors: list[str] = []
    for item in gaps.get("items", []):
        if item.get("priority") == "do_not_build":
            item_id = item.get("id", "<unknown>")
            reason = item.get("reason", "").strip().lower()
            if not reason:
                errors.append(f"do_not_build item '{item_id}' missing reason")
            elif not any(word in reason for word in ["safety", "out of scope", "forbidden", "legal", "boundary", "contradict"]):
                errors.append(f"do_not_build item '{item_id}' reason lacks safety/out-of-scope rationale")
    return errors


def _check_safety_class_consistency(gaps: dict) -> list[str]:
    errors: list[str] = []
    for item in gaps.get("items", []):
        item_id = item.get("id", "<unknown>")
        safety_class = item.get("safety_class", "")
        priority = item.get("priority", "")
        title = item.get("title", "").lower()

        # Safety-sensitive items should not be marked "safe"
        if safety_class == "safe" and priority in ("do_not_build", "defer"):
            for keyword in LIVE_PROFIT_AUTONOMOUS_KEYWORDS:
                if keyword in title:
                    errors.append(
                        f"Gap item '{item_id}' mentions '{keyword}' but is marked 'safe'"
                    )
                    break
    return errors


def _check_live_profit_deferred_or_rejected(gaps: dict) -> list[str]:
    errors: list[str] = []
    for item in gaps.get("items", []):
        item_id = item.get("id", "<unknown>")
        title = item.get("title", "").lower()
        priority = item.get("priority", "")
        scope = item.get("scope", "")
        # Docs and safety-check clarifications about live/profit are allowed as must_fix/should_fix
        if scope in ("docs", "safety_check", "release_gate"):
            continue
        for keyword in LIVE_PROFIT_AUTONOMOUS_KEYWORDS:
            if keyword in title and priority not in ("defer", "do_not_build"):
                errors.append(
                    f"Gap item '{item_id}' mentions '{keyword}' but is not defer/do_not_build"
                )
    return errors


def _check_capability_ids(gaps: dict) -> list[str]:
    errors: list[str] = []
    if not INVENTORY_FILE.exists():
        return errors
    try:
        inventory = _load_json(INVENTORY_FILE)
    except json.JSONDecodeError:
        return errors

    valid_ids = {cap.get("id", "") for cap in inventory.get("capabilities", [])}
    for item in gaps.get("items", []):
        cap_id = item.get("capability_id")
        if cap_id is not None and cap_id not in valid_ids:
            errors.append(
                f"Gap item '{item.get('id')}' references unknown capability_id: '{cap_id}'"
            )
    return errors


def _check_doc_safety_posture() -> list[str]:
    errors: list[str] = []
    if not GAP_DOC.exists():
        errors.append("Missing gap doc")
        return errors

    text = GAP_DOC.read_text(encoding="utf-8").lower()
    for phrase_tuple in SAFETY_POSTURE_PHRASES:
        if len(phrase_tuple) == 1:
            if phrase_tuple[0] not in text:
                errors.append(f"Gap doc missing safety phrase: '{phrase_tuple[0]}'")
        else:
            part_a, part_b = phrase_tuple
            if part_a not in text or part_b not in text:
                errors.append(f"Gap doc missing safety phrase: '{part_a} + {part_b}'")

    if "non-goals" not in text:
        errors.append("Gap doc missing non-goals section")
    if "do-not-build" not in text and "do not build" not in text:
        errors.append("Gap doc missing do-not-build section")
    return errors


def _gather() -> dict:
    all_errors: list[str] = []
    gaps: dict = {}

    all_errors.extend(_check_files_exist())
    if GAP_FILE.exists():
        try:
            gaps = _load_json(GAP_FILE)
        except json.JSONDecodeError as exc:
            all_errors.append(f"Failed to parse gap JSON: {exc}")
            gaps = {}

    if gaps:
        all_errors.extend(_check_required_fields(gaps))
        all_errors.extend(_check_allowed_values(gaps))
        all_errors.extend(_check_must_fix_acceptance(gaps))
        all_errors.extend(_check_do_not_build_rationale(gaps))
        all_errors.extend(_check_safety_class_consistency(gaps))
        all_errors.extend(_check_live_profit_deferred_or_rejected(gaps))
        all_errors.extend(_check_capability_ids(gaps))

    all_errors.extend(_check_doc_safety_posture())

    item_count = len(gaps.get("items", []))
    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "items_checked": item_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify v0.5.8 gap prioritization and docs"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("v0.5.8 gap prioritization check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"v0.5.8 gap prioritization check PASSED: "
                f"items={result['items_checked']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
