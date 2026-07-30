# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/preflight.py
# PURPOSE: CLI handlers for research PREFLIGHT — generating and freezing the call
#          plan, so a human can read exactly what WOULD be sent before it is.
# DEPS:    research.provider_preflight_freeze, providers.provider_preflight
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


@research_envelope("provider-preflight-freeze")
def handle_provider_preflight_freeze(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import create_provider_preflight_freeze
    result = create_provider_preflight_freeze(ws, args.provider_execution_readiness_report_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider preflight freeze {result.get('provider_preflight_freeze_id')}: {result.get('freeze_status')} ({result.get('freeze_recommendation')})")
    return 0


@research_envelope("provider-preflight-freeze-list")
def handle_provider_preflight_freeze_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import iter_provider_preflight_freeze_artifacts
    from atlas_agent.research.session import (
        InvalidResearchSymbolError,
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
            print("research provider-preflight-freeze-list skipped safely: invalid research symbol")
        return 1

    limit = args.limit
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100
    items = iter_provider_preflight_freeze_artifacts(ws, symbol=symbol_filter)[:limit]

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_preflight_freezes_listed",
            "items": items,
        }
        print_json(out)
    else:
        if not items:
            print("No provider preflight freeze artifacts found.")
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Freeze ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_preflight_freeze_id', ''):<34} {item.get('freeze_status', ''):<24} {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-preflight-freeze-show")
def handle_provider_preflight_freeze_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        load_and_validate_provider_preflight_freeze,
    )
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_preflight_freeze_id)
    freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_preflight_freeze_not_found")
    artifact = load_and_validate_provider_preflight_freeze(freeze_path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_preflight_freeze_loaded",
            "artifact": artifact,
        }
        print_json(out)
    else:
        print("Provider preflight freeze")
        print(f"  Freeze ID: {artifact.get('provider_preflight_freeze_id', '')}")
        print(f"  Symbol: {artifact.get('symbol', '')}")
        print(f"  Freeze status: {artifact.get('freeze_status', '')}")
        print(f"  Freeze recommendation: {artifact.get('freeze_recommendation', '')}")
        print(f"  Readiness score: {artifact.get('readiness_score', 0)}")
        print(f"  Chain health: {artifact.get('chain_health', '')}")
    return 0


@research_envelope("provider-preflight-freeze-validate")
def handle_provider_preflight_freeze_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        validate_provider_preflight_freeze_artifact,
    )
    from atlas_agent.research.session import (
        ResearchSessionError,
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_preflight_freeze_id)
    freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_preflight_freeze_not_found")
    validation = validate_provider_preflight_freeze_artifact(freeze_path, ws, strict=args.strict)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_preflight_freeze_validated",
            "provider_preflight_freeze_id": safe_id,
            "valid": validation.valid,
            "passed_checks": validation.passed_checks,
            "failed_checks": validation.failed_checks,
            "checks": validation.checks,
            "warnings": validation.warnings,
        }
        print_json(out)
    else:
        status_str = "valid" if validation.valid else "invalid"
        print(f"Provider preflight freeze validation {safe_id}: {status_str}")
        print(f"  Passed: {validation.passed_checks}")
        print(f"  Failed: {validation.failed_checks}")
    if args.strict and not validation.valid:
        return 2
    return 0


@research_envelope("provider-preflight-freeze-replay")
def handle_provider_preflight_freeze_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import replay_provider_preflight_freeze
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_preflight_freeze_id)
    replay_result = replay_provider_preflight_freeze(safe_id, ws, strict=args.strict)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_preflight_freeze_replayed",
            "provider_preflight_freeze_id": safe_id,
            "match": replay_result["match"],
            "expected_hash": replay_result["expected_hash"],
            "actual_hash": replay_result["actual_hash"],
            "checks": replay_result["checks"],
            "warnings": replay_result["warnings"],
        }
        print_json(out)
    else:
        status_str = "matches" if replay_result["match"] else "mismatch"
        print(f"Provider preflight freeze replay {safe_id}: {status_str}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-preflight-freeze-summary")
def handle_provider_preflight_freeze_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_preflight_freeze import summarize_provider_preflight_freeze_for_run
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_preflight_freeze_for_run(safe_id, ws)

    if args.json:
        print_json(result)
    else:
        if not result.get("ok"):
            print(f"Preflight freeze summary: {result.get('status', 'error')}")
            print(f"  Run ID: {safe_id}")
            print(f"  Warnings: {result.get('warnings', [])}")
        else:
            print(f"Preflight freeze summary for run {safe_id}:")
            print(f"  Symbol: {result.get('symbol', '')}")
            print(f"  Freeze status: {result.get('freeze_status', '')}")
            print(f"  Freeze recommendation: {result.get('freeze_recommendation', '')}")
            print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
            if result.get("blocking_reasons"):
                print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
    return 0



HANDLERS = {
    "provider-preflight-freeze": handle_provider_preflight_freeze,
    "provider-preflight-freeze-list": handle_provider_preflight_freeze_list,
    "provider-preflight-freeze-replay": handle_provider_preflight_freeze_replay,
    "provider-preflight-freeze-show": handle_provider_preflight_freeze_show,
    "provider-preflight-freeze-summary": handle_provider_preflight_freeze_summary,
    "provider-preflight-freeze-validate": handle_provider_preflight_freeze_validate,
}
