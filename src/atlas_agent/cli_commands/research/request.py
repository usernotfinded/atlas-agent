# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/request.py
# PURPOSE: CLI handlers for building a research REQUEST and its call plan.
# DEPS:    research.provider_call_plan
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_request_response_pairing(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing":
        try:
            from atlas_agent.research.provider_request_response_pairing import create_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.intake_policy_id)
            result = create_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing created: {result.get('provider_request_response_pairing_id', '')}")
            print(f"  Source intake policy: {result.get('source_provider_response_intake_policy_id', '')}")
            print(f"  Status: {result.get('pairing_status', '')}")
            print(f"  State: {result.get('pairing_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_request_response_pairing_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-list":
        try:
            from atlas_agent.research.provider_request_response_pairing import iter_provider_request_response_pairing_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            limit = max(1, min(args.limit, 100))
            items = iter_provider_request_response_pairing_artifacts(ws, symbol=safe_symbol)
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_request_response_pairing_list", "items": items}, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairings ({len(items)}):")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_request_response_pairing_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_request_response_pairing_id', '')}: {item.get('pairing_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_request_response_pairing_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-show":
        try:
            from atlas_agent.research.provider_request_response_pairing import (
                find_provider_request_response_pairing_by_id,
                load_provider_request_response_pairing,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            path = find_provider_request_response_pairing_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-request-response-pairing-show skipped safely: artifact not found")
                return 1
            data = load_provider_request_response_pairing(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_shown",
                "provider_request_response_pairing_id": safe_id,
                "pairing_status": data.get("pairing_status"),
                "pairing_state": data.get("pairing_state"),
                "request_response_pair_completed": data.get("request_response_pair_completed"),
                "future_response_artifact_present": data.get("future_response_artifact_present"),
                "provider_response_trusted": data.get("provider_response_trusted"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}:")
            print(f"  Status: {data.get('pairing_status', '')}")
            print(f"  State: {data.get('pairing_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_request_response_pairing_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-validate":
        try:
            from atlas_agent.research.provider_request_response_pairing import (
                find_provider_request_response_pairing_by_id,
                validate_provider_request_response_pairing_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            path = find_provider_request_response_pairing_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-request-response-pairing-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_request_response_pairing_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_validated",
                "provider_request_response_pairing_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}: {'valid' if result.valid else 'invalid'}")
            print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_request_response_pairing_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-replay":
        try:
            from atlas_agent.research.provider_request_response_pairing import replay_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            replay_result = replay_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_replayed",
                "provider_request_response_pairing_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_request_response_pairing_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-summary":
        try:
            from atlas_agent.research.provider_request_response_pairing import summarize_provider_request_response_pairing_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_request_response_pairing_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Request/response pairing summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
            else:
                print(f"Request/response pairing summary for run {safe_id}:")
                print(f"  Pairing ID: {result.get('provider_request_response_pairing_id') or 'none'}")
                print(f"  Status: {result.get('pairing_status', '')}")
                print(f"  State: {result.get('pairing_state', '')}")
                print(f"  Pair completed: {result.get('request_response_pair_completed', False)}")
                print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
                print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        return 0
    return None


def handle_provider_request_response_pairing_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-request-response-pairing-doctor":
        try:
            from atlas_agent.research.provider_request_response_pairing import doctor_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Request/response pairing doctor for run {safe_id}:")
            print(f"  Health: {result.get('pairing_health', '')}")
            print(f"  Pair completed: {result.get('request_response_pair_completed', False)}")
            print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            if result.get("missing_artifacts"):
                print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    return None



HANDLERS = {
    "provider-request-response-pairing": handle_provider_request_response_pairing,
    "provider-request-response-pairing-doctor": handle_provider_request_response_pairing_doctor,
    "provider-request-response-pairing-list": handle_provider_request_response_pairing_list,
    "provider-request-response-pairing-replay": handle_provider_request_response_pairing_replay,
    "provider-request-response-pairing-show": handle_provider_request_response_pairing_show,
    "provider-request-response-pairing-summary": handle_provider_request_response_pairing_summary,
    "provider-request-response-pairing-validate": handle_provider_request_response_pairing_validate,
}
