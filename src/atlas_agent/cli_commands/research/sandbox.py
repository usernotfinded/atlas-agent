# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/sandbox.py
# PURPOSE: CLI handlers for the research SANDBOX — running the research pipeline in
#          a contained environment with no live provider behind it.
# DEPS:    research.llm_sandbox, research.sandbox_contracts, research._envelope
# ==============================================================================

"""CLI handlers for `atlas research sandbox*`.

Each handler below is only the part that differs. The dispatch guard, workspace
resolution and the fail-closed error envelope live once in `_envelope.py`.
"""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._envelope import print_json, research_envelope
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


@research_envelope("sandbox")
def handle_sandbox(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.llm_sandbox import build_llm_sandbox_request_from_prompt_packet
    from atlas_agent.research.session import (
        InvalidResearchSymbolError,
        UnsupportedArtifactSchemaError,
        validate_run_id,
    )

    # These two stay inside the body. Both are `ResearchSessionError` subclasses
    # raised with prose messages that `safe_research_session_error` does not map,
    # so letting them reach the envelope's clause would downgrade their status
    # codes to `research_error`.
    try:
        safe_prompt_packet_id = validate_run_id(args.prompt_packet_id)
        result = build_llm_sandbox_request_from_prompt_packet(
            workspace_path=ws,
            prompt_packet_id=safe_prompt_packet_id,
        )
    except InvalidResearchSymbolError:
        if args.json:
            _research_error_json("invalid_research_symbol", "Invalid research symbol.")
        else:
            _research_error_text("research sandbox", "invalid research symbol")
        return 1
    except UnsupportedArtifactSchemaError:
        if args.json:
            _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
        else:
            _research_error_text("research sandbox", "unsupported research artifact schema")
        return 1

    if args.json:
        print_json({
            "ok": True,
            "status": "research_sandbox_request_created",
            "symbol": result["symbol"],
            "prompt_packet_id": result["prompt_packet_id"],
            "source_run_id": result["source_run_id"],
            "sandbox_request_id": result["sandbox_request_id"],
            "provider": result["provider"],
            "recommendation": "sandbox_request_ready",
            "artifact_path": result["artifact_path"],
            "warnings": result.get("warnings", []),
        })
    else:
        print("Research sandbox request created")
        print(f"  Symbol: {result['symbol']}")
        print(f"  Prompt Packet ID: {result['prompt_packet_id']}")
        print(f"  Source Run ID: {result['source_run_id']}")
        print(f"  Sandbox Request ID: {result['sandbox_request_id']}")
        print(f"  Provider: {result['provider']}")
        print(f"  Recommendation: sandbox_request_ready")
        print(f"  Artifact: {result['artifact_path']}")
        if result.get("warnings"):
            print(f"  Warnings: {len(result['warnings'])}")
        else:
            print("  Warnings: 0")
    return 0


@research_envelope("sandbox-list")
def handle_sandbox_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.session import _iter_sandbox_request_artifacts

    limit = args.limit
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    items = _iter_sandbox_request_artifacts(ws, symbol=args.symbol)[:limit]

    if args.json:
        print_json({
            "ok": True,
            "status": "research_sandbox_listed",
            "items": items,
        })
    else:
        print(f"Sandbox requests: {len(items)}")
        for item in items:
            print(f"  {item['sandbox_request_id']}  {item['symbol']}  {item['artifact_path']}")
    return 0


@research_envelope("sandbox-show")
def handle_sandbox_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.session import (
        ResearchSessionError,
        find_sandbox_request_by_id,
        load_sandbox_request,
        validate_run_id,
    )

    safe_id = validate_run_id(args.sandbox_request_id)
    path = find_sandbox_request_by_id(ws, safe_id)
    if path is None:
        raise ResearchSessionError("sandbox_request_not_found")
    artifact = load_sandbox_request(path, ws)

    if args.json:
        print_json({
            "ok": True,
            "status": "research_sandbox_loaded",
            "artifact": artifact,
        })
    else:
        print(f"Sandbox request: {artifact['sandbox_request_id']}")
        print(f"  Symbol: {artifact['symbol']}")
        print(f"  Prompt Packet ID: {artifact['prompt_packet_id']}")
        print(f"  Source Run ID: {artifact['source_run_id']}")
        print(f"  Provider: {artifact['provider']}")
        print(f"  Artifact: {artifact['artifact_path']}")
    return 0


@research_envelope("sandbox-validate")
def handle_sandbox_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.sandbox_contracts import validate_sandbox_request_artifact
    from atlas_agent.research.session import (
        ResearchSessionError,
        find_sandbox_request_by_id,
        load_sandbox_request,
        validate_run_id,
    )

    safe_id = validate_run_id(args.sandbox_request_id)
    path = find_sandbox_request_by_id(ws, safe_id)
    if path is None:
        raise ResearchSessionError("sandbox_request_not_found")
    artifact = load_sandbox_request(path, ws)
    result = validate_sandbox_request_artifact(artifact)

    if args.json:
        print_json({
            "ok": True,
            "status": "research_sandbox_validated",
            "sandbox_request_id": artifact["sandbox_request_id"],
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "warnings": result.warnings,
        })
    else:
        status_str = "valid" if result.valid else "invalid"
        print(f"Sandbox request {artifact['sandbox_request_id']}: {status_str}")
        print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
    if args.strict and not result.valid:
        return 2
    return 0


@research_envelope("sandbox-replay")
def handle_sandbox_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.llm_sandbox import _build_sandbox_request_dict
    from atlas_agent.research.session import (
        ResearchSessionError,
        find_prompt_packet_by_id,
        find_sandbox_request_by_id,
        load_prompt_packet,
        load_sandbox_request,
        validate_run_id,
    )

    safe_id = validate_run_id(args.sandbox_request_id)
    sandbox_path = find_sandbox_request_by_id(ws, safe_id)
    if sandbox_path is None:
        raise ResearchSessionError("sandbox_request_not_found")
    sandbox = load_sandbox_request(sandbox_path, ws)

    prompt_packet_id = sandbox.get("prompt_packet_id", "")
    if not prompt_packet_id:
        raise ResearchSessionError("invalid_sandbox_lineage")

    packet_path = find_prompt_packet_by_id(ws, prompt_packet_id)
    if packet_path is None:
        raise ResearchSessionError("prompt_packet_not_found")
    prompt_packet = load_prompt_packet(packet_path, ws)

    rebuilt = _build_sandbox_request_dict(prompt_packet, prompt_packet_id, safe_id)
    actual_hash = sandbox.get("content_hash", "")
    expected_hash = rebuilt.get("content_hash", "")
    match = actual_hash == expected_hash

    checks = [
        {"name": "sandbox_request_loaded", "passed": True, "message": "Sandbox request loaded."},
        {"name": "prompt_packet_loaded", "passed": True, "message": "Prompt packet loaded."},
        {"name": "hash_matches", "passed": match, "message": "Hash matches." if match else "Hash mismatch detected."},
    ]

    if args.json:
        print_json({
            "ok": True,
            "status": "research_sandbox_replayed",
            "sandbox_request_id": safe_id,
            "source_prompt_packet_id": prompt_packet_id,
            "match": match,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "checks": checks,
        })
    else:
        status_str = "matches" if match else "mismatch"
        print(f"Sandbox replay {safe_id}: {status_str}")
    if args.strict and not match:
        return 2
    return 0


HANDLERS = {
    "sandbox": handle_sandbox,
    "sandbox-list": handle_sandbox_list,
    "sandbox-replay": handle_sandbox_replay,
    "sandbox-show": handle_sandbox_show,
    "sandbox-validate": handle_sandbox_validate,
}
