#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_shadow_live_readonly_contract.py
# PURPOSE: Static check for the shadow-live read-only comparison contract
#         (CAND-005).
# DEPS:    argparse, json, re, sys, pathlib.
# ==============================================================================

"""Static check for the shadow-live read-only comparison contract (CAND-005).

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
import re
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC = REPO_ROOT / "docs" / "shadow-live-readonly-comparison.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
READINESS_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"
SHADOW_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_shadow_live.py"
)
CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_shadow_live_readonly.py"
CONTRACT_TEST_MODULE = REPO_ROOT / "tests" / "test_shadow_live_readonly_contract.py"

REQUIRED_FILES = [
    DOC,
    GOVERNANCE_DOC,
    READINESS_DOC,
    SHADOW_MODULE,
    CLI_MODULE,
    TEST_MODULE,
    CONTRACT_TEST_MODULE,
]

REQUIRED_STATUSES = (
    "matched",
    "minor_divergence",
    "major_divergence",
    "stale_snapshot",
    "incomplete_snapshot",
    "blocked",
    "not_evaluated",
)

REQUIRED_ARTIFACT_NAMES = (
    "shadow-live-comparison.json",
    "shadow-live-report.md",
)

REQUIRED_DOC_PHRASES = (
    "read-only fixture comparison",
    "read-only fixture-first comparison",
    "does not indicate live readiness",
    "does not implement live trading or live readiness",
    "does not submit orders or call broker APIs",
    "does not load credentials",
    "eligible_for_shadow_live_quality_review",
    "shadow-live-comparison.json",
    "shadow-live-report.md",
)

REQUIRED_SOURCE_PHRASES = (
    "read-only fixture comparison",
    "read-only fixture-first comparison",
    "does not indicate live readiness",
    "does not implement live trading or live readiness",
    "does not submit orders or call broker APIs",
    "does not load credentials",
)

REQUIRED_CLI_OPTIONS = (
    "--quality-gate",
    "--broker-snapshot",
    "--output-dir",
    "--max-snapshot-age-seconds",
    "--state",
    "--metrics",
    "--decisions",
    "--fills",
    "--json",
)

REQUIRED_CLI_HELP_PHRASES = (
    "read-only fixture-first comparison",
    "does not submit orders or call broker APIs",
    "does not load credentials",
    "does not implement live trading or live readiness",
)

FORBIDDEN_DOC_PHRASES = (
    "live-ready",
    "live ready",
    "production-ready",
    "guaranteed profit",
    "risk-free",
    "autonomous live trading ready",
    "safe to trade real money",
)

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
    "planning-only",
)

FORBIDDEN_MODULE_IMPORTS = (
    "from atlas_agent.brokers",
    "import atlas_agent.brokers",
    "from atlas_agent.providers",
    "import atlas_agent.providers",
    "from atlas_agent.execution",
    "import atlas_agent.execution",
)

FORBIDDEN_SUBMISSION_PATTERNS = (
    "place_order(",
    ".cancel_order(",
    ".flatten_all(",
    "broker.submit",
    "OrderRouter(",
    ".route(",
    "can_submit",
    "live_trading_enabled=True",
    "paper_only=False",
)

FORBIDDEN_CREDENTIAL_PATTERNS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "private_key",
    "auth_header",
    "bearer ",
)


# ==============================================================================
# PATH HELPERS
# ==============================================================================

def _rel(path: Path) -> Path:
    """Return a safe diagnostic path for repository or temporary fixtures."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        # Tests inspect mutated copies outside the repository; diagnostics must
        # remain useful without exposing the host's absolute temporary path.
        return Path("<temp>") / path.name


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
            errors.append(f"Required file missing: {_rel(path)}")
    return errors


def _check_required_statuses() -> list[str]:
    errors: list[str] = []
    if not SHADOW_MODULE.exists():
        return errors
    text = _read(SHADOW_MODULE)
    for status in REQUIRED_STATUSES:
        if f'"{status}"' not in text:
            errors.append(
                f"[{_rel(SHADOW_MODULE)}] Missing status: {status}"
            )
    return errors


def _check_required_artifact_names() -> list[str]:
    errors: list[str] = []
    if not SHADOW_MODULE.exists():
        return errors
    text = _read(SHADOW_MODULE)
    for name in REQUIRED_ARTIFACT_NAMES:
        if name not in text:
            errors.append(
                f"[{_rel(SHADOW_MODULE)}] Missing artifact name: {name}"
            )
    return errors


def _check_required_doc_phrases() -> list[str]:
    errors: list[str] = []
    if not DOC.exists():
        return errors
    text = _read(DOC).lower()
    rel = _rel(DOC)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase.lower() not in text:
            errors.append(f"[{rel}] Missing required phrase: {phrase}")
    return errors


