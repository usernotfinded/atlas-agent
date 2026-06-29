#!/usr/bin/env python3
"""Static check for the gated submit conformance rehearsal contract (CAND-006).

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

DOC = REPO_ROOT / "docs" / "gated-submit-conformance.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
ENGINE_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "gated_submit_conformance.py"
)
CLI_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "gated_submit_conformance_cli.py"
)
BOOTSTRAP_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli_bootstrap.py"
LEGACY_CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_gated_submit_conformance.py"
CLI_TEST_MODULE = REPO_ROOT / "tests" / "test_gated_submit_conformance_cli.py"
IMPORT_TRACE_TEST_MODULE = (
    REPO_ROOT / "tests" / "test_gated_submit_conformance_import_trace.py"
)

REQUIRED_FILES = [
    DOC,
    ENGINE_MODULE,
    CLI_MODULE,
    BOOTSTRAP_MODULE,
    TEST_MODULE,
    CLI_TEST_MODULE,
    IMPORT_TRACE_TEST_MODULE,
]

REQUIRED_STATUSES = (
    "not_evaluated",
    "blocked",
    "approval_required",
    "risk_blocked",
    "kill_switch_blocked",
    "shadow_divergence_blocked",
    "dry_run_ready",
    "dry_run_recorded",
)

REQUIRED_ARTIFACT_NAMES = (
    "gated-submit-conformance.json",
    "gated-submit-conformance-report.md",
)

REQUIRED_DOC_PHRASES = (
    "simulated-only",
    "conformance rehearsal",
    "does not submit orders",
    "does not call broker",
    "does not load credentials",
    "not live readiness",
    "gated-submit-conformance.json",
    "gated-submit-conformance-report.md",
)

REQUIRED_SOURCE_PHRASES = (
    "does not submit orders",
    "does not call broker",
    "does not load credentials",
    "not live readiness",
    "simulated-only",
)

REQUIRED_CLI_OPTIONS = (
    "--quality-gate",
    "--shadow-comparison",
    "--order-intent",
    "--kill-switch",
    "--risk-envelope",
    "--approval",
    "--output-dir",
    "--as-of",
    "--json",
)

REQUIRED_BOOTSTRAP_PHRASES = (
    "agent",
    "submit-conformance",
    "gated_submit_conformance_cli",
)

REQUIRED_SAFETY_ASSERTIONS = (
    "simulated_only",
    "no_live_submit",
    "no_broker_called",
    "no_provider_called",
    "no_credentials_loaded",
    "no_runtime_state_mutation",
    "no_order_instantiated",
    "transmission_blocked",
    "json_authoritative",
)

FORBIDDEN_DOC_PHRASES = (
    "live-ready",
    "live ready",
    "production-ready",
    "guaranteed profit",
    "risk-free",
    "autonomous live trading ready",
    "safe to trade real money",
    "permission to submit orders",
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
    "from atlas_agent.risk",
    "import atlas_agent.risk",
    "from atlas_agent.safety",
    "import atlas_agent.safety",
    "from atlas_agent.config",
    "import atlas_agent.config",
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
    "Order(",
    "OrderResult",
)

FORBIDDEN_NETWORK_PATTERNS = (
    "urllib.request",
    "requests.get",
    "requests.post",
    "httpx.",
    "aiohttp.",
)

# Docs that must not regress to stale "CAND-006 is future/unimplemented" claims.
STALE_CAND006_DOC_PATHS = (
    REPO_ROOT / "docs" / "autonomy-roadmap.md",
    REPO_ROOT / "docs" / "shadow-live-readiness-contract.md",
    REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md",
    REPO_ROOT / "docs" / "releases" / "v0.6.16-plan.md",
    REPO_ROOT / "docs" / "releases" / "v0.6.16-candidates.md",
    REPO_ROOT / "docs" / "releases" / "v0.6.16-candidate-selection.md",
    REPO_ROOT / "docs" / "releases" / "v0.6.16-candidates.json",
)

# Stale claims that must not re-enter docs. These are exact substrings; safety
# disclaimers use different wording ("is not live trading", "does not submit
# orders", etc.) and are intentionally not matched.
STALE_CAND006_CLAIMS = (
    "CAND-006 remains future",
    "CAND-006 is not implemented",
    "CAND-006 remains planning-only",
    "submit-conformance is future work",
    "gated submit conformance is not implemented",
)

# If a matched line contains one of these safety-continuation markers, treat it
# as a disclaimer rather than a stale claim. This protects phrases like
# "CAND-006 is not implemented as a live trading feature" when they are used to
# reinforce the safety boundary.
CAND006_SAFETY_CONTINUATIONS = (
    "live trading",
    "live readiness",
    "submit orders",
    "call broker",
    "load credentials",
    "mutate",
    "not a ",
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


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    for status in REQUIRED_STATUSES:
        if f'"{status}"' not in text:
            errors.append(
                f"[{_rel(ENGINE_MODULE)}] Missing status: {status}"
            )
    return errors


def _check_required_artifact_names() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    for name in REQUIRED_ARTIFACT_NAMES:
        if name not in text:
            errors.append(
                f"[{_rel(ENGINE_MODULE)}] Missing artifact name: {name}"
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
    errors: list[str] = []
    texts: list[str] = []
    for path in (ENGINE_MODULE, CLI_MODULE, BOOTSTRAP_MODULE, LEGACY_CLI_MODULE):
        if path.exists():
            texts.append(_read(path))
    if not texts:
        return errors
    combined = re.sub(r"\s+", " ", "\n".join(texts).replace('"', "")).lower()
    for phrase in REQUIRED_SOURCE_PHRASES:
        if phrase.lower() not in combined:
            errors.append(f"[source] Missing required disclaimer: {phrase}")
    return errors


def _check_forbidden_doc_claims() -> list[str]:
    errors: list[str] = []
    docs_to_check = [p for p in (DOC, GOVERNANCE_DOC) if p.exists()]
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


def _check_cli_wiring() -> list[str]:
    errors: list[str] = []
    if not BOOTSTRAP_MODULE.exists():
        return errors
    text = _read(BOOTSTRAP_MODULE)
    rel = _rel(BOOTSTRAP_MODULE)
    for phrase in REQUIRED_BOOTSTRAP_PHRASES:
        if phrase not in text:
            errors.append(f"[{rel}] Missing bootstrap routing phrase: {phrase}")

    if LEGACY_CLI_MODULE.exists():
        legacy_text = _read(LEGACY_CLI_MODULE)
        if '"submit-conformance"' not in legacy_text:
            errors.append(
                f"[{_rel(LEGACY_CLI_MODULE)}] "
                "Missing 'submit-conformance' subparser registration"
            )
        if "args.agent_command == \"submit-conformance\"" not in legacy_text:
            errors.append(
                f"[{_rel(LEGACY_CLI_MODULE)}] "
                "Missing 'submit-conformance' dispatch handler"
            )

    if CLI_MODULE.exists():
        cli_text = _read(CLI_MODULE)
        for option in REQUIRED_CLI_OPTIONS:
            if option not in cli_text:
                errors.append(
                    f"[{_rel(CLI_MODULE)}] "
                    f"Missing required CLI option: {option}"
                )

    return errors


def _check_module_safety() -> list[str]:
    errors: list[str] = []
    for path in (ENGINE_MODULE, CLI_MODULE, BOOTSTRAP_MODULE):
        if not path.exists():
            continue
        text = _read(path)
        rel = _rel(path)

        # Strip out defensive scanner definitions and safety disclaimers that
        # legitimately mention the words they scan for.
        lines = text.splitlines()
        filtered_lines: list[str] = []
        skip_to_close = False
        tuple_markers = (
            "FORBIDDEN_MODULE_IMPORTS",
            "FORBIDDEN_SUBMISSION_PATTERNS",
            "FORBIDDEN_NETWORK_PATTERNS",
            "FORBIDDEN_CREDENTIAL_PATTERNS",
            "_SECRET_KEYS",
            "_SECRET_VALUE_PATTERNS",
            "_FORBIDDEN_FIXTURE_KEYS",
        )
        line_skip_markers = (
            "does not load credentials",
            "load credentials",
        )
        for line in lines:
            if any(marker in line for marker in tuple_markers):
                skip_to_close = True
            if skip_to_close:
                if line.rstrip().endswith((")", "}", "]")):
                    skip_to_close = False
                continue
            if any(marker in line for marker in line_skip_markers):
                continue
            filtered_lines.append(line)
        filtered_text = "\n".join(filtered_lines)

        for forbidden in FORBIDDEN_MODULE_IMPORTS:
            if forbidden in filtered_text:
                errors.append(f"[{rel}] Forbidden import/reference: {forbidden}")
        for pattern in FORBIDDEN_SUBMISSION_PATTERNS:
            if pattern in filtered_text:
                errors.append(f"[{rel}] Forbidden submission pattern: {pattern}")
        for pattern in FORBIDDEN_NETWORK_PATTERNS:
            if pattern in filtered_text:
                errors.append(f"[{rel}] Forbidden network pattern: {pattern}")

        # Scan credential words in a sanitized view with comments and quoted
        # literals removed, so defensive scanner definitions and disclaimers are
        # not false positives.
        sanitized = re.sub(r"#[^\n]*", "", filtered_text)
        sanitized = re.sub(r'(["\'])(?:\\\1|.)*?\1', "", sanitized)
        lower_sanitized = sanitized.lower()
        for pattern in FORBIDDEN_CREDENTIAL_PATTERNS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", lower_sanitized):
                errors.append(f"[{rel}] Forbidden credential/secret pattern: {pattern}")

    return errors


def _check_safety_assertions() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    for assertion in REQUIRED_SAFETY_ASSERTIONS:
        if f'"{assertion}":' not in text:
            errors.append(f"[{rel}] Missing safety assertion: {assertion}")
    return errors


def _check_stale_cand006_doc_claims() -> list[str]:
    """Fail if any governance/release doc regresses to stale CAND-006 claims."""
    errors: list[str] = []
    for path in STALE_CAND006_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path)
        lower_text = text.lower()
        for claim in STALE_CAND006_CLAIMS:
            claim_lower = claim.lower()
            start = 0
            while True:
                idx = lower_text.find(claim_lower, start)
                if idx == -1:
                    break
                # Extract the surrounding line/phrase for context.
                line_start = lower_text.rfind("\n", 0, idx) + 1
                line_end = lower_text.find("\n", idx)
                if line_end == -1:
                    line_end = len(lower_text)
                context = lower_text[line_start:line_end]
                # If the context continues into a safety disclaimer, skip it.
                if not any(cont in context for cont in CAND006_SAFETY_CONTINUATIONS):
                    errors.append(
                        f"[{_rel(path)}] Stale CAND-006 claim: {claim!r}"
                    )
                start = idx + len(claim_lower)
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
    errors.extend(_check_cli_wiring())
    errors.extend(_check_module_safety())
    errors.extend(_check_safety_assertions())
    errors.extend(_check_stale_cand006_doc_claims())

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
        description="Gated submit conformance rehearsal contract check."
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
        print("Gated submit conformance contract check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 1

    print("Gated submit conformance contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
