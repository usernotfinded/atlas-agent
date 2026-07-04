"""CLI handlers for `atlas research ...` subcommands."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_opt_in_policy(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy":
        try:
            from atlas_agent.research.provider_opt_in_policy import create_provider_opt_in_policy
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy skipped safely: no workspace found")
                return 1

            result = create_provider_opt_in_policy(ws, args.provider_preflight_freeze_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {result.get('provider_opt_in_policy_id')}: {result.get('policy_status')} ({result.get('opt_in_state')})")
        return 0
    return None


def handle_provider_opt_in_policy_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy-list":
        try:
            from atlas_agent.research.provider_opt_in_policy import iter_provider_opt_in_policy_artifacts
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
                    print("research provider-opt-in-policy-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_opt_in_policy_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-opt-in-policy-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policies_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Policy ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_opt_in_policy_id', ''):<34} {item.get('policy_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_opt_in_policy_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy-show":
        try:
            from atlas_agent.research.provider_opt_in_policy import (
                find_provider_opt_in_policy_by_id,
                load_provider_opt_in_policy,
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
                    print("research provider-opt-in-policy-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
            if policy_path is None:
                raise ResearchSessionError("provider_opt_in_policy_not_found")
            artifact = load_provider_opt_in_policy(policy_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policy_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {artifact.get('provider_opt_in_policy_id')}:")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Policy status: {artifact.get('policy_status', '')}")
            print(f"  Opt-in state: {artifact.get('opt_in_state', '')}")
            print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
        return 0
    return None


def handle_provider_opt_in_policy_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy-validate":
        try:
            from atlas_agent.research.provider_opt_in_policy import (
                find_provider_opt_in_policy_by_id,
                validate_provider_opt_in_policy_artifact,
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
                    print("research provider-opt-in-policy-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
            if policy_path is None:
                raise ResearchSessionError("provider_opt_in_policy_not_found")
            validation = validate_provider_opt_in_policy_artifact(policy_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-validate", "research command failed")
            return 1
        if args.json:
            import json
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
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    return None


def handle_provider_opt_in_policy_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy-replay":
        try:
            from atlas_agent.research.provider_opt_in_policy import replay_provider_opt_in_policy
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
                    print("research provider-opt-in-policy-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            replay_result = replay_provider_opt_in_policy(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-replay", "research command failed")
            return 1
        if args.json:
            import json
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
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Expected hash: {replay_result['expected_hash']}")
            print(f"  Actual hash: {replay_result['actual_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_opt_in_policy_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-opt-in-policy-summary":
        try:
            from atlas_agent.research.provider_opt_in_policy import summarize_provider_opt_in_policy_for_run
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
                    print("research provider-opt-in-policy-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_opt_in_policy_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
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
    return None



HANDLERS = {
    "provider-opt-in-policy": handle_provider_opt_in_policy,
    "provider-opt-in-policy-list": handle_provider_opt_in_policy_list,
    "provider-opt-in-policy-replay": handle_provider_opt_in_policy_replay,
    "provider-opt-in-policy-show": handle_provider_opt_in_policy_show,
    "provider-opt-in-policy-summary": handle_provider_opt_in_policy_summary,
    "provider-opt-in-policy-validate": handle_provider_opt_in_policy_validate,
}
