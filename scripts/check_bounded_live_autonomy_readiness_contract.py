#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_bounded_live_autonomy_readiness_contract.py
# PURPOSE: Static contract checker for CAND-015 bounded live autonomy readiness
#         gate.
# DEPS:    argparse, ast, json, re, sys, pathlib, additional local modules.
# ==============================================================================

"""Static contract checker for CAND-015 bounded live autonomy readiness gate.

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

# --- IMPORTS ---

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import cast


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-readiness.md"
DESIGN_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-readiness-design.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
ENGINE_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "bounded_live_autonomy_readiness.py"
CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "bounded_live_autonomy_readiness_cli.py"
BOOTSTRAP_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli_bootstrap.py"
LEGACY_CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_bounded_live_autonomy_readiness.py"
CLI_TEST_MODULE = REPO_ROOT / "tests" / "test_bounded_live_autonomy_readiness_cli.py"
CONTRACT_TEST_MODULE = REPO_ROOT / "tests" / "test_bounded_live_autonomy_readiness_contract.py"
IMPORT_TRACE_TEST_MODULE = REPO_ROOT / "tests" / "test_bounded_live_autonomy_readiness_import_trace.py"
AGENT_INIT_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "__init__.py"

REQUIRED_FILES = [
    DESIGN_DOC,
    DOC,
    ENGINE_MODULE,
    CLI_MODULE,
    BOOTSTRAP_MODULE,
    LEGACY_CLI_MODULE,
    TEST_MODULE,
    CLI_TEST_MODULE,
    CONTRACT_TEST_MODULE,
    IMPORT_TRACE_TEST_MODULE,
]

REQUIRED_STATUSES = (
    "not_evaluated",
    "blocked",
    "upstream_evidence_blocked",
    "operator_policy_blocked",
    "autonomy_policy_blocked",
    "risk_limit_blocked",
    "symbol_policy_blocked",
    "heartbeat_deadman_blocked",
    "audit_redaction_blocked",
    "l2_l3_boundary_blocked",
    "readiness_synthesized",
    "bounded_live_readiness_recorded",
)

REQUIRED_GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_projection_gate",
    "cand005_projection_gate",
    "cand006_projection_gate",
    "cand007_projection_gate",
    "cand008_projection_gate",
    "cross_artifact_correlation_gate",
    "bounded_autonomy_policy_gate",
    "risk_limit_gate",
    "symbol_allowlist_gate",
    "heartbeat_deadman_gate",
    "audit_redaction_gate",
    "l2_l3_boundary_gate",
    "readiness_synthesis_gate",
    "artifact_recording_gate",
)

REQUIRED_ARTIFACT_NAMES = (
    "bounded-live-readiness.json",
    "bounded-live-readiness-report.md",
)

REQUIRED_DOC_PHRASES = (
    "evidence-only",
    "simulated-only",
    "not live readiness",
    "permission to submit orders",
    "bounded-live-readiness.json",
    "bounded-live-readiness-report.md",
    "bounded_live_readiness_recorded is evidence-recording status only",
)

REQUIRED_SOURCE_PHRASES = (
    "does not submit orders",
    "does not call broker",
    "does not load credentials",
    "not live readiness",
    "simulated-only",
)

REQUIRED_BOOTSTRAP_PHRASES = (
    "agent",
    "submit-conformance",
    "readiness-envelope",
    "operator-approval-gate",
    "bounded-live-readiness",
    "bounded_live_autonomy_readiness_cli",
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

REQUIRED_APPROVAL_GATE_ASSERTIONS = (
    "cand007_status_accepted",
    "cand007_mode_simulated_only",
    "cand007_blockers_empty",
    "cand007_safety_assertions_accepted",
    "operator_identity_valid",
    "approval_policy_fail_closed",
    "kill_switch_observed_blocked",
    "operator_acknowledgments_all_true",
    "audit_policy_fail_closed",
    "no_credentials_in_fixtures",
    "no_endpoints_in_fixtures",
    "no_account_ids_in_fixtures",
    "no_raw_upstream_leakage",
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
    "implying",
    "avoided",
)

FORBIDDEN_STATUSES = (
    "approved_for_live",
    "live_ready",
    "safe_to_trade",
    "ready_to_submit",
    "operator_approved_trade",
    "approved_to_trade",
    "ready_for_live",
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

UNSAFE_FLAGS = (
    "--live",
    "--submit",
    "--broker",
    "--provider",
    "--api-key",
    "--credentials",
    "--endpoint",
    "--account",
    "--account-id",
    "--client-order-id",
    "--place-order",
    "--order-router",
    "--risk-manager",
    "--mode",
    "--kill-switch-override",
    "--approve-live",
    "--approve-submit",
    "--trade",
    "--execute",
    "--enable-l3",
    "--l3-autonomy",
)

STALE_CAND015_CLAIMS = (
    "CAND-015 remains future",
    "CAND-015 is not implemented",
    "CAND-015 remains planning-only",
    "bounded live autonomy readiness is future work",
    "bounded live autonomy readiness is not implemented",
)

CAND015_SAFETY_CONTINUATIONS = (
    "live trading",
    "live readiness",
    "submit orders",
    "call broker",
    "load credentials",
    "mutate",
    "not a ",
)


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

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
    errors.extend(
        _check_ordered_sequence(
            _read(ENGINE_MODULE), _rel(ENGINE_MODULE), REQUIRED_STATUSES, "status"
        )
    )
    text = _read(ENGINE_MODULE)
    for status in FORBIDDEN_STATUSES:
        if f'"{status}"' in text:
            errors.append(
                f"[{_rel(ENGINE_MODULE)}] Forbidden status present: {status}"
            )
    return errors


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


def _check_required_doc_phrases() -> list[str]:
    errors: list[str] = []
    for path in (DOC, DESIGN_DOC):
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = _rel(path)
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
    docs_to_check = [p for p in (DOC, DESIGN_DOC, GOVERNANCE_DOC) if p.exists()]
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
    if 'args[1] == "operator-approval-gate"' not in text:
        errors.append(f"[{rel}] Missing exact operator-approval-gate route check")
    if 'args[1] == "bounded-live-readiness"' not in text:
        errors.append(f"[{rel}] Missing exact bounded-live-readiness route check")

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
                    errors.append(f"[{rel}] Forbidden top-level import: atlas_agent.cli")
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
    if '"bounded-live-readiness"' not in text:
        errors.append(f"[{rel}] Missing 'bounded-live-readiness' subparser registration")
    if 'args.agent_command == "bounded-live-readiness"' not in text:
        errors.append(f"[{rel}] Missing 'bounded-live-readiness' dispatch handler")
    return errors


def _stdlib_module_names() -> set[str]:
    try:
        return set(sys.stdlib_module_names)
    except AttributeError:  # pragma: no cover
        return set()


def _check_core_cli_imports() -> list[str]:
    """Core engine and CAND-015 CLI modules must import only stdlib + the engine."""
    errors: list[str] = []
    stdlib = _stdlib_module_names() | {"__future__"}
    allowed_atlas = {"atlas_agent.agent.bounded_live_autonomy_readiness"}

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
        return errors
    text = _read(AGENT_INIT_MODULE)
    rel = _rel(AGENT_INIT_MODULE)
    if "bounded_live_autonomy_readiness" in text:
        errors.append(
            f"[{rel}] __init__ must not import CAND-015 modules as convenience exports"
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

        lines = text.splitlines()
        filtered_lines: list[str] = []
        skip_to_close = False
        tuple_markers = (
            "FORBIDDEN_ATLAS_MODULE_IMPORTS",
            "FORBIDDEN_SUBMISSION_PATTERNS",
            "FORBIDDEN_NETWORK_MODULES",
            "FORBIDDEN_CREDENTIAL_PATTERNS",
            "FORBIDDEN_STATUSES",
            "UNSAFE_FLAGS",
            "_SECRET_KEYS",
            "_SECRET_VALUE_PATTERNS",
            "_ENDPOINT_KEYS",
            "_URL_PROTOCOL_PATTERNS",
            "_FORBIDDEN_FIXTURE_KEYS",
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
        filtered_text = re.sub(r'("""|\'\'\').*?\1', "", filtered_text, flags=re.DOTALL)

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
            if re.search(rf"\b{re.escape(module)}\b", lower_sanitized):
                errors.append(f"[{rel}] Forbidden network/credential reference: {module}")

    return errors


