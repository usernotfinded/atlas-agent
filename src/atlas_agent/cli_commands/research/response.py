# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/response.py
# PURPOSE: CLI handlers for the research RESPONSE path — schema contract, review and
#          review result. A provider response is untrusted input; nothing here
#          accepts one without validating it against a closed schema first.
# DEPS:    research.provider_response_schema_contract, .._review_result
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


@research_envelope("provider-response-intake-policy")
def handle_provider_response_intake_policy(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import create_provider_response_intake_policy
    result = create_provider_response_intake_policy(ws, args.provider_outbound_payload_preview_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider response intake policy {result.get('provider_response_intake_policy_id')}: {result.get('response_intake_policy_status')}")
        print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        print(f"  Source preview ID: {result.get('source_provider_outbound_payload_preview_id')}")
        print(f"  Artifact: {result.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-intake-policy-list")
def handle_provider_response_intake_policy_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import iter_provider_response_intake_policy_artifacts
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
            print("research provider-response-intake-policy-list skipped safely: invalid research symbol")
        return 1

    items = iter_provider_response_intake_policy_artifacts(ws, symbol=symbol_filter)

    if args.json:
        print_json({"ok": True, "status": "research_provider_response_intake_policy_list", "items": items})
    else:
        print("Provider response intake policies")
        for item in items:
            if item.get("_invalid"):
                print(f"  [INVALID] {item.get('artifact_path', '')} — {item.get('error_code', 'unknown')}")
            else:
                print(f"  {item.get('provider_response_intake_policy_id', '')}: {item.get('response_intake_policy_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-intake-policy-show")
def handle_provider_response_intake_policy_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.provider_response_intake_policy_id)
    path = find_provider_response_intake_policy_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-intake-policy-show skipped safely: artifact not found")
        return 1
    data = load_provider_response_intake_policy(path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_intake_policy_shown",
            "provider_response_intake_policy_id": data.get("provider_response_intake_policy_id", ""),
            "response_intake_policy_status": data.get("response_intake_policy_status", ""),
            "response_intake_policy_scope": data.get("response_intake_policy_scope", ""),
            "provider_id": data.get("provider_id", ""),
            "model_id": data.get("model_id", ""),
            "artifact_path": data.get("artifact_path", ""),
        }
        print_json(out)
    else:
        print(f"Provider response intake policy {data.get('provider_response_intake_policy_id', '')}")
        print(f"  Status: {data.get('response_intake_policy_status', '')}")
        print(f"  Scope: {data.get('response_intake_policy_scope', '')}")
        print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
        print(f"  Artifact: {data.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-intake-policy-validate")
def handle_provider_response_intake_policy_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        validate_provider_response_intake_policy_artifact,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.provider_response_intake_policy_id)
    path = find_provider_response_intake_policy_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-intake-policy-validate skipped safely: artifact not found")
        return 1
    result = validate_provider_response_intake_policy_artifact(path, ws)

    if args.json:
        out = {
            "ok": result.valid,
            "status": "research_provider_response_intake_policy_validated" if result.valid else "research_provider_response_intake_policy_invalid",
            "provider_response_intake_policy_id": safe_id,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
        }
        print_json(out)
    else:
        print(f"Provider response intake policy {safe_id}: {'valid' if result.valid else 'invalid'}")
        print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
        print(f"  Recommendation: {result.recommendation}")
    if args.strict and not result.valid:
        return 2
    return 0


