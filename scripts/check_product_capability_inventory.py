#!/usr/bin/env python3
"""Verify the product capability inventory JSON and docs.

Deterministic and local. Does not call the GitHub API, load credentials,
access the network, or modify repo files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_FILE = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
INVENTORY_DOC = REPO_ROOT / "docs" / "product-capability-inventory.md"
README_FILE = REPO_ROOT / "README.md"

ALLOWED_STATUSES = {
    "implemented",
    "partial",
    "experimental",
    "disabled_by_default",
    "docs_only",
    "missing",
    "deprecated",
}

ALLOWED_CLAIM_LEVELS = {
    "safe_to_claim",
    "claim_with_limits",
    "internal_only",
    "do_not_claim",
}

REQUIRED_CAPABILITY_GROUPS = [
    "core-workspace",
    "paper-simulation",
    "research-artifacts",
    "safety-risk",
    "audit-events",
    "memory-learning",
    "automation-ops",
    "integrations",
    "public-review-release",
]

REQUIRED_FIELDS = [
    "id",
    "name",
    "group",
    "status",
    "public_claim_level",
    "cli_commands",
    "source_paths",
    "docs_paths",
    "tests_or_checks",
    "safety_notes",
    "known_gaps",
    "reviewer_notes",
]

CRITICAL_CAPABILITIES = [
    "cli-compatibility-contract",
    "golden-path-smoke-test",
    "release-evidence-bundle",
    "feedback-intake",
    "feedback-taxonomy",
    "reviewer-outreach",
    "historical-release-record-check",
]

README_CLAIM_KEYWORDS = [
    "workspace",
    "paper trading",
    "backtest",
    "risk gate",
    "approval queue",
    "memory",
    "audit log",
    "hash-chain",
    "provider",
    "broker",
    "kill switch",
    "replay",
    "dashboard",
    "routine",
    "scheduler",
    "research",
    "discipline",
]

UNSAFE_SAFE_TO_CLAIM_PHRASES = [
    "guaranteed profit",
    "zero risk",
    "risk-free",
    "safe live trading",
    "unattended live trading",
    "production trading ready",
    "autonomous trading bot",
    "ai trading bot that makes money",
    "profitable trading system",
]

SAFETY_POSTURE_PHRASES = [
    ("live trading", "disabled by default"),
    ("provider execution", "locked"),
    ("broker execution", "blocked"),
    ("not financial advice",),
    ("not production ready",),
]


def _load_inventory() -> dict:
    with open(INVENTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def _check_file_exists() -> list[str]:
    errors: list[str] = []
    if not INVENTORY_FILE.exists():
        errors.append(f"Missing inventory file: {INVENTORY_FILE.relative_to(REPO_ROOT)}")
    if not INVENTORY_DOC.exists():
        errors.append(f"Missing inventory doc: {INVENTORY_DOC.relative_to(REPO_ROOT)}")
    return errors


def _check_required_fields(inventory: dict) -> list[str]:
    errors: list[str] = []
    capabilities = inventory.get("capabilities", [])
    if not capabilities:
        errors.append("No capabilities found in inventory")
        return errors
    for cap in capabilities:
        cap_id = cap.get("id", "<unknown>")
        for field in REQUIRED_FIELDS:
            if field not in cap:
                errors.append(f"Capability '{cap_id}' missing required field: {field}")
    return errors


def _check_status_values(inventory: dict) -> list[str]:
    errors: list[str] = []
    for cap in inventory.get("capabilities", []):
        status = cap.get("status", "")
        if status not in ALLOWED_STATUSES:
            errors.append(
                f"Capability '{cap.get('id')}' has invalid status: '{status}'"
            )
    return errors


def _check_claim_levels(inventory: dict) -> list[str]:
    errors: list[str] = []
    for cap in inventory.get("capabilities", []):
        level = cap.get("public_claim_level", "")
        if level not in ALLOWED_CLAIM_LEVELS:
            errors.append(
                f"Capability '{cap.get('id')}' has invalid claim level: '{level}'"
            )
    return errors


def _check_required_groups(inventory: dict) -> list[str]:
    errors: list[str] = []
    actual_groups = {cap.get("group", "") for cap in inventory.get("capabilities", [])}
    for group in REQUIRED_CAPABILITY_GROUPS:
        if group not in actual_groups:
            errors.append(f"Missing required capability group in inventory: {group}")
    return errors


def _check_critical_capabilities(inventory: dict) -> list[str]:
    errors: list[str] = []
    actual_ids = {cap.get("id", "") for cap in inventory.get("capabilities", [])}
    for cap_id in CRITICAL_CAPABILITIES:
        if cap_id not in actual_ids:
            errors.append(f"Missing critical capability in inventory: {cap_id}")
    return errors


def _check_readme_claims_represented(inventory: dict) -> list[str]:
    errors: list[str] = []
    if not README_FILE.exists():
        errors.append("README.md not found; cannot verify claim representation")
        return errors

    readme_text = README_FILE.read_text(encoding="utf-8").lower()
    cap_names = [cap.get("name", "").lower() for cap in inventory.get("capabilities", [])]

    missing = []
    for keyword in README_CLAIM_KEYWORDS:
        if keyword in readme_text:
            # Check if any capability name roughly matches this keyword
            if not any(keyword in name for name in cap_names):
                missing.append(keyword)

    if missing:
        errors.append(
            f"README claims not represented in inventory: {', '.join(missing)}"
        )
    return errors


def _check_safe_to_claim_safety(inventory: dict) -> list[str]:
    errors: list[str] = []
    for cap in inventory.get("capabilities", []):
        if cap.get("public_claim_level") != "safe_to_claim":
            continue
        text_to_check = " ".join(
            [
                cap.get("name", ""),
                cap.get("safety_notes", ""),
                cap.get("reviewer_notes", ""),
            ]
        ).lower()
        for phrase in UNSAFE_SAFE_TO_CLAIM_PHRASES:
            if phrase in text_to_check:
                errors.append(
                    f"Capability '{cap.get('id')}' marked safe_to_claim contains unsafe phrase: '{phrase}'"
                )
    return errors


def _check_safety_notes_present(inventory: dict) -> list[str]:
    errors: list[str] = []
    safety_sensitive_statuses = {"disabled_by_default", "partial", "experimental"}
    for cap in inventory.get("capabilities", []):
        if cap.get("status") in safety_sensitive_statuses:
            if not cap.get("safety_notes", "").strip():
                errors.append(
                    f"Safety-sensitive capability '{cap.get('id')}' missing safety_notes"
                )
    return errors


def _check_inventory_doc_safety() -> list[str]:
    errors: list[str] = []
    if not INVENTORY_DOC.exists():
        errors.append("Missing inventory doc")
        return errors

    text = INVENTORY_DOC.read_text(encoding="utf-8").lower()
    for phrase_tuple in SAFETY_POSTURE_PHRASES:
        if len(phrase_tuple) == 1:
            if phrase_tuple[0] not in text:
                errors.append(f"Inventory doc missing safety phrase: '{phrase_tuple[0]}'")
        else:
            part_a, part_b = phrase_tuple
            if part_a not in text or part_b not in text:
                errors.append(
                    f"Inventory doc missing safety phrase: '{part_a} + {part_b}'"
                )
    return errors


def _check_safe_to_claim_files_exist(inventory: dict) -> list[str]:
    """Verify safe_to_claim capabilities have corresponding CLI commands or files in the repo."""
    errors: list[str] = []
    for cap in inventory.get("capabilities", []):
        if cap.get("public_claim_level") != "safe_to_claim":
            continue
        cap_id = cap.get("id", "<unknown>")

        # Non-empty cli_commands count as evidence
        if cap.get("cli_commands"):
            continue

        # Check if any referenced file exists in the repo
        found = False
        for path_list in (cap.get("source_paths", []), cap.get("docs_paths", []), cap.get("tests_or_checks", [])):
            for rel_path in path_list:
                # Some paths may be directories or patterns; check exact file existence
                candidate = REPO_ROOT / rel_path
                if candidate.exists():
                    found = True
                    break
                # Also check if it's a directory
                if candidate.is_dir():
                    found = True
                    break
            if found:
                break

        if not found:
            errors.append(
                f"Capability '{cap_id}' marked safe_to_claim has no verified CLI commands, source_paths, docs_paths, or tests_or_checks in the repo"
            )
    return errors


def _gather() -> dict:
    all_errors: list[str] = []
    inventory: dict = {}

    all_errors.extend(_check_file_exists())
    if INVENTORY_FILE.exists():
        try:
            inventory = _load_inventory()
        except json.JSONDecodeError as exc:
            all_errors.append(f"Failed to parse inventory JSON: {exc}")
            inventory = {}

    if inventory:
        all_errors.extend(_check_required_fields(inventory))
        all_errors.extend(_check_status_values(inventory))
        all_errors.extend(_check_claim_levels(inventory))
        all_errors.extend(_check_required_groups(inventory))
        all_errors.extend(_check_critical_capabilities(inventory))
        all_errors.extend(_check_readme_claims_represented(inventory))
        all_errors.extend(_check_safe_to_claim_safety(inventory))
        all_errors.extend(_check_safety_notes_present(inventory))
        all_errors.extend(_check_safe_to_claim_files_exist(inventory))
        all_errors.extend(_check_inventory_doc_safety())

    cap_count = len(inventory.get("capabilities", []))
    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "capabilities_checked": cap_count,
        "groups_checked": len(REQUIRED_CAPABILITY_GROUPS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify product capability inventory and docs"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("Product capability inventory check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"Product capability inventory check PASSED: "
                f"capabilities={result['capabilities_checked']} "
                f"groups={result['groups_checked']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
