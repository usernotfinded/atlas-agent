#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_feedback_taxonomy.py
# PURPOSE: Verify the local feedback label taxonomy and triage docs.
# DEPS:    argparse, json, re, sys, pathlib.
# ==============================================================================

"""Verify the local feedback label taxonomy and triage docs.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_FILE = REPO_ROOT / ".github" / "labels.yml"
TRIAGE_DOC = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
FEEDBACK_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
BUG_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
FEATURE_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml"
SAFETY_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml"
DOCS_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml"

REQUIRED_GROUPS = ["type", "area", "priority", "risk", "status"]

REQUIRED_LABELS: dict[str, list[str]] = {
    "type": [
        "type: bug",
        "type: docs",
        "type: feedback",
        "type: safety",
        "type: feature",
        "type: chore",
    ],
    "area": [
        "area: cli",
        "area: install",
        "area: docs",
        "area: research",
        "area: release-gate",
        "area: safety-model",
        "area: feedback-intake",
        "area: github-hygiene",
    ],
    "priority": [
        "priority: blocker",
        "priority: high",
        "priority: normal",
        "priority: low",
    ],
    "risk": [
        "risk: protected-boundary",
        "risk: safety-sensitive",
        "risk: credentials",
        "risk: live-trading",
        "risk: provider-execution",
        "risk: broker-execution",
    ],
    "status": [
        "status: needs-triage",
        "status: accepted",
        "status: needs-info",
        "status: rejected-out-of-scope",
        "status: duplicate",
        "status: wontfix",
    ],
}

REQUIRED_TRIAGE_DOC_PHRASES = [
    ("blocker", "non-blocker"),
    ("out of scope", "out-of-scope"),
    ("credentials",),
    ("safety bypass", "bypass safety"),
    ("live trading",),
    ("provider execution",),
    ("broker execution",),
    ("profit", "trading signal"),
]

RISK_LABEL_REQUIRED_WORDS = [
    "does not mean",
    "does not",
]

# Issue templates should reference categories compatible with the taxonomy.
# We look for category-like words in template labels or dropdown options.
TEMPLATE_COMPATIBLE_CATEGORIES = [
    "bug",
    "docs",
    "feedback",
    "safety",
    "feature",
    "install",
    "cli",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _parse_labels_yml(path: Path) -> dict[str, list[dict[str, str]]]:
    """Parse the simple YAML structure used by labels.yml without PyYAML."""
    text = path.read_text(encoding="utf-8")
    groups: dict[str, list[dict[str, str]]] = {}
    current_group: str | None = None
    current_item: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        # Top-level group key (no leading dash, ends with colon)
        m = re.match(r"^(\w+):\s*$", line)
        if m:
            current_group = m.group(1)
            groups[current_group] = []
            current_item = None
            continue

        # Start of a list item under a group
        m = re.match(r"^\s+-\s+name:\s*['\"]?(.*?)['\"]?\s*$", line)
        if m and current_group is not None:
            current_item = {"name": m.group(1).strip().strip('"').strip("'")}
            groups[current_group].append(current_item)
            continue

        # color or description field inside an item
        m = re.match(r"^\s+(color|description):\s*['\"]?(.*?)['\"]?\s*$", line)
        if m and current_item is not None:
            key = m.group(1)
            value = m.group(2).strip().strip('"').strip("'")
            current_item[key] = value
            continue

    return groups


def _check_labels_file_exists() -> list[str]:
    errors: list[str] = []
    if not LABELS_FILE.exists():
        try:
            rel = LABELS_FILE.relative_to(REPO_ROOT)
        except ValueError:
            rel = LABELS_FILE.name
        errors.append(f"Missing labels file: {rel}")
    return errors


def _check_required_groups(groups: dict[str, list[dict[str, str]]]) -> list[str]:
    errors: list[str] = []
    for group in REQUIRED_GROUPS:
        if group not in groups:
            errors.append(f"Missing label group: {group}")
    return errors


def _check_required_labels(groups: dict[str, list[dict[str, str]]]) -> list[str]:
    errors: list[str] = []
    for group, expected_names in REQUIRED_LABELS.items():
        actual_names = {item.get("name", "") for item in groups.get(group, [])}
        for name in expected_names:
            if name not in actual_names:
                errors.append(f"Missing required label in group '{group}': {name}")
    return errors


def _check_label_fields(groups: dict[str, list[dict[str, str]]]) -> list[str]:
    errors: list[str] = []
    for group, items in groups.items():
        for item in items:
            name = item.get("name", "<unnamed>")
            if not item.get("color"):
                errors.append(f"Label '{name}' missing color")
            if not item.get("description"):
                errors.append(f"Label '{name}' missing description")
    return errors


def _check_risk_label_wording(groups: dict[str, list[dict[str, str]]]) -> list[str]:
    errors: list[str] = []
    for item in groups.get("risk", []):
        desc = item.get("description", "").lower()
        if not any(word in desc for word in RISK_LABEL_REQUIRED_WORDS):
            errors.append(
                f"Risk label '{item.get('name')}' missing conservative safety wording"
            )
    return errors


def _check_triage_doc() -> list[str]:
    errors: list[str] = []
    if not TRIAGE_DOC.exists():
        try:
            rel = TRIAGE_DOC.relative_to(REPO_ROOT)
        except ValueError:
            rel = TRIAGE_DOC.name
        errors.append(f"Missing triage doc: {rel}")
        return errors

    text = TRIAGE_DOC.read_text(encoding="utf-8").lower()
    for phrase_tuple in REQUIRED_TRIAGE_DOC_PHRASES:
        if len(phrase_tuple) == 1:
            if phrase_tuple[0] not in text:
                errors.append(
                    f"Triage doc missing phrase: '{phrase_tuple[0]}'"
                )
        else:
            part_a, part_b = phrase_tuple
            if part_a not in text and part_b not in text:
                errors.append(
                    f"Triage doc missing phrase: '{part_a}' or '{part_b}'"
                )
    return errors


def _check_template_category_compatibility() -> list[str]:
    errors: list[str] = []
    templates = [
        FEEDBACK_TEMPLATE,
        BUG_TEMPLATE,
        FEATURE_TEMPLATE,
        SAFETY_TEMPLATE,
        DOCS_TEMPLATE,
    ]
    for tmpl in templates:
        if not tmpl.exists():
            errors.append(f"Missing template: {tmpl.relative_to(REPO_ROOT)}")
            continue
        text = tmpl.read_text(encoding="utf-8").lower()
        # Each template should mention at least one category-compatible word
        if not any(cat in text for cat in TEMPLATE_COMPATIBLE_CATEGORIES):
            errors.append(
                f"Template {tmpl.relative_to(REPO_ROOT)} lacks recognizable category"
            )
    return errors


def _gather() -> dict:
    all_errors: list[str] = []
    labels_data: dict[str, list[dict[str, str]]] = {}

    all_errors.extend(_check_labels_file_exists())
    if LABELS_FILE.exists():
        try:
            labels_data = _parse_labels_yml(LABELS_FILE)
        except Exception as exc:
            all_errors.append(f"Failed to parse labels.yml: {exc}")

    all_errors.extend(_check_required_groups(labels_data))
    all_errors.extend(_check_required_labels(labels_data))
    all_errors.extend(_check_label_fields(labels_data))
    all_errors.extend(_check_risk_label_wording(labels_data))
    all_errors.extend(_check_triage_doc())
    all_errors.extend(_check_template_category_compatibility())

    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "groups_checked": len(REQUIRED_GROUPS),
        "labels_checked": sum(len(v) for v in REQUIRED_LABELS.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify feedback label taxonomy and triage docs"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("Feedback taxonomy check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"Feedback taxonomy check PASSED: "
                f"groups={result['groups_checked']} "
                f"labels={result['labels_checked']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