def _check_unsafe_flag_deny_list() -> list[str]:
    errors: list[str] = []
    if not CLI_MODULE.exists():
        return errors
    text = _read(CLI_MODULE)
    rel = _rel(CLI_MODULE)
    for flag in UNSAFE_FLAGS:
        if flag not in text:
            errors.append(f"[{rel}] Missing unsafe flag in deny list: {flag}")
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


def _check_cand007_projection() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    for marker in (
        'readiness_envelope_recorded',
        '"simulated_only"',
        '"CAND-007"',
    ):
        if marker not in text:
            errors.append(f"[{rel}] Missing CAND-007 projection marker: {marker}")

    if "_CAND007_REQUIRED_ASSERTIONS" not in text:
        errors.append(f"[{rel}] Missing CAND-007 required assertions constant")
    else:
        for assertion in REQUIRED_SAFETY_ASSERTIONS:
            if f'"{assertion}"' not in text:
                errors.append(
                    f"[{rel}] Missing CAND-007 required assertion in set: {assertion}"
                )

    return errors


def _check_cand008_projection() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    for marker in (
        'operator_gate_recorded',
        '"evidence_only"',
        '"CAND-008"',
    ):
        if marker not in text:
            errors.append(f"[{rel}] Missing CAND-008 projection marker: {marker}")

    if "_CAND008_REQUIRED_ASSERTIONS" not in text:
        errors.append(f"[{rel}] Missing CAND-008 required assertions constant")
    else:
        for assertion in REQUIRED_APPROVAL_GATE_ASSERTIONS:
            if f'"{assertion}"' not in text:
                errors.append(
                    f"[{rel}] Missing CAND-008 required assertion in set: {assertion}"
                )

    return errors


