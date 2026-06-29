#!/usr/bin/env python3
"""Static check for the runtime readiness envelope contract (CAND-007).

Deterministic, local-only, read-only. Does not:
- call the network
- call brokers or providers
- require credentials
- execute live trading
- mutate files

Exit codes:
  0 = pass
  2 = findings or operational error
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# User-facing design doc is checked because docs/runtime-readiness-envelope.md
# is created in a later documentation task.
DOC = REPO_ROOT / "docs" / "runtime-readiness-envelope-design.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
ENGINE_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "runtime_readiness_envelope.py"
)
CLI_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "runtime_readiness_envelope_cli.py"
)
BOOTSTRAP_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli_bootstrap.py"
LEGACY_CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_runtime_readiness_envelope.py"
CLI_TEST_MODULE = REPO_ROOT / "tests" / "test_runtime_readiness_envelope_cli.py"
IMPORT_TRACE_TEST_MODULE = (
    REPO_ROOT / "tests" / "test_runtime_readiness_envelope_import_trace.py"
)
AGENT_INIT_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "__init__.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REQUIRED_FILES = [
    DOC,
    ENGINE_MODULE,
    CLI_MODULE,
    BOOTSTRAP_MODULE,
    LEGACY_CLI_MODULE,
    TEST_MODULE,
    CLI_TEST_MODULE,
    IMPORT_TRACE_TEST_MODULE,
]

REQUIRED_STATUSES = (
    "not_evaluated",
    "blocked",
    "upstream_quality_blocked",
    "shadow_evidence_blocked",
    "submit_conformance_blocked",
    "runtime_envelope_blocked",
    "broker_capability_blocked",
    "operator_policy_blocked",
    "kill_switch_policy_blocked",
    "audit_policy_blocked",
    "envelope_synthesized",
    "readiness_envelope_recorded",
)

REQUIRED_GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_evidence_gate",
    "cand005_evidence_gate",
    "cand006_evidence_gate",
    "runtime_envelope_fixture_gate",
    "broker_capability_manifest_gate",
    "operator_policy_fixture_gate",
    "kill_switch_policy_fixture_gate",
    "audit_policy_fixture_gate",
    "envelope_synthesis_gate",
    "artifact_recording_gate",
)

REQUIRED_ARTIFACT_NAMES = (
    "runtime-readiness-envelope.json",
    "runtime-readiness-envelope-report.md",
)

REQUIRED_DOC_PHRASES = (
    "simulated-only",
    "evidence-only",
    "not live readiness",
    "permission to submit orders",
    "runtime-readiness-envelope.json",
    "runtime-readiness-envelope-report.md",
    "readiness_envelope_recorded is evidence-recording status only",
)

REQUIRED_SOURCE_PHRASES = (
    "does not submit orders",
    "does not call broker",
    "does not load credentials",
    "not live readiness",
    "simulated only",
)

REQUIRED_BOOTSTRAP_PHRASES = (
    "agent",
    "submit-conformance",
    "readiness-envelope",
    "runtime_readiness_envelope_cli",
)

REQUIRED_SAFETY_ASSERTIONS = (
    "live_submit_forbidden",
    "human_approval_required",
    "kill_switch_required",
    "risk_gate_required",
    "audit_recording_required",
    "broker_manifest_required",
    "operator_policy_fail_closed",
    "all_upstream_statuses_accepted",
    "no_credentials_in_fixtures",
    "no_endpoints_in_fixtures",
    "no_account_ids_in_fixtures",
    "cand006_transmission_blocked",
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
    "implying",
    "avoided",
)

FORBIDDEN_ATLAS_MODULE_IMPORTS = (
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

FORBIDDEN_NETWORK_MODULES = (
    "urllib",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "subprocess",
    "dotenv",
    "keyring",
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

# Stale claims that must not re-enter docs. These are exact substrings; safety
# disclaimers use different wording and are intentionally not matched.
STALE_CAND007_CLAIMS = (
    "CAND-007 remains future",
    "CAND-007 is not implemented",
    "CAND-007 remains planning-only",
    "readiness envelope is future work",
    "runtime readiness envelope is not implemented",
)

# If a matched line contains one of these safety-continuation markers, treat it
# as a disclaimer rather than a stale claim.
CAND007_SAFETY_CONTINUATIONS = (
    "live trading",
    "live readiness",
    "submit orders",
    "call broker",
    "load credentials",
    "mutate",
    "not a ",
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
    boundary_chars = {".", "!", "?"}
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


def _check_pyproject_entry_point() -> list[str]:
    errors: list[str] = []
    if not PYPROJECT.exists():
        errors.append(f"Required file missing: {_rel(PYPROJECT)}")
        return errors
    text = _read(PYPROJECT)
    if 'atlas = "atlas_agent.cli_bootstrap:main"' not in text:
        errors.append(
            f"[{_rel(PYPROJECT)}] Console script must point to atlas_agent.cli_bootstrap:main"
        )
    return errors


def _check_bootstrap_routing() -> list[str]:
    errors: list[str] = []
    if not BOOTSTRAP_MODULE.exists():
        return errors
    text = _read(BOOTSTRAP_MODULE)
    rel = _rel(BOOTSTRAP_MODULE)

    for phrase in REQUIRED_BOOTSTRAP_PHRASES:
        if phrase not in text:
            errors.append(f"[{rel}] Missing bootstrap routing phrase: {phrase}")

    if '"agent"' not in text and "'agent'" not in text:
        errors.append(f"[{rel}] Missing exact 'agent' route token")
    if 'args[1] == "submit-conformance"' not in text:
        errors.append(f"[{rel}] Missing exact submit-conformance route check")
    if 'args[1] == "readiness-envelope"' not in text:
        errors.append(f"[{rel}] Missing exact readiness-envelope route check")

    # Ensure atlas_agent.cli is not imported at module import time.
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        errors.append(f"[{rel}] Syntax error: {exc}")
        return errors

    top_level = getattr(tree, "body", [])
    for node in top_level:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "atlas_agent.cli":
                    errors.append(
                        f"[{rel}] Forbidden top-level import: atlas_agent.cli"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "atlas_agent.cli":
                errors.append(
                    f"[{rel}] Forbidden top-level import from: atlas_agent.cli"
                )

    return errors


def _check_legacy_cli_registration() -> list[str]:
    errors: list[str] = []
    if not LEGACY_CLI_MODULE.exists():
        return errors
    text = _read(LEGACY_CLI_MODULE)
    rel = _rel(LEGACY_CLI_MODULE)
    if '"readiness-envelope"' not in text:
        errors.append(f"[{rel}] Missing 'readiness-envelope' subparser registration")
    if 'args.agent_command == "readiness-envelope"' not in text:
        errors.append(f"[{rel}] Missing 'readiness-envelope' dispatch handler")
    return errors


def _stdlib_module_names() -> set[str]:
    try:
        return set(sys.stdlib_module_names)
    except AttributeError:  # pragma: no cover
        # Fallback for environments without sys.stdlib_module_names.
        return set()


def _check_core_cli_imports() -> list[str]:
    """Core engine and CAND-007 CLI modules must import only stdlib + the engine."""
    errors: list[str] = []
    stdlib = _stdlib_module_names() | {"__future__"}
    allowed_atlas = {"atlas_agent.agent.runtime_readiness_envelope"}

    for path in (ENGINE_MODULE, CLI_MODULE):
        if not path.exists():
            continue
        rel = _rel(path)
        text = _read(path)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            errors.append(f"[{rel}] Syntax error: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name not in stdlib:
                        errors.append(
                            f"[{rel}] Non-stdlib top-level import: {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in allowed_atlas:
                    continue
                root = module.split(".")[0]
                if root not in stdlib:
                    errors.append(
                        f"[{rel}] Non-stdlib top-level import from: {module}"
                    )
                # Also catch forbidden network/credential modules anywhere.
                if any(
                    module == forbidden or module.startswith(forbidden + ".")
                    for forbidden in FORBIDDEN_NETWORK_MODULES
                ):
                    errors.append(
                        f"[{rel}] Forbidden network/credential import: {module}"
                    )

    return errors


def _check_agent_init() -> list[str]:
    errors: list[str] = []
    if not AGENT_INIT_MODULE.exists():
        # An absent __init__ is effectively empty.
        return errors
    text = _read(AGENT_INIT_MODULE)
    rel = _rel(AGENT_INIT_MODULE)
    if "runtime_readiness_envelope" in text:
        errors.append(
            f"[{rel}] __init__ must not import CAND-007 modules as convenience exports"
        )
    return errors


def _check_forbidden_module_references() -> list[str]:
    """String-level guard against forbidden Atlas/network/submission patterns."""
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
            "FORBIDDEN_ATLAS_MODULE_IMPORTS",
            "FORBIDDEN_SUBMISSION_PATTERNS",
            "FORBIDDEN_NETWORK_MODULES",
            "FORBIDDEN_CREDENTIAL_PATTERNS",
            "_SECRET_KEYS",
            "_SECRET_VALUE_PATTERNS",
            "_ENDPOINT_KEYS",
            "_URL_PROTOCOL_PATTERNS",
            "_FORBIDDEN_FIXTURE_KEYS",
            "_UNSAFE_FLAGS",
        )
        line_skip_markers = (
            "does not load credentials",
            "load credentials",
            "does not call broker",
            "call broker",
            "for token in args",
            "token.split",
            "_reject_unsafe_flags",
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
        # Remove docstrings / multiline string literals before scanning for
        # forbidden submission or credential patterns.
        filtered_text = re.sub(
            r'("""|\'\'\').*?\1', "", filtered_text, flags=re.DOTALL
        )

        # Sanitized view has comments and all quoted literals removed so that
        # defensive scanner definitions and safety disclaimers are not false
        # positives. Atlas forbidden imports, submission patterns, credential
        # words, and network modules are all scanned against this view.
        sanitized = re.sub(r"#[^\n]*", "", filtered_text)
        sanitized = re.sub(r'(["\'])(?:\\\1|.)*?\1', "", sanitized)
        lower_sanitized = sanitized.lower()

        for forbidden in FORBIDDEN_ATLAS_MODULE_IMPORTS:
            if forbidden in sanitized:
                errors.append(f"[{rel}] Forbidden Atlas import/reference: {forbidden}")
        for pattern in FORBIDDEN_SUBMISSION_PATTERNS:
            if pattern in sanitized:
                errors.append(f"[{rel}] Forbidden submission pattern: {pattern}")
        for pattern in FORBIDDEN_CREDENTIAL_PATTERNS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", lower_sanitized):
                errors.append(f"[{rel}] Forbidden credential/secret pattern: {pattern}")
        for module in FORBIDDEN_NETWORK_MODULES:
            # Match import-like or attribute usage, but not when it is part of a
            # larger identifier that happens to contain the substring.
            if re.search(rf"\b{re.escape(module)}\b", lower_sanitized):
                errors.append(f"[{rel}] Forbidden network/credential reference: {module}")

    return errors


