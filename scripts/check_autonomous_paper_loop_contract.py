#!/usr/bin/env python3
"""Static check for the autonomous paper decision loop contract (CAND-001).

Deterministic, local-only, read-only. Does not:
- call the network
- call brokers or providers
- require credentials
- execute live trading
- mutate files

Exit codes:
  0 = pass
  1 = blocking findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

DOC = REPO_ROOT / "docs" / "autonomous-paper-loop.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
SHADOW_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"

REQUIRED_FILES = [
    DOC,
    SHADOW_DOC,
]

REQUIRED_DOC_PHRASES = [
    "paper-only",
    "local-first",
    "no live trading",
    "no broker order submission",
    "RiskManager",
    "deterministic",
    "not financial advice",
    "does **not** claim autonomous live trading readiness",
    "atlas agent autonomous-paper",
]

FORBIDDEN_DOC_PHRASES = [
    "autonomous live trading ready",
    "safe live trading",
    "production-ready",
    "guaranteed profit",
    "risk-free",
    "unattended live trading",
]

NEGATIVE_CONTEXT_INDICATORS = (
    "not ",
    "does not",
    "never",
    "no ",
    "avoid",
    "disclaimer",
    "prohibited",
    "forbidden",
    "must not",
    "cannot",
    "do not",
    "is not",
    "are not",
    "without",
    "fail closed",
    "not yet",
    "not implemented",
    "not enabled",
    "not authorized",
    "not a ",
    "not ready",
    "remains disabled",
    "remains locked",
    "remains blocked",
    "out of scope",
    "does **not**",
)


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sentence_around(text: str, start: int, end: int) -> str:
    boundary_chars = {".", "!", "?", "\n"}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_required_files() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"Required file missing: {rel}")
    return errors


def _check_required_doc_phrases() -> list[str]:
    errors: list[str] = []
    if not DOC.exists():
        return errors

    text = _read(DOC)
    rel = DOC.relative_to(REPO_ROOT)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase.lower() not in text.lower():
            errors.append(f"[{rel}] Missing required phrase: {phrase}")
    return errors


def _check_forbidden_doc_claims() -> list[str]:
    errors: list[str] = []
    if not DOC.exists():
        return errors

    text = _read(DOC).lower()
    rel = DOC.relative_to(REPO_ROOT)
    for phrase in FORBIDDEN_DOC_PHRASES:
        start = text.find(phrase)
        while start != -1:
            end = start + len(phrase)
            sentence = _sentence_around(text, start, end).lower()
            if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                errors.append(
                    f"[{rel}] Forbidden phrase '{phrase}' outside negative context"
                )
            start = text.find(phrase, end)
    return errors


def _check_cross_references() -> list[str]:
    errors: list[str] = []
    if not DOC.exists():
        return errors

    text = _read(DOC)
    rel = DOC.relative_to(REPO_ROOT)
    for link in [
        "bounded-live-autonomy-governance.md",
        "shadow-live-readiness-contract.md",
    ]:
        if link not in text:
            errors.append(f"[{rel}] Missing link to {link}")
    return errors


def check_all() -> dict:
    """Run all contract checks and return a structured result."""
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_cross_references())

    return {
        "passed": len(errors) == 0,
        "errors": errors,
    }


def _redact(text: str) -> str:
    home = str(Path.home())
    repo = str(REPO_ROOT)
    replacements = [
        (home, "~"),
        (repo, "<repo>"),
        ("/Users/", "<home>/"),
        ("/private/var/", "<temp>/"),
        ("/var/folders/", "<temp>/"),
        ("/tmp/", "<temp>/"),
        ("/var/tmp/", "<temp>/"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous paper decision loop contract check."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    args = parser.parse_args()

    try:
        result = check_all()
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "passed": False}))
        else:
            print(f"Operational error: {exc}")
        return 2

    if args.json:
        output = {
            "passed": result["passed"],
            "errors": [_redact(e) for e in result["errors"]],
        }
        print(json.dumps(output, indent=2))
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Autonomous paper decision loop contract check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 1

    print("Autonomous paper decision loop contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
