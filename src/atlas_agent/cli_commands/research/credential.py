# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/credential.py
# PURPOSE: CLI handlers for the research CREDENTIAL BOUNDARY — proving which
#          credentials a research call would touch, and that none of them leak into
#          the artifacts it produces.
# DEPS:    research.provider_credential_boundary, research._envelope
# ==============================================================================

"""CLI handlers for `atlas research provider-credential-boundary*`.

Each handler below is only the part that differs. The dispatch guard, workspace
resolution and the fail-closed error envelope live once in `_envelope.py`; see
that module for why absorbing them is safe and what must not be absorbed with
them.
"""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._envelope import print_json, research_envelope
from atlas_agent.cli_commands.research._shared import _research_error_json


@research_envelope("provider-credential-boundary")
def handle_provider_credential_boundary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import create_provider_credential_boundary

    result = create_provider_credential_boundary(ws, args.provider_opt_in_policy_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider credential boundary {result.get('provider_credential_boundary_id')}: {result.get('credential_boundary_status')} ({result.get('credential_loading_state')})")
    return 0


@research_envelope("provider-credential-boundary-list")
def handle_provider_credential_boundary_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import iter_provider_credential_boundary_artifacts
    from atlas_agent.research.session import InvalidResearchSymbolError, sanitize_symbol

    # Kept inside the handler on purpose. `sanitize_symbol` raises with a prose
    # message that `safe_research_session_error` does not map, so letting this
    # reach the envelope's generic clause would downgrade the status code from
    # `invalid_research_symbol` to `research_error`.
    try:
        symbol_filter = sanitize_symbol(args.symbol) if args.symbol else None
    except InvalidResearchSymbolError:
        if args.json:
            _research_error_json("invalid_research_symbol", "Invalid research symbol.")
        else:
            print("research provider-credential-boundary-list skipped safely: invalid research symbol")
        return 1

    limit = max(1, min(args.limit, 100))
    items = iter_provider_credential_boundary_artifacts(ws, symbol=symbol_filter)[:limit]

    if args.json:
        print_json({
            "ok": True,
            "status": "research_provider_credential_boundaries_listed",
            "items": items,
        })
    else:
        print(f"{'Created At':<24} {'Symbol':<8} {'Boundary ID':<34} {'Status':<24} {'Artifact'}")
        for item in items:
            print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_credential_boundary_id', ''):<34} {item.get('credential_boundary_status', ''):<24} {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-credential-boundary-show")
def handle_provider_credential_boundary_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import (
        find_provider_credential_boundary_by_id,
        load_provider_credential_boundary,
    )
    from atlas_agent.research.session import ResearchSessionError, validate_run_id

    safe_id = validate_run_id(args.provider_credential_boundary_id)
    boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
    if boundary_path is None:
        raise ResearchSessionError("provider_credential_boundary_not_found")
    artifact = load_provider_credential_boundary(boundary_path, ws)

    if args.json:
        print_json({
            "ok": True,
            "status": "research_provider_credential_boundary_loaded",
            "artifact": artifact,
        })
    else:
        print(f"Provider credential boundary {artifact.get('provider_credential_boundary_id')}:")
        print(f"  Symbol: {artifact.get('symbol', '')}")
        print(f"  Credential boundary status: {artifact.get('credential_boundary_status', '')}")
        print(f"  Credential loading state: {artifact.get('credential_loading_state', '')}")
        print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
    return 0


@research_envelope("provider-credential-boundary-validate")
def handle_provider_credential_boundary_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import (
        find_provider_credential_boundary_by_id,
        validate_provider_credential_boundary_artifact,
    )
    from atlas_agent.research.session import ResearchSessionError, validate_run_id

    safe_id = validate_run_id(args.provider_credential_boundary_id)
    boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
    if boundary_path is None:
        raise ResearchSessionError("provider_credential_boundary_not_found")
    validation = validate_provider_credential_boundary_artifact(boundary_path, ws, strict=args.strict)

    if args.json:
        print_json({
            "ok": True,
            "status": "research_provider_credential_boundary_validated",
            "provider_credential_boundary_id": safe_id,
            "valid": validation.valid,
            "passed_checks": validation.passed_checks,
            "failed_checks": validation.failed_checks,
            "checks": validation.checks,
            "warnings": validation.warnings,
        })
    else:
        print(f"Provider credential boundary {safe_id}: {'valid' if validation.valid else 'invalid'}")
        print(f"  Passed: {validation.passed_checks}")
        print(f"  Failed: {validation.failed_checks}")
    if args.strict and not validation.valid:
        return 2
    return 0


@research_envelope("provider-credential-boundary-replay")
def handle_provider_credential_boundary_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import replay_provider_credential_boundary
    from atlas_agent.research.session import validate_run_id

    safe_id = validate_run_id(args.provider_credential_boundary_id)
    replay_result = replay_provider_credential_boundary(safe_id, ws, strict=args.strict)

    if args.json:
        print_json({
            "ok": True,
            "status": "research_provider_credential_boundary_replayed",
            "provider_credential_boundary_id": safe_id,
            "match": replay_result["match"],
            "expected_hash": replay_result["expected_hash"],
            "actual_hash": replay_result["actual_hash"],
            "checks": replay_result["checks"],
            "warnings": replay_result["warnings"],
        })
    else:
        print(f"Provider credential boundary {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
        print(f"  Expected hash: {replay_result['expected_hash']}")
        print(f"  Actual hash: {replay_result['actual_hash']}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-credential-boundary-summary")
def handle_provider_credential_boundary_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_credential_boundary import summarize_provider_credential_boundary_for_run
    from atlas_agent.research.session import validate_run_id

    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_credential_boundary_for_run(safe_id, ws)

    if args.json:
        print_json(result)
    elif not result.get("ok"):
        print(f"Credential boundary summary: {result.get('status', 'error')}")
        print(f"  Run ID: {safe_id}")
        print(f"  Warnings: {result.get('warnings', [])}")
    else:
        print(f"Credential boundary summary for run {safe_id}:")
        print(f"  Symbol: {result.get('symbol', '')}")
        print(f"  Credential boundary status: {result.get('credential_boundary_status', '')}")
        print(f"  Credential loading state: {result.get('credential_loading_state', '')}")
        print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
        print(f"  Env read attempted: {result.get('env_read_attempted', False)}")
        print(f"  Dotenv loaded: {result.get('dotenv_loaded', False)}")
        print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
        if result.get("blocking_reasons"):
            print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
    return 0


HANDLERS = {
    "provider-credential-boundary": handle_provider_credential_boundary,
    "provider-credential-boundary-list": handle_provider_credential_boundary_list,
    "provider-credential-boundary-replay": handle_provider_credential_boundary_replay,
    "provider-credential-boundary-show": handle_provider_credential_boundary_show,
    "provider-credential-boundary-summary": handle_provider_credential_boundary_summary,
    "provider-credential-boundary-validate": handle_provider_credential_boundary_validate,
}