def _check_ordered_sequence(text: str, rel: str, sequence: tuple[str, ...], label: str) -> list[str]:
    errors: list[str] = []
    prev = -1
    for item in sequence:
        double = f'"{item}"'
        single = f"'{item}'"
        idx_double = text.find(double)
        idx_single = text.find(single)
        candidates = [i for i in (idx_double, idx_single) if i != -1]
        idx = min(candidates) if candidates else -1
        if idx == -1:
            errors.append(f"[{rel}] Missing {label}: {item}")
        elif idx <= prev:
            errors.append(f"[{rel}] {label} out of order: {item}")
        prev = max(prev, idx)
    return errors


def _check_required_statuses() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    return _check_ordered_sequence(
        _read(ENGINE_MODULE), _rel(ENGINE_MODULE), REQUIRED_STATUSES, "status"
    )


def _check_gate_sequence() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    return _check_ordered_sequence(
        _read(ENGINE_MODULE), _rel(ENGINE_MODULE), REQUIRED_GATE_SEQUENCE, "gate"
    )


def _check_required_artifact_names() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    for name in REQUIRED_ARTIFACT_NAMES:
        if name not in text:
            errors.append(f"[{rel}] Missing artifact name: {name}")
    return errors


def _check_universal_rejection_rules() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    required_markers = (
        "_SECRET_KEYS",
        "_SECRET_VALUE_PATTERNS",
        "_ENDPOINT_KEYS",
        "_URL_PROTOCOL_PATTERNS",
        "_universal_reject_scan",
    )
    for marker in required_markers:
        if marker not in text:
            errors.append(f"[{rel}] Missing universal rejection marker: {marker}")
    return errors


