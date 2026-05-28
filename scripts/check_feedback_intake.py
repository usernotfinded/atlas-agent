#!/usr/bin/env python3
"""Verify public feedback intake templates, docs, and safety warnings.

Deterministic and local. Does not call network, load credentials, or modify repo files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_TEMPLATES = [
    ".github/ISSUE_TEMPLATE/reviewer_feedback.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/docs_issue.yml",
    ".github/ISSUE_TEMPLATE/safety_concern.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
]

REQUIRED_DOCS = [
    "docs/feedback-intake-process.md",
    "docs/public-feedback-checklist.md",
    "docs/feedback-request-guide.md",
]

REQUIRED_SAFETY_WARNINGS = [
    ("paste secrets", "credentials"),
    ("real-money", "broker"),
    ("bypass", "safety"),
    ("profit", "trading"),
    ("live trading", "default"),
    ("not financial advice",),
]

UNSAFE_PHRASES = [
    "guaranteed profit",
    "zero risk",
    "risk-free",
    "safe live trading",
    "unattended live trading",
    "can't lose",
]

CREDENTIAL_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}"),
]

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9_/-]+"),
    re.compile(r"/private/var/[A-Za-z0-9_/-]+"),
]


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _check_templates_exist() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_TEMPLATES:
        path = REPO_ROOT / rel
        if not path.exists():
            errors.append(f"Missing template: {rel}")
    return errors


def _check_docs_exist() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_DOCS:
        path = REPO_ROOT / rel
        if not path.exists():
            errors.append(f"Missing doc: {rel}")
    return errors


def _check_safety_warnings() -> list[str]:
    errors: list[str] = []
    feedback_template = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    if not feedback_template.exists():
        errors.append(" reviewer_feedback.yml not found; cannot check safety warnings")
        return errors

    text = feedback_template.read_text(encoding="utf-8").lower()
    for warning in REQUIRED_SAFETY_WARNINGS:
        if len(warning) == 1:
            if warning[0] not in text:
                errors.append(f" reviewer_feedback.yml missing safety warning: '{warning[0]}'")
        else:
            part_a, part_b = warning
            if part_a not in text or part_b not in text:
                errors.append(f" reviewer_feedback.yml missing safety warning: '{part_a} + {part_b}'")
    return errors


def _check_unsafe_phrases() -> list[str]:
    errors: list[str] = []
    targets = [
        REPO_ROOT / "docs" / "feedback-intake-process.md",
        REPO_ROOT / "docs" / "public-feedback-checklist.md",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml",
    ]
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in UNSAFE_PHRASES:
            for m in re.finditer(re.escape(phrase), text):
                # Allow if clearly negated in surrounding context
                start = max(0, m.start() - 80)
                end = min(len(text), m.end() + 80)
                context = text[start:end]
                negations = ("not ", "do not", "never", "no ", "forbidden", "reject", "out of scope", "do not accept")
                if not any(n in context for n in negations):
                    rel = path.relative_to(REPO_ROOT)
                    errors.append(f"[{rel}] Unsafe phrase '{phrase}' found without clear negation")
    return errors


def _check_credential_fragments() -> list[str]:
    errors: list[str] = []
    targets = [
        REPO_ROOT / "docs" / "feedback-intake-process.md",
        REPO_ROOT / "docs" / "public-feedback-checklist.md",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml",
    ]
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for pattern in CREDENTIAL_PATTERNS:
            for m in pattern.finditer(text):
                errors.append(f"[{rel}] Credential-like fragment: {m.group(0)[:40]}")
        for pattern in ABSOLUTE_PATH_PATTERNS:
            for m in pattern.finditer(text):
                errors.append(f"[{rel}] Absolute path fragment: {m.group(0)[:60]}")
    return errors


def _gather() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_templates_exist())
    all_errors.extend(_check_docs_exist())
    all_errors.extend(_check_safety_warnings())
    all_errors.extend(_check_unsafe_phrases())
    all_errors.extend(_check_credential_fragments())

    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "templates_checked": len(REQUIRED_TEMPLATES),
        "docs_checked": len(REQUIRED_DOCS),
        "safety_warnings_checked": len(REQUIRED_SAFETY_WARNINGS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify public feedback intake templates and safety warnings"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("Feedback intake check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"Feedback intake check PASSED: "
                f"templates={result['templates_checked']} "
                f"docs={result['docs_checked']} "
                f"warnings={result['safety_warnings_checked']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