def _check_bounded_autonomy_policy_gate() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    required_fields = (
        "l3_autonomy_enabled",
        "live_submit_enabled_by_default",
        "provider_output_authoritative",
        "manual_approval_required",
        "unattended_operation_allowed",
        "auto_approval_allowed",
        "requires_explicit_opt_in",
        "requires_active_operator_oversight",
        "requires_paper_validation",
    )
    for field in required_fields:
        if field not in text:
            errors.append(f"[{rel}] Missing bounded autonomy policy field check: {field}")
    return errors


def _check_heartbeat_deadman_gate() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    required_fields = (
        "heartbeat_required",
        "deadman_required",
        "missing_heartbeat_fails_closed",
        "stale_heartbeat_fails_closed",
    )
    for field in required_fields:
        if field not in text:
            errors.append(f"[{rel}] Missing heartbeat/deadman field check: {field}")
    return errors


def _check_audit_redaction_gate() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    required_fields = (
        "redacts_secrets",
        "redacts_api_keys",
        "redacts_account_ids",
        "redacts_raw_broker_payloads",
        "redacts_raw_provider_output",
        "audit_hash_chain_required",
        "manifest_required",
    )
    for field in required_fields:
        if field not in text:
            errors.append(f"[{rel}] Missing audit redaction field check: {field}")
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


def _check_stale_cand015_doc_claims() -> list[str]:
    """Fail if any doc regresses to stale CAND-015 claims."""
    errors: list[str] = []
    docs_to_check = [p for p in (DOC, DESIGN_DOC, GOVERNANCE_DOC) if p.exists()]
    for path in docs_to_check:
        if not path.exists():
            continue
        text = _read(path)
        lower_text = text.lower()
        for claim in STALE_CAND015_CLAIMS:
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
                if not any(cont in context for cont in CAND015_SAFETY_CONTINUATIONS):
                    errors.append(f"[{_rel(path)}] Stale CAND-015 claim: {claim!r}")
                start = idx + len(claim_lower)
    return errors


def _check_canonical_blockers_field() -> list[str]:
    """Assert the canonical output field is ``blockers``."""
    errors: list[str] = []

    if ENGINE_MODULE.exists():
        text = _read(ENGINE_MODULE)
        rel = _rel(ENGINE_MODULE)
        if "blockers: list[str]" not in text:
            errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport missing blockers field")
        if '"blockers": self.blockers' not in text:
            errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport.to_dict missing blockers key")
        if "## Blockers" not in text:
            errors.append(f"[{rel}] Markdown renderer missing Blockers section")

    if CLI_MODULE.exists():
        text = _read(CLI_MODULE)
        rel = _rel(CLI_MODULE)
        if "if report.blockers:" not in text:
            errors.append(f"[{rel}] CLI text output missing blockers list guard")
        if "report.to_dict()" not in text:
            errors.append(f"[{rel}] CLI JSON output must serialize report.to_dict()")

    return errors


def _check_no_raw_upstream_leakage() -> list[str]:
    """Engine must build summaries, not copy raw upstream artifacts."""
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    if "_build_upstream_summaries" not in text:
        errors.append(f"[{rel}] Missing upstream summary builder")
    if "_build_fixture_summaries" not in text:
        errors.append(f"[{rel}] Missing fixture summary builder")
    return errors


