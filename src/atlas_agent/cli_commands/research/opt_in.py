# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/opt_in.py
# PURPOSE: CLI handlers for the research OPT-IN policy — the explicit consent that
#          must exist before any data leaves the machine for a research provider.
# DEPS:    research.provider_opt_in_policy
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._envelope import print_json, research_envelope
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


@research_envelope("provider-opt-in-policy")
def handle_provider_opt_in_policy(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import create_provider_opt_in_policy
    from atlas_agent.research.session import ResearchSessionError
    result = create_provider_opt_in_policy(ws, args.provider_preflight_freeze_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider opt-in policy {result.get('provider_opt_in_policy_id')}: {result.get('policy_status')} ({result.get('opt_in_state')})")
    return 0


@research_envelope("provider-opt-in-policy-list")
def handle_provider_opt_in_policy_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import iter_provider_opt_in_policy_artifacts
    from atlas_agent.research.session import (
        InvalidResearchSymbolError,
        ResearchSessionError,
        sanitize_symbol,
    )

    # Kept inside the body. `sanitize_symbol` raises with a prose message that
    # `safe_research_session_error` does not map, so letting it reach the
    # envelope's clause would downgrade `invalid_research_symbol` to
    # `research_error`.
    try:
        symbol_filter = None
        if args.symbol:
            symbol_filter = sanitize_symbol(args.symbol)
    except InvalidResearchSymbolError:
        if args.json:
            _research_error_json("invalid_research_symbol", "Invalid research symbol.")
        else:
            print("research provider-opt-in-policy-list skipped safely: invalid research symbol")
        return 1

    limit = max(1, min(args.limit, 100))
    items = iter_provider_opt_in_policy_artifacts(ws, symbol=symbol_filter)[:limit]

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_opt_in_policies_listed",
            "items": items,
        }
        print_json(out)
    else:
        print(f"{'Created At':<24} {'Symbol':<8} {'Policy ID':<34} {'Status':<24} {'Artifact'}")
        for item in items:
            print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_opt_in_policy_id', ''):<34} {item.get('policy_status', ''):<24} {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-opt-in-policy-show")
def handle_provider_opt_in_policy_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        load_provider_opt_in_policy,
    )
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_opt_in_policy_id)
    policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
    if policy_path is None:
        raise ResearchSessionError("provider_opt_in_policy_not_found")
    artifact = load_provider_opt_in_policy(policy_path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_opt_in_policy_loaded",
            "artifact": artifact,
        }
        print_json(out)
    else:
        print(f"Provider opt-in policy {artifact.get('provider_opt_in_policy_id')}:")
        print(f"  Symbol: {artifact.get('symbol', '')}")
        print(f"  Policy status: {artifact.get('policy_status', '')}")
        print(f"  Opt-in state: {artifact.get('opt_in_state', '')}")
        print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
    return 0


@research_envelope("provider-opt-in-policy-validate")
def handle_provider_opt_in_policy_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        validate_provider_opt_in_policy_artifact,
    )
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_opt_in_policy_id)
    policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
    if policy_path is None:
        raise ResearchSessionError("provider_opt_in_policy_not_found")
    validation = validate_provider_opt_in_policy_artifact(policy_path, ws, strict=args.strict)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_opt_in_policy_validated",
            "provider_opt_in_policy_id": safe_id,
            "valid": validation.valid,
            "passed_checks": validation.passed_checks,
            "failed_checks": validation.failed_checks,
            "checks": validation.checks,
            "warnings": validation.warnings,
        }
        print_json(out)
    else:
        print(f"Provider opt-in policy {safe_id}: {'valid' if validation.valid else 'invalid'}")
        print(f"  Passed: {validation.passed_checks}")
        print(f"  Failed: {validation.failed_checks}")
    if args.strict and not validation.valid:
        return 2
    return 0


@research_envelope("provider-opt-in-policy-replay")
def handle_provider_opt_in_policy_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import replay_provider_opt_in_policy
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_opt_in_policy_id)
    replay_result = replay_provider_opt_in_policy(safe_id, ws, strict=args.strict)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_opt_in_policy_replayed",
            "provider_opt_in_policy_id": safe_id,
            "match": replay_result["match"],
            "expected_hash": replay_result["expected_hash"],
            "actual_hash": replay_result["actual_hash"],
            "checks": replay_result["checks"],
            "warnings": replay_result["warnings"],
        }
        print_json(out)
    else:
        print(f"Provider opt-in policy {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
        print(f"  Expected hash: {replay_result['expected_hash']}")
        print(f"  Actual hash: {replay_result['actual_hash']}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-opt-in-policy-summary")
def handle_provider_opt_in_policy_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_opt_in_policy import summarize_provider_opt_in_policy_for_run
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_opt_in_policy_for_run(safe_id, ws)

    if args.json:
        print_json(result)
    else:
        if not result.get("ok"):
            print(f"Opt-in policy summary: {result.get('status', 'error')}")
            print(f"  Run ID: {safe_id}")
            print(f"  Warnings: {result.get('warnings', [])}")
        else:
            print(f"Opt-in policy summary for run {safe_id}:")
            print(f"  Symbol: {result.get('symbol', '')}")
            print(f"  Policy status: {result.get('policy_status', '')}")
            print(f"  Opt-in state: {result.get('opt_in_state', '')}")
            print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
            if result.get("blocking_reasons"):
                print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
    return 0



HANDLERS = {
    "provider-opt-in-policy": handle_provider_opt_in_policy,
    "provider-opt-in-policy-list": handle_provider_opt_in_policy_list,
    "provider-opt-in-policy-replay": handle_provider_opt_in_policy_replay,
    "provider-opt-in-policy-show": handle_provider_opt_in_policy_show,
    "provider-opt-in-policy-summary": handle_provider_opt_in_policy_summary,
    "provider-opt-in-policy-validate": handle_provider_opt_in_policy_validate,
}