@research_envelope("provider-response-intake-policy-replay")
def handle_provider_response_intake_policy_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import replay_provider_response_intake_policy
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.provider_response_intake_policy_id)
    replay_result = replay_provider_response_intake_policy(ws, safe_id)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_intake_policy_replayed",
            "provider_response_intake_policy_id": safe_id,
            "match": replay_result["match"],
            "original_hash": replay_result["original_hash"],
            "replayed_hash": replay_result["replayed_hash"],
        }
        print_json(out)
    else:
        print(f"Provider response intake policy {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
        print(f"  Original hash: {replay_result['original_hash']}")
        print(f"  Replayed hash: {replay_result['replayed_hash']}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-response-intake-policy-summary")
def handle_provider_response_intake_policy_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_intake_policy import summarize_provider_response_intake_policy_state
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_response_intake_policy_state(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        if not result.get("ok"):
            print(f"Response intake policy summary: {result.get('status', 'error')}")
            print(f"  Run ID: {safe_id}")
        else:
            print(f"Response intake policy summary for run {safe_id}:")
            print(f"  Policy ID: {result.get('provider_response_intake_policy_id') or 'none'}")
            print(f"  Status: {result.get('response_intake_policy_status', '')}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider response received: {result.get('provider_response_received', False)}")
    return 0


@research_envelope("provider-response-schema-contract")
def handle_provider_response_schema_contract(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import create_provider_response_schema_contract
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.pairing_id)
    result = create_provider_response_schema_contract(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider response schema contract created: {result.get('provider_response_schema_contract_id', '')}")
        print(f"  Source pairing: {result.get('source_provider_request_response_pairing_id', '')}")
        print(f"  Status: {result.get('response_schema_status', '')}")
        print(f"  State: {result.get('response_schema_state', '')}")
        print(f"  Artifact: {result.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-schema-contract-list")
def handle_provider_response_schema_contract_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import iter_provider_response_schema_contract_artifacts
    from atlas_agent.research.session import (
        sanitize_symbol,
    )
    safe_symbol = args.symbol.strip().upper() if args.symbol else None
    if safe_symbol:
        safe_symbol = sanitize_symbol(safe_symbol)
    limit = max(1, min(args.limit, 100))
    items = iter_provider_response_schema_contract_artifacts(ws, symbol=safe_symbol)
    items = items[:limit]

    if args.json:
        print_json({"ok": True, "status": "research_provider_response_schema_contract_list", "items": items})
    else:
        print(f"Provider response schema contracts ({len(items)}):")
        for item in items:
            if item.get("_invalid"):
                print(f"  [INVALID] {item.get('provider_response_schema_contract_id', '')}: {item.get('error_code', '')}")
            else:
                print(f"  {item.get('provider_response_schema_contract_id', '')}: {item.get('response_schema_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-schema-contract-show")
def handle_provider_response_schema_contract_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.contract_id)
    path = find_provider_response_schema_contract_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-schema-contract-show skipped safely: artifact not found")
        return 1
    data = load_provider_response_schema_contract(path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_schema_contract_shown",
            "provider_response_schema_contract_id": safe_id,
            "response_schema_status": data.get("response_schema_status"),
            "response_schema_state": data.get("response_schema_state"),
            "manual_review_gate_open": data.get("manual_review_gate_open"),
            "future_response_artifact_present": data.get("future_response_artifact_present"),
            "provider_response_trusted": data.get("provider_response_trusted"),
            "artifact_path": data.get("artifact_path"),
        }
        print_json(out)
    else:
        print(f"Provider response schema contract {safe_id}:")
        print(f"  Status: {data.get('response_schema_status', '')}")
        print(f"  State: {data.get('response_schema_state', '')}")
        print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
        print(f"  Artifact: {data.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-schema-contract-validate")
def handle_provider_response_schema_contract_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        validate_provider_response_schema_contract_artifact,
    )
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.contract_id)
    path = find_provider_response_schema_contract_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-schema-contract-validate skipped safely: artifact not found")
        return 1
    result = validate_provider_response_schema_contract_artifact(path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_schema_contract_validated",
            "provider_response_schema_contract_id": safe_id,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
        }
        print_json(out)
    else:
        print(f"Provider response schema contract {safe_id}: {'valid' if result.valid else 'invalid'}")
        print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
        print(f"  Recommendation: {result.recommendation}")
    if args.strict and not result.valid:
        return 2
    return 0


