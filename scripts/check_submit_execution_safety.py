#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_submit_execution_safety.py
# PURPOSE: Static safety check for the live submit execution boundary.
# DEPS:    argparse, ast, json, sys, pathlib, typing.
# ==============================================================================

"""Static safety check for the live submit execution boundary.

This check is deterministic and local-only. It does not import Atlas runtime
modules, load credentials, contact brokers, or make network calls.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REQUIRED_DOC_GATE_IDS = [
    "explicit_live_submit_opt_in",
    "live_trading_enabled",
    "trading_mode_live",
    "real_broker_selected",
    "provider_execution_not_used",
    "pending_order_exists",
    "pending_order_id_path_safe",
    "order_hash_valid",
    "approval_hash_valid",
    "approval_not_expired",
    "approval_actor_valid",
    "approval_manager_integrity",
    "live_sync_available",
    "fresh_live_sync_valid",
    "quote_required_for_market",
    "quote_symbol_matches",
    "quote_bid_ask_positive_finite",
    "quote_not_crossed",
    "quote_not_stale",
    "conservative_price_by_side",
    "risk_revalidated_before_submit",
    "notional_position_loss_limits",
    "kill_switch_initial_normal",
    "can_submit_true",
    "submit_state_mutation_succeeds",
    "execution_broker_resolved",
    "execution_broker_place_order_callable",
    "kill_switch_final_normal",
    "audit_attempt_written_without_secrets",
    "broker_place_order_called_once",
]

REQUIRED_SUBMIT_SYMBOLS = [
    "path.exists",
    "load_pending_order",
    "approved",
    "_check_expiry",
    "enable_live_trading",
    "_check_kill_switch",
    "resolve_status",
    "resolve_sync_provider",
    "BrokerSyncService",
    "validate_live_sync",
    "validate_market_quote",
    "conservative_price_for_side",
    "RiskLimits",
    "RiskManager",
    "evaluate_order",
    "live_submit_max_order_notional",
    "live_submit_allowed_symbols",
    "live_submit_allowed_sides",
    "can_submit",
    "mark_submit_requested",
    "resolve_execution_broker",
    "place_order",
    "_emit_live_submit_attempted",
    "_emit_live_submit_blocked",
]

REQUIRED_RESOLVER_SYMBOLS = [
    "enable_live_submit",
    "enable_live_trading",
    "trading_mode",
    "order_approval_mode",
    "allow_leverage",
    "_credentials_configured",
    "_live_submit_opt_in_status",
    "resolve_execution_broker",
    "can_submit",
]

REQUIRED_APPROVAL_SYMBOLS = [
    "approval_hash",
    "_compute_approval_hash",
    "approval_actor",
    "unknown",
    "_validate_v2_payload_integrity",
]

REQUIRED_TEST_FRAGMENTS = [
    "test_submit_execution_batch4_failed_gate_matrix_never_places_order",
    "test_submit_execution_batch4_all_gates_pass_fake_broker_called_once",
    "test_submit_execution_batch4_attempt_audit_payload_has_no_secrets",
    "test_market_order_blocks_when_quote_provider_returns_none",
    "test_market_order_blocks_when_quote_symbol_mismatches",
    "test_market_order_blocks_when_quote_is_stale",
    "test_market_order_blocks_when_quote_bid_ask_invalid",
    "test_market_buy_uses_ask_for_risk_revalidation",
    "test_market_sell_uses_bid_for_risk_revalidation",
    "test_live_submit_limits_block_when_notional_exceeded",
    "test_risk_failure_blocks_before_mutation",
    "test_kill_switch_active_before_final_place_order_blocks_without_broker_call",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _function_calls(tree: ast.AST, function_name: str) -> list[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            calls: list[tuple[str, int]] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    calls.append((_call_name(child.func), child.lineno))
            return sorted(calls, key=lambda item: item[1])
    return []


def _call_locations(tree: ast.AST, suffix: str) -> list[tuple[str, int]]:
    locations: list[tuple[str, int]] = []
    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_Call(self, node: ast.Call) -> Any:
            name = _call_name(node.func)
            if name == suffix or name.endswith(f".{suffix}"):
                locations.append((stack[-1] if stack else "<module>", node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return locations


def _add(checks: list[dict[str, Any]], name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def run_check(repo_root: Path) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    submit_path = repo_root / "src" / "atlas_agent" / "execution" / "submit_execution.py"
    resolver_path = repo_root / "src" / "atlas_agent" / "brokers" / "resolver.py"
    approval_path = repo_root / "src" / "atlas_agent" / "execution" / "approval.py"
    docs_path = repo_root / "docs" / "live-submit-safety-contract.md"
    tests_path = repo_root / "tests" / "execution" / "test_submit_execution.py"

    required_paths = [submit_path, resolver_path, approval_path, docs_path, tests_path]
    for path in required_paths:
        _add(checks, f"file_exists:{path.relative_to(repo_root)}", path.exists())
    if any(not path.exists() for path in required_paths):
        return False, checks

    submit_src = _read(submit_path)
    resolver_src = _read(resolver_path)
    approval_src = _read(approval_path)
    docs_src = _read(docs_path)
    tests_src = _read(tests_path)

    try:
        submit_tree = ast.parse(submit_src)
    except SyntaxError as exc:
        _add(checks, "submit_execution_ast_parse", False, str(exc))
        return False, checks
    try:
        resolver_tree = ast.parse(resolver_src)
    except SyntaxError as exc:
        _add(checks, "resolver_ast_parse", False, str(exc))
        return False, checks

    submit_functions = {
        node.name for node in ast.walk(submit_tree) if isinstance(node, ast.FunctionDef)
    }
    _add(checks, "run_submit_execution_exists", "run_submit_execution" in submit_functions)

    for symbol in REQUIRED_SUBMIT_SYMBOLS:
        _add(checks, f"submit_symbol:{symbol}", symbol in submit_src)
    for symbol in REQUIRED_RESOLVER_SYMBOLS:
        _add(checks, f"resolver_symbol:{symbol}", symbol in resolver_src)
    for symbol in REQUIRED_APPROVAL_SYMBOLS:
        _add(checks, f"approval_symbol:{symbol}", symbol in approval_src)

    place_order_locations = _call_locations(submit_tree, "place_order")
    _add(
        checks,
        "place_order_only_in_run_submit_execution",
        bool(place_order_locations)
        and all(func == "run_submit_execution" for func, _line in place_order_locations),
        str(place_order_locations),
    )

    resolve_locations = _call_locations(submit_tree, "resolve_execution_broker")
    _add(
        checks,
        "resolve_execution_broker_only_in_run_submit_execution",
        bool(resolve_locations)
        and all(func == "run_submit_execution" for func, _line in resolve_locations),
        str(resolve_locations),
    )

    calls = _function_calls(submit_tree, "run_submit_execution")
    first_line: dict[str, int] = {}
    for name, lineno in calls:
        key = name.split(".")[-1]
        first_line.setdefault(key, lineno)

    ordering_pairs = [
        ("load_pending_order", "resolve_status"),
        ("resolve_status", "resolve_sync_provider"),
        ("resolve_sync_provider", "validate_live_sync"),
        ("validate_live_sync", "RiskLimits"),
        ("RiskManager", "mark_submit_requested"),
        ("mark_submit_requested", "resolve_execution_broker"),
        ("resolve_execution_broker", "place_order"),
        ("_emit_live_submit_attempted", "place_order"),
    ]
    for before, after in ordering_pairs:
        ok = before in first_line and after in first_line and first_line[before] < first_line[after]
        _add(checks, f"order:{before}_before_{after}", ok, str(first_line))

    kill_switch_calls = [
        lineno for name, lineno in calls if name.endswith("_check_kill_switch")
    ]
    place_order_line = first_line.get("place_order", -1)
    _add(
        checks,
        "kill_switch_checked_before_and_after_prepare",
        len(kill_switch_calls) >= 2
        and kill_switch_calls[0] < first_line.get("resolve_status", -1)
        and kill_switch_calls[-1] < place_order_line,
        str(kill_switch_calls),
    )

    for gate_id in REQUIRED_DOC_GATE_IDS:
        _add(checks, f"doc_gate:{gate_id}", f"`{gate_id}`" in docs_src)
    for fragment in REQUIRED_TEST_FRAGMENTS:
        _add(checks, f"test_fragment:{fragment}", fragment in tests_src)

    forbidden_test_fragments = [
        "ALPACA_API_KEY=",
        "ALPACA_SECRET_KEY=",
        "requests.",
        "httpx.",
        "urllib.request",
    ]
    for fragment in forbidden_test_fragments:
        _add(checks, f"test_forbidden_fragment_absent:{fragment}", fragment not in tests_src)

    ok = all(check["ok"] for check in checks)
    return ok, checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    ok, checks = run_check(repo_root)
    result = {"ok": ok, "checks": checks}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif ok:
        print(f"Submit execution safety check PASSED: checks={len(checks)}")
    else:
        print("Submit execution safety check FAILED:")
        for check in checks:
            if not check["ok"]:
                print(f"- {check['name']}: {check['detail']}")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