def _check_cand006_freshness() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    if "_cand006_age_hours" not in text:
        errors.append(f"[{rel}] Missing CAND-006 age helper")
    if "24 hours" not in text and "> 24.0" not in text:
        errors.append(f"[{rel}] Missing 24-hour freshness rule")
    return errors


def _check_broker_label_prefix() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    for prefix in ("local-", "simulated-", "fixture-", "redacted-"):
        if f'"{prefix}"' not in text:
            errors.append(f"[{rel}] Missing broker-label prefix: {prefix}")
    return errors


def _check_output_path_aliasing() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    for marker in ("_check_output_path_aliases", "_candidate_aliases_input"):
        if marker not in text:
            errors.append(f"[{rel}] Missing output-path aliasing guard: {marker}")
    return errors


def _check_disclaimers() -> list[str]:
    errors: list[str] = []
    if ENGINE_MODULE.exists():
        text = _read(ENGINE_MODULE)
        rel = _rel(ENGINE_MODULE)
        if "EVIDENCE_ONLY_DISCLAIMER" not in text:
            errors.append(f"[{rel}] Missing EVIDENCE_ONLY_DISCLAIMER constant")
        if '"disclaimer"' not in text:
            errors.append(f"[{rel}] JSON artifact must include disclaimer key")
        if "report.disclaimer" not in text:
            errors.append(f"[{rel}] Markdown artifact must include report.disclaimer")

    if DOC.exists():
        doc_text = _read(DOC).lower()
        rel = _rel(DOC)
        for phrase in REQUIRED_DOC_PHRASES:
            if phrase.lower() not in doc_text:
                errors.append(f"[{rel}] Missing required doc phrase: {phrase}")

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


