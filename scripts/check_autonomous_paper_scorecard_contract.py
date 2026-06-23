#!/usr/bin/env python3
"""Static check for the autonomous paper scorecard contract (CAND-002).

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

DOC = REPO_ROOT / "docs" / "autonomous-paper-scorecard.md"
PARENT_DOC = REPO_ROOT / "docs" / "autonomous-paper-loop.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
SHADOW_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"
SCORECARD_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_scorecard.py"
CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_autonomous_paper_scorecard.py"

REQUIRED_FILES = [
    DOC,
    PARENT_DOC,
    GOVERNANCE_DOC,
    SHADOW_DOC,
    SCORECARD_MODULE,
    CLI_MODULE,
    TEST_MODULE,
]

REQUIRED_DOC_PHRASES = [
    "paper-only",
    "offline",
    "no live trading",
    "no broker order submission",
    "RiskManager",
    "deterministic",
    "not financial advice",
    "does **not** claim autonomous live trading readiness",
    "atlas agent autonomous-scorecard",
    "eligible_for_shadow_live_review",
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

FORBIDDEN_MODULE_IMPORTS = (
    "atlas_agent.brokers",
    "atlas_agent.providers",
    "atlas_agent.execution.live",
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
        "autonomous-paper-loop.md",
        "bounded-live-autonomy-governance.md",
        "shadow-live-readiness-contract.md",
    ]:
        if link not in text:
            errors.append(f"[{rel}] Missing link to {link}")
    return errors


def _check_cli_wiring() -> list[str]:
    errors: list[str] = []
    if not CLI_MODULE.exists():
        return errors

    text = _read(CLI_MODULE)
    if '"autonomous-scorecard"' not in text:
        errors.append("[src/atlas_agent/cli.py] Missing 'autonomous-scorecard' subparser registration")
    return errors


def _check_module_safety() -> list[str]:
    errors: list[str] = []
    if not SCORECARD_MODULE.exists():
        return errors

    text = _read(SCORECARD_MODULE)
    for forbidden in FORBIDDEN_MODULE_IMPORTS:
        if forbidden in text:
            errors.append(
                f"[{SCORECARD_MODULE.relative_to(REPO_ROOT)}] Forbidden import/reference: {forbidden}"
            )
    return errors


def check_all() -> dict:
    """Run all contract checks and return a structured result."""
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_cross_references())
    errors.extend(_check_cli_wiring())
    errors.extend(_check_module_safety())

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
        description="Autonomous paper scorecard contract check."
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
        print("Autonomous paper scorecard contract check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 1

    print("Autonomous paper scorecard contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