def _get_class_method_source(text: str, class_name: str, method_name: str) -> str | None:
    """Return the source text of a method inside a class, or None."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(text, item) or ""
    return None


def _check_no_input_paths_in_serialization() -> list[str]:
    """BoundedLiveAutonomyReadinessReport.to_dict() must not serialize input_paths."""
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    method_source = _get_class_method_source(text, "BoundedLiveAutonomyReadinessReport", "to_dict")
    if method_source is None:
        errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport.to_dict() not found")
        return errors

    if '"input_paths"' in method_source or "'input_paths'" in method_source:
        errors.append(f"[{rel}] to_dict() serializes forbidden 'input_paths' key")

    class_source = ""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        errors.append(f"[{rel}] Syntax error: {exc}")
        return errors
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BoundedLiveAutonomyReadinessReport":
            class_source = ast.get_source_segment(text, node) or ""
            break
    if "input_paths:" not in class_source:
        errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport missing internal input_paths field")

    return errors


def _check_output_uses_safe_identifiers() -> list[str]:
    """Output serialization must use basename-only input_artifacts and fingerprints."""
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    method_source = _get_class_method_source(text, "BoundedLiveAutonomyReadinessReport", "to_dict")
    if method_source is None:
        errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport.to_dict() not found")
        return errors

    if '"input_artifacts": self.input_artifacts' not in method_source:
        errors.append(f"[{rel}] to_dict() must serialize input_artifacts")
    if '"input_fingerprints": self.input_fingerprints' not in method_source:
        errors.append(f"[{rel}] to_dict() must serialize input_fingerprints")

    if "_redact_path" not in text:
        errors.append(f"[{rel}] Missing _redact_path basename helper")
    if "path.name" not in text:
        errors.append(f"[{rel}] input_artifacts must derive identifiers from path.name")

    return errors


def _check_no_path_string_serialization() -> list[str]:
    """Guard against absolute/relative path serialization in output artifacts."""
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)

    method_source = _get_class_method_source(text, "BoundedLiveAutonomyReadinessReport", "to_dict")
    if method_source is None:
        errors.append(f"[{rel}] BoundedLiveAutonomyReadinessReport.to_dict() not found")
        return errors

    forbidden_patterns = (
        "str(path)",
        "str(self.input_paths",
        "Path(",
    )
    for pattern in forbidden_patterns:
        if pattern in method_source:
            errors.append(
                f"[{rel}] to_dict() contains possible path serialization: {pattern!r}"
            )

    return errors


def _check_output_path_aliasing() -> list[str]:
    errors: list[str] = []
    if not ENGINE_MODULE.exists():
        return errors
    text = _read(ENGINE_MODULE)
    rel = _rel(ENGINE_MODULE)
    for marker in ("_check_path_aliasing", "_resolve_unique_id"):
        if marker not in text:
            errors.append(f"[{rel}] Missing output-path aliasing guard: {marker}")
    return errors


def check_all() -> dict[str, bool | list[str]]:
    """Run all contract checks and return a structured result."""
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_required_statuses())
    errors.extend(_check_gate_sequence())
    errors.extend(_check_required_artifact_names())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_required_source_disclaimers())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_bootstrap_routing())
    errors.extend(_check_legacy_cli_registration())
    errors.extend(_check_core_cli_imports())
    errors.extend(_check_agent_init())
    errors.extend(_check_forbidden_module_references())
    errors.extend(_check_unsafe_flag_deny_list())
    errors.extend(_check_universal_rejection_rules())
    errors.extend(_check_cand007_projection())
    errors.extend(_check_cand008_projection())
    errors.extend(_check_bounded_autonomy_policy_gate())
    errors.extend(_check_heartbeat_deadman_gate())
    errors.extend(_check_audit_redaction_gate())
    errors.extend(_check_disclaimers())
    errors.extend(_check_stale_cand015_doc_claims())
    errors.extend(_check_canonical_blockers_field())
    errors.extend(_check_no_raw_upstream_leakage())
    errors.extend(_check_no_input_paths_in_serialization())
    errors.extend(_check_output_uses_safe_identifiers())
    errors.extend(_check_no_path_string_serialization())
    errors.extend(_check_output_path_aliasing())

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
        description="Bounded live autonomy readiness contract check (CAND-015)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    args = parser.parse_args()

    try:
        result = check_all()
    except Exception:
        if args.json:
            print(json.dumps({"error": "operational error", "passed": False}))
        else:
            print("Operational error: contract check failed")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["passed"]:
            print("PASSED: CAND-015 contract checks passed.")
        else:
            print("FAILED: CAND-015 contract checks found issues:")
            for error in cast(list[str], result["errors"]):
                print(f"  - {_redact(error)}")

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