def _check_required_source_disclaimers() -> list[str]:
    """Check that required disclaimers appear in the source tree.

    The shadow-live source module contains the core disclaimer text, while the
    CLI wiring contains the explicit "does not submit orders or call broker
    APIs" and "does not load credentials" language. We therefore search both
    files.
    """
    errors: list[str] = []
    texts: list[str] = []
    for path in (SHADOW_MODULE, CLI_MODULE):
        if path.exists():
            texts.append(_read(path))
    if not texts:
        return errors
    combined = re.sub(r"\s+", " ", "\n".join(texts).replace('"', "")).lower()
    for phrase in REQUIRED_SOURCE_PHRASES:
        if phrase.lower() not in combined:
            errors.append(
                f"[source] Missing required shadow-live disclaimer: {phrase}"
            )
    return errors


def _check_forbidden_doc_claims() -> list[str]:
    errors: list[str] = []
    docs_to_check = [p for p in (DOC, GOVERNANCE_DOC, READINESS_DOC) if p.exists()]
    for path in docs_to_check:
        text = _read(path).lower()
        rel = _rel(path)
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
    rel = _rel(DOC)
    for link in (
        "bounded-live-autonomy-governance.md",
        "shadow-live-readiness-contract.md",
    ):
        if link not in text:
            errors.append(f"[{rel}] Missing link to {link}")
    return errors


def _check_cli_wiring() -> list[str]:
    errors: list[str] = []
    if not CLI_MODULE.exists():
        return errors
    text = _read(CLI_MODULE)
    try:
        rel = _rel(CLI_MODULE)
    except ValueError:
        rel = str(CLI_MODULE)
    if '"shadow-live"' not in text:
        errors.append(f"[{rel}] Missing 'shadow-live' subparser registration")
    if not re.search(r"agent_sub\.add_parser\([\s\S]*?\"shadow-live\"", text):
        errors.append(f"[{rel}] 'shadow-live' not wired under agent subparser")

    # Isolate the shadow-live parser block so options and disclaimers are
    # verified for this specific command rather than any other subcommand.
    match = re.search(
        r"agent_sub\.add_parser\(\s*\"shadow-live\".*?(?=^\s*agent_sub\.add_parser\()",
        text,
        re.DOTALL | re.MULTILINE,
    )
    region = match.group(0) if match else text

    for option in REQUIRED_CLI_OPTIONS:
        if option not in region:
            errors.append(f"[{rel}] shadow-live missing required CLI option: {option}")

    normalized = re.sub(r"\s+", " ", region.replace('"', "")).lower()
    for phrase in REQUIRED_CLI_HELP_PHRASES:
        if phrase.lower() not in normalized:
            errors.append(
                f"[{rel}] shadow-live help/description missing required phrase: {phrase}"
            )

    return errors


def _check_module_safety() -> list[str]:
    errors: list[str] = []
    if not SHADOW_MODULE.exists():
        return errors
    text = _read(SHADOW_MODULE)
    rel = _rel(SHADOW_MODULE)

    # Strip out the pattern tuple definitions in this checker if they were ever
    # copied into the module (defensive: they are not, but the scan should not
    # flag its own definitions).
    lines = text.splitlines()
    filtered_lines: list[str] = []
    skip = False
    for line in lines:
        if any(marker in line for marker in ("FORBIDDEN_MODULE_IMPORTS", "FORBIDDEN_SUBMISSION_PATTERNS", "FORBIDDEN_CREDENTIAL_PATTERNS")):
            skip = True
        if skip:
            if line.rstrip().endswith(")"):
                skip = False
            continue
        filtered_lines.append(line)
    filtered_text = "\n".join(filtered_lines)

    for forbidden in FORBIDDEN_MODULE_IMPORTS:
        if forbidden in filtered_text:
            errors.append(f"[{rel}] Forbidden import/reference: {forbidden}")
    for pattern in FORBIDDEN_SUBMISSION_PATTERNS:
        if pattern in filtered_text:
            errors.append(f"[{rel}] Forbidden submission pattern: {pattern}")

    lower_text = filtered_text.lower()
    for pattern in FORBIDDEN_CREDENTIAL_PATTERNS:
        if pattern in lower_text:
            errors.append(f"[{rel}] Forbidden credential/secret pattern: {pattern}")

    return errors


def check_all() -> dict:
    """Run all contract checks and return a structured result."""
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_required_statuses())
    errors.extend(_check_required_artifact_names())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_required_source_disclaimers())
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
        description="Shadow-live read-only comparison contract check."
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
        print("Shadow-live read-only contract check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 1

    print("Shadow-live read-only contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