def _check_stale_cand007_doc_claims() -> list[str]:
    """Fail if any doc regresses to stale CAND-007 claims."""
    errors: list[str] = []
    docs_to_check = [p for p in (DOC, GOVERNANCE_DOC) if p.exists()]
    for path in docs_to_check:
        if not path.exists():
            continue
        text = _read(path)
        lower_text = text.lower()
        for claim in STALE_CAND007_CLAIMS:
            claim_lower = claim.lower()
            start = 0
            while True:
                idx = lower_text.find(claim_lower, start)
                if idx == -1:
                    break
                line_start = lower_text.rfind("\n", 0, idx) + 1
                line_end = lower_text.find("\n", idx)
                if line_end == -1:
                    line_end = len(lower_text)
                context = lower_text[line_start:line_end]
                if not any(cont in context for cont in CAND007_SAFETY_CONTINUATIONS):
                    errors.append(f"[{_rel(path)}] Stale CAND-007 claim: {claim!r}")
                start = idx + len(claim_lower)
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


def check_all() -> dict[str, bool | list[str]]:
    """Run all contract checks and return a structured result."""
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_pyproject_entry_point())
    errors.extend(_check_bootstrap_routing())
    errors.extend(_check_legacy_cli_registration())
    errors.extend(_check_core_cli_imports())
    errors.extend(_check_agent_init())
    errors.extend(_check_forbidden_module_references())
    errors.extend(_check_required_statuses())
    errors.extend(_check_gate_sequence())
    errors.extend(_check_required_artifact_names())
    errors.extend(_check_universal_rejection_rules())
    errors.extend(_check_cand006_freshness())
    errors.extend(_check_broker_label_prefix())
    errors.extend(_check_output_path_aliasing())
    errors.extend(_check_disclaimers())
    errors.extend(_check_required_source_disclaimers())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_stale_cand007_doc_claims())
    errors.extend(_check_safety_assertions())

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
        description="Runtime readiness envelope contract check."
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
        return 0 if result["passed"] else 2

    if result["errors"]:
        print("Runtime readiness envelope contract check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Runtime readiness envelope contract check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
