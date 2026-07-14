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


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_preflight_freeze(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze":
        try:
            from atlas_agent.research.provider_preflight_freeze import create_provider_preflight_freeze
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze skipped safely: no workspace found")
                return 1

            result = create_provider_preflight_freeze(ws, args.provider_execution_readiness_report_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider preflight freeze {result.get('provider_preflight_freeze_id')}: {result.get('freeze_status')} ({result.get('freeze_recommendation')})")
        return 0
    return None


def handle_provider_preflight_freeze_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze-list":
        try:
            from atlas_agent.research.provider_preflight_freeze import iter_provider_preflight_freeze_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
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
                    print("research provider-preflight-freeze-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_preflight_freeze_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-preflight-freeze-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freezes_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if not items:
                print("No provider preflight freeze artifacts found.")
            else:
                print(f"{'Created At':<24} {'Symbol':<8} {'Freeze ID':<34} {'Status':<24} {'Artifact'}")
                for item in items:
                    print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_preflight_freeze_id', ''):<34} {item.get('freeze_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_preflight_freeze_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze-show":
        try:
            from atlas_agent.research.provider_preflight_freeze import (
                find_provider_preflight_freeze_by_id,
                load_and_validate_provider_preflight_freeze,
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
                    print("research provider-preflight-freeze-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
            if freeze_path is None:
                raise ResearchSessionError("provider_preflight_freeze_not_found")
            artifact = load_and_validate_provider_preflight_freeze(freeze_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freeze_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider preflight freeze")
            print(f"  Freeze ID: {artifact.get('provider_preflight_freeze_id', '')}")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Freeze status: {artifact.get('freeze_status', '')}")
            print(f"  Freeze recommendation: {artifact.get('freeze_recommendation', '')}")
            print(f"  Readiness score: {artifact.get('readiness_score', 0)}")
            print(f"  Chain health: {artifact.get('chain_health', '')}")
        return 0
    return None


def handle_provider_preflight_freeze_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze-validate":
        try:
            from atlas_agent.research.provider_preflight_freeze import (
                find_provider_preflight_freeze_by_id,
                validate_provider_preflight_freeze_artifact,
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
                    print("research provider-preflight-freeze-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
            if freeze_path is None:
                raise ResearchSessionError("provider_preflight_freeze_not_found")
            validation = validate_provider_preflight_freeze_artifact(freeze_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-validate", "research command failed")
            return 1
        if args.json:
            import json
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
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if validation.valid else "invalid"
            print(f"Provider preflight freeze validation {safe_id}: {status_str}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    return None


def handle_provider_preflight_freeze_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze-replay":
        try:
            from atlas_agent.research.provider_preflight_freeze import replay_provider_preflight_freeze
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
                    print("research provider-preflight-freeze-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            replay_result = replay_provider_preflight_freeze(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-replay", "research command failed")
            return 1
        if args.json:
            import json
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
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider preflight freeze replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_preflight_freeze_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-preflight-freeze-summary":
        try:
            from atlas_agent.research.provider_preflight_freeze import summarize_provider_preflight_freeze_for_run
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
                    print("research provider-preflight-freeze-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_preflight_freeze_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
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
    return None



HANDLERS = {
    "provider-preflight-freeze": handle_provider_preflight_freeze,
    "provider-preflight-freeze-list": handle_provider_preflight_freeze_list,
    "provider-preflight-freeze-replay": handle_provider_preflight_freeze_replay,
    "provider-preflight-freeze-show": handle_provider_preflight_freeze_show,
    "provider-preflight-freeze-summary": handle_provider_preflight_freeze_summary,
    "provider-preflight-freeze-validate": handle_provider_preflight_freeze_validate,
}
