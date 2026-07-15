#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_shadow_live_contract.py
# PURPOSE: Static check for the shadow-live / read-only readiness contract
#         (CAND-001).
# DEPS:    argparse, json, sys, pathlib.
# ==============================================================================

"""Static check for the shadow-live / read-only readiness contract (CAND-001).

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

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

CONTRACT_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"

REQUIRED_FILES = [
    CONTRACT_DOC,
    GOVERNANCE_DOC,
]

REQUIRED_DOC_PHRASES = [
    "shadow live",
    "read-only",
    "must not submit orders",
    "must not mutate broker state",
    "planning-only",
    "not financial advice",
    "advisory only",
    "bounded-live-autonomy-governance.md",
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


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

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
    if not CONTRACT_DOC.exists():
        return errors

    text = _read(CONTRACT_DOC).lower()
    rel = CONTRACT_DOC.relative_to(REPO_ROOT)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase.lower() not in text:
            errors.append(f"[{rel}] Missing required phrase: {phrase}")
    return errors


def _check_forbidden_doc_claims() -> list[str]:
    errors: list[str] = []
    if not CONTRACT_DOC.exists():
        return errors

    text = _read(CONTRACT_DOC).lower()
    rel = CONTRACT_DOC.relative_to(REPO_ROOT)
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


def check_all() -> dict:
    """Run all static checks and return a result dict.

    Returns {"passed": bool, "errors": list[str]}.
    """
    errors: list[str] = []
    errors.extend(_check_required_files())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_doc_claims())
    return {"passed": len(errors) == 0, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shadow-live / read-only readiness contract check."
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
            "errors": result["errors"],
        }
        print(json.dumps(output, indent=2))
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Shadow-live readiness contract check FAILED")
        for e in result["errors"]:
            print(f"  - {e}")
        return 1

    print("Shadow-live readiness contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
