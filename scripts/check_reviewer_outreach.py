#!/usr/bin/env python3
"""Verify controlled reviewer outreach docs, checklists, and message drafts.

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

OUTREACH_DOC = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
CHECKLIST_DOC = REPO_ROOT / "docs" / "reviewer-outreach-checklist.md"
TARGETS_TEMPLATE = REPO_ROOT / "docs" / "reviewer-targets-template.md"

REQUIRED_DOCS = [
    OUTREACH_DOC,
    CHECKLIST_DOC,
    TARGETS_TEMPLATE,
]

REQUIRED_SAFETY_PHRASES: dict[Path, list] = {
    OUTREACH_DOC: [
        ("not financial advice",),
        ("live trading", "disabled by default"),
        ("provider execution", "locked"),
        ("broker execution", "blocked"),
        ("not", "production ready"),
        ("not", "profitability"),
        ("not", "live trading product"),
        ("out of scope",),
        ("do not", "credentials"),
        ("do not", "live trading"),
    ],
    CHECKLIST_DOC: [
        ("not financial advice",),
        ("live trading", "disabled by default"),
        ("provider execution", "locked"),
        ("broker execution", "blocked"),
        ("v0.5.7",),
        ("0.5.8rc5",),
    ],
    TARGETS_TEMPLATE: [
        ("not financial advice",),
        ("no real personal data",),
    ],
}

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "zero risk",
    "risk-free",
    "safe live trading",
    "unattended live trading",
    "can't lose",
    "production trading ready",
    "autonomous trading bot",
    "ai trading bot that makes money",
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


def _check_docs_exist() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.exists():
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path.name
            errors.append(f"Missing outreach doc: {rel}")
    return errors


def _check_safety_phrases() -> list[str]:
    errors: list[str] = []
    for path, phrases in REQUIRED_SAFETY_PHRASES.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase_tuple in phrases:
            if len(phrase_tuple) == 1:
                if phrase_tuple[0] not in text:
                    errors.append(
                        f"[{path.relative_to(REPO_ROOT)}] Missing safety phrase: '{phrase_tuple[0]}'"
                    )
            else:
                part_a, part_b = phrase_tuple
                if part_a not in text or part_b not in text:
                    errors.append(
                        f"[{path.relative_to(REPO_ROOT)}] Missing safety phrase: '{part_a} + {part_b}'"
                    )
    return errors


def _check_forbidden_claims() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_CLAIMS:
            for m in re.finditer(re.escape(phrase), text):
                start = max(0, m.start() - 80)
                end = min(len(text), m.end() + 80)
                context = text[start:end]
                negations = (
                    "not ", "do not", "never", "no ", "forbidden",
                    "reject", "out of scope", "do not accept", "avoid",
                )
                if not any(n in context for n in negations):
                    rel = path.relative_to(REPO_ROOT)
                    errors.append(
                        f"[{rel}] Forbidden claim '{phrase}' found without clear negation"
                    )
    return errors


def _check_credential_fragments() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for pattern in CREDENTIAL_PATTERNS:
            for m in pattern.finditer(text):
                errors.append(
                    f"[{rel}] Credential-like fragment: {m.group(0)[:40]}"
                )
        for pattern in ABSOLUTE_PATH_PATTERNS:
            for m in pattern.finditer(text):
                errors.append(
                    f"[{rel}] Absolute path fragment: {m.group(0)[:60]}"
                )
    return errors


def _check_message_drafts_safe() -> list[str]:
    errors: list[str] = []
    if not OUTREACH_DOC.exists():
        return errors

    text = OUTREACH_DOC.read_text(encoding="utf-8").lower()
    # Verify the doc contains message draft sections
    if "short direct message" not in text:
        errors.append("Outreach doc missing short direct message draft")
    if "longer technical review request" not in text:
        errors.append("Outreach doc missing longer technical review request draft")
    if "github/reddit-style post" not in text:
        errors.append("Outreach doc missing GitHub/Reddit-style post draft")
    if "follow-up message" not in text:
        errors.append("Outreach doc missing follow-up message draft")

    # Verify drafts explicitly discourage live trading, broker setup, profit eval
    required_draft_phrases = [
        ("live trading", "disabled"),
        ("not", "financial advice"),
        ("out of scope",),
        ("credentials",),
    ]
    for phrase_tuple in required_draft_phrases:
        if len(phrase_tuple) == 1:
            if phrase_tuple[0] not in text:
                errors.append(
                    f"Outreach drafts missing phrase: '{phrase_tuple[0]}'"
                )
        else:
            part_a, part_b = phrase_tuple
            if part_a not in text or part_b not in text:
                errors.append(
                    f"Outreach drafts missing phrase: '{part_a} + {part_b}'"
                )
    return errors


def _check_targets_template_safe() -> list[str]:
    errors: list[str] = []
    if not TARGETS_TEMPLATE.exists():
        return errors

    text = TARGETS_TEMPLATE.read_text(encoding="utf-8").lower()
    # Verify it contains the template fields
    required_fields = [
        "reviewer handle",
        "reason for asking",
        "expected expertise",
        "contact channel",
        "date contacted",
        "response status",
        "feedback issue link",
        "classification labels",
        "follow-up needed",
        "notes",
    ]
    for field in required_fields:
        if field not in text:
            errors.append(f"Targets template missing field: '{field}'")

    # Verify safety rules section exists
    if "safety rules for this template" not in text:
        errors.append("Targets template missing safety rules section")

    # Verify no real personal data disclaimer
    if "no real personal data" not in text:
        errors.append("Targets template missing 'no real personal data' disclaimer")

    return errors


def _gather() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_docs_exist())
    all_errors.extend(_check_safety_phrases())
    all_errors.extend(_check_forbidden_claims())
    all_errors.extend(_check_credential_fragments())
    all_errors.extend(_check_message_drafts_safe())
    all_errors.extend(_check_targets_template_safe())

    safety_count = sum(len(v) for v in REQUIRED_SAFETY_PHRASES.values())
    return {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "docs_checked": len(REQUIRED_DOCS),
        "safety_phrases_checked": safety_count,
        "forbidden_claims_checked": len(FORBIDDEN_CLAIMS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify controlled reviewer outreach docs and message drafts"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    args = parser.parse_args()

    result = _gather()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["errors"]:
            print("Reviewer outreach check FAILED")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print(
                f"Reviewer outreach check PASSED: "
                f"docs={result['docs_checked']} "
                f"safety_phrases={result['safety_phrases_checked']} "
                f"forbidden_claims={result['forbidden_claims_checked']}"
            )

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