@research_envelope("provider-response-schema-contract-replay")
def handle_provider_response_schema_contract_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import replay_provider_response_schema_contract
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.contract_id)
    replay_result = replay_provider_response_schema_contract(ws, safe_id)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_schema_contract_replayed",
            "provider_response_schema_contract_id": safe_id,
            "match": replay_result["match"],
            "original_hash": replay_result["original_hash"],
            "replayed_hash": replay_result["replayed_hash"],
        }
        print_json(out)
    else:
        print(f"Provider response schema contract {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
        print(f"  Original hash: {replay_result['original_hash']}")
        print(f"  Replayed hash: {replay_result['replayed_hash']}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-response-schema-contract-summary")
def handle_provider_response_schema_contract_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import summarize_provider_response_schema_contract_state
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_response_schema_contract_state(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        if not result.get("ok"):
            print(f"Response schema contract summary: {result.get('status', 'error')}")
            print(f"  Run ID: {safe_id}")
        else:
            print(f"Response schema contract summary for run {safe_id}:")
            print(f"  Contract ID: {result.get('provider_response_schema_contract_id') or 'none'}")
            print(f"  Status: {result.get('response_schema_status', '')}")
            print(f"  State: {result.get('response_schema_state', '')}")
            print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
            print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
    return 0


@research_envelope("provider-response-schema-contract-doctor")
def handle_provider_response_schema_contract_doctor(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_schema_contract import doctor_provider_response_schema_contract
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = doctor_provider_response_schema_contract(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        print(f"Response schema contract doctor for run {safe_id}:")
        print(f"  Health: {result.get('schema_health', '')}")
        print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
        print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
        print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        if result.get("missing_artifacts"):
            print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
        if result.get("blocking_reasons"):
            print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
    return 0


@research_envelope("provider-response-review-result")
def handle_provider_response_review_result(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import create_provider_response_review_result
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.schema_contract_id)
    result = create_provider_response_review_result(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        print(f"Provider response review result created: {result.get('provider_response_review_result_id', '')}")
        print(f"  Source schema contract: {result.get('source_provider_response_schema_contract_id', '')}")
        print(f"  Status: {result.get('review_result_status', '')}")
        print(f"  State: {result.get('review_result_state', '')}")
        print(f"  Decision: {result.get('review_decision', '')}")
        print(f"  Artifact: {result.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-review-result-list")
def handle_provider_response_review_result_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import iter_provider_response_review_result_artifacts
    from atlas_agent.research.session import (
        sanitize_symbol,
    )
    safe_symbol = args.symbol.strip().upper() if args.symbol else None
    if safe_symbol:
        safe_symbol = sanitize_symbol(safe_symbol)
    limit = max(1, min(args.limit, 100))
    items = iter_provider_response_review_result_artifacts(ws, symbol=safe_symbol)
    items = items[:limit]

    if args.json:
        print_json({"ok": True, "status": "research_provider_response_review_result_list", "items": items})
    else:
        print(f"Provider response review results ({len(items)}):")
        for item in items:
            if item.get("_invalid"):
                print(f"  [INVALID] {item.get('provider_response_review_result_id', '')}: {item.get('error_code', '')}")
            else:
                print(f"  {item.get('provider_response_review_result_id', '')}: {item.get('review_result_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-review-result-show")
def handle_provider_response_review_result_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.review_result_id)
    path = find_provider_response_review_result_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-review-result-show skipped safely: artifact not found")
        return 1
    data = load_provider_response_review_result(path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_review_result_shown",
            "provider_response_review_result_id": safe_id,
            "review_result_status": data.get("review_result_status"),
            "review_result_state": data.get("review_result_state"),
            "review_decision": data.get("review_decision"),
            "manual_review_gate_open": data.get("manual_review_gate_open"),
            "review_result_present": data.get("review_result_present"),
            "provider_response_trusted": data.get("provider_response_trusted"),
            "artifact_path": data.get("artifact_path"),
        }
        print_json(out)
    else:
        print(f"Provider response review result {safe_id}:")
        print(f"  Status: {data.get('review_result_status', '')}")
        print(f"  State: {data.get('review_result_state', '')}")
        print(f"  Decision: {data.get('review_decision', '')}")
        print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
        print(f"  Artifact: {data.get('artifact_path', '')}")
    return 0


@research_envelope("provider-response-review-result-validate")
def handle_provider_response_review_result_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        validate_provider_response_review_result_artifact,
    )
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.review_result_id)
    path = find_provider_response_review_result_by_id(ws, safe_id)
    if path is None:
        if args.json:
            _research_error_json("research_artifact_not_found", "Research artifact not found.")
        else:
            print("research provider-response-review-result-validate skipped safely: artifact not found")
        return 1
    result = validate_provider_response_review_result_artifact(path, ws)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_review_result_validated",
            "provider_response_review_result_id": safe_id,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
        }
        print_json(out)
    else:
        print(f"Provider response review result {safe_id}: {'valid' if result.valid else 'invalid'}")
        print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
        print(f"  Recommendation: {result.recommendation}")
    if args.strict and not result.valid:
        return 2
    return 0


@research_envelope("provider-response-review-result-replay")
def handle_provider_response_review_result_replay(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import replay_provider_response_review_result
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.review_result_id)
    replay_result = replay_provider_response_review_result(ws, safe_id)

    if args.json:
        out = {
            "ok": True,
            "status": "research_provider_response_review_result_replayed",
            "provider_response_review_result_id": safe_id,
            "match": replay_result["match"],
            "original_hash": replay_result["original_hash"],
            "replayed_hash": replay_result["replayed_hash"],
        }
        print_json(out)
    else:
        print(f"Provider response review result {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
        print(f"  Original hash: {replay_result['original_hash']}")
        print(f"  Replayed hash: {replay_result['replayed_hash']}")
    if args.strict and not replay_result["match"]:
        return 2
    return 0


@research_envelope("provider-response-review-result-summary")
def handle_provider_response_review_result_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import summarize_provider_response_review_result_state
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = summarize_provider_response_review_result_state(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        if not result.get("ok"):
            print(f"Response review result summary: {result.get('status', 'error')}")
            print(f"  Run ID: {safe_id}")
        else:
            print(f"Response review result summary for run {safe_id}:")
            print(f"  Review result ID: {result.get('provider_response_review_result_id') or 'none'}")
            print(f"  Status: {result.get('review_result_status', '')}")
            print(f"  State: {result.get('review_result_state', '')}")
            print(f"  Decision: {result.get('review_decision', '')}")
            print(f"  Review result present: {result.get('review_result_present', False)}")
            print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
    return 0


@research_envelope("provider-response-review-result-doctor")
def handle_provider_response_review_result_doctor(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
    from atlas_agent.research.session import (
        validate_run_id,
    )
    safe_id = validate_run_id(args.run_id)
    result = doctor_provider_response_review_result(ws, safe_id)

    if args.json:
        print_json(result)
    else:
        print(f"Response review result doctor for run {safe_id}:")
        print(f"  Health: {result.get('review_health', '')}")
        print(f"  Review result present: {result.get('review_result_present', False)}")
        print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
        print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        if result.get("missing_artifacts"):
            print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
        if result.get("blocking_reasons"):
            print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
    return 0



HANDLERS = {
    "provider-response-intake-policy": handle_provider_response_intake_policy,
    "provider-response-intake-policy-list": handle_provider_response_intake_policy_list,
    "provider-response-intake-policy-replay": handle_provider_response_intake_policy_replay,
    "provider-response-intake-policy-show": handle_provider_response_intake_policy_show,
    "provider-response-intake-policy-summary": handle_provider_response_intake_policy_summary,
    "provider-response-intake-policy-validate": handle_provider_response_intake_policy_validate,
    "provider-response-review-result": handle_provider_response_review_result,
    "provider-response-review-result-doctor": handle_provider_response_review_result_doctor,
    "provider-response-review-result-list": handle_provider_response_review_result_list,
    "provider-response-review-result-replay": handle_provider_response_review_result_replay,
    "provider-response-review-result-show": handle_provider_response_review_result_show,
    "provider-response-review-result-summary": handle_provider_response_review_result_summary,
    "provider-response-review-result-validate": handle_provider_response_review_result_validate,
    "provider-response-schema-contract": handle_provider_response_schema_contract,
    "provider-response-schema-contract-doctor": handle_provider_response_schema_contract_doctor,
    "provider-response-schema-contract-list": handle_provider_response_schema_contract_list,
    "provider-response-schema-contract-replay": handle_provider_response_schema_contract_replay,
    "provider-response-schema-contract-show": handle_provider_response_schema_contract_show,
    "provider-response-schema-contract-summary": handle_provider_response_schema_contract_summary,
    "provider-response-schema-contract-validate": handle_provider_response_schema_contract_validate,
}
