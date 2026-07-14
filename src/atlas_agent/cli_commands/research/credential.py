# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/credential.py
# PURPOSE: CLI handlers for the research CREDENTIAL BOUNDARY — proving which
#          credentials a research call would touch, and that none of them leak into
#          the artifacts it produces.
# DEPS:    research.provider_credential_boundary
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_credential_boundary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary":
        try:
            from atlas_agent.research.provider_credential_boundary import create_provider_credential_boundary
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary skipped safely: no workspace found")
                return 1

            result = create_provider_credential_boundary(ws, args.provider_opt_in_policy_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {result.get('provider_credential_boundary_id')}: {result.get('credential_boundary_status')} ({result.get('credential_loading_state')})")
        return 0
    return None


def handle_provider_credential_boundary_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary-list":
        try:
            from atlas_agent.research.provider_credential_boundary import iter_provider_credential_boundary_artifacts
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
                    print("research provider-credential-boundary-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_credential_boundary_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-credential-boundary-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundaries_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Boundary ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_credential_boundary_id', ''):<34} {item.get('credential_boundary_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_credential_boundary_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary-show":
        try:
            from atlas_agent.research.provider_credential_boundary import (
                find_provider_credential_boundary_by_id,
                load_provider_credential_boundary,
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
                    print("research provider-credential-boundary-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
            if boundary_path is None:
                raise ResearchSessionError("provider_credential_boundary_not_found")
            artifact = load_provider_credential_boundary(boundary_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {artifact.get('provider_credential_boundary_id')}:")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Credential boundary status: {artifact.get('credential_boundary_status', '')}")
            print(f"  Credential loading state: {artifact.get('credential_loading_state', '')}")
            print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
        return 0
    return None


def handle_provider_credential_boundary_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary-validate":
        try:
            from atlas_agent.research.provider_credential_boundary import (
                find_provider_credential_boundary_by_id,
                validate_provider_credential_boundary_artifact,
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
                    print("research provider-credential-boundary-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
            if boundary_path is None:
                raise ResearchSessionError("provider_credential_boundary_not_found")
            validation = validate_provider_credential_boundary_artifact(boundary_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_validated",
                "provider_credential_boundary_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    return None


def handle_provider_credential_boundary_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary-replay":
        try:
            from atlas_agent.research.provider_credential_boundary import replay_provider_credential_boundary
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
                    print("research provider-credential-boundary-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            replay_result = replay_provider_credential_boundary(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_replayed",
                "provider_credential_boundary_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Expected hash: {replay_result['expected_hash']}")
            print(f"  Actual hash: {replay_result['actual_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_credential_boundary_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-credential-boundary-summary":
        try:
            from atlas_agent.research.provider_credential_boundary import summarize_provider_credential_boundary_for_run
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
                    print("research provider-credential-boundary-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_credential_boundary_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
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
    return None



HANDLERS = {
    "provider-credential-boundary": handle_provider_credential_boundary,
    "provider-credential-boundary-list": handle_provider_credential_boundary_list,
    "provider-credential-boundary-replay": handle_provider_credential_boundary_replay,
    "provider-credential-boundary-show": handle_provider_credential_boundary_show,
    "provider-credential-boundary-summary": handle_provider_credential_boundary_summary,
    "provider-credential-boundary-validate": handle_provider_credential_boundary_validate,
}
