# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/provider_misc.py
# PURPOSE: CLI handlers for the remaining research provider commands — outbound
#          payload preview, request/response pairing, response intake policy.
# DEPS:    research.provider_outbound_payload_preview, .._request_response_pairing,
#          .._response_intake_policy
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_providers(context: CLIContext) -> int | None:
    args = context.args
    import json

    if args.command == "research" and args.research_command == "providers":
        from atlas_agent.research.providers import list_research_providers

        providers = list_research_providers()
        if args.json:
            import json

            payload = {
                "ok": True,
                "status": "research_providers_listed",
                "providers": [
                    {
                        "name": p.name,
                        "status": p.status,
                        "enabled": p.enabled,
                        "default": p.default,
                        "local": p.local,
                        "network": p.network,
                        "requires_api_key": p.requires_api_key,
                    }
                    for p in providers
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Research providers\n")
            for p in providers:
                print(p.name)
                print(f"  Status: {p.status}")
                print(f"  Default: {'yes' if p.default else 'no'}")
                print(f"  Local: {'yes' if p.local else 'no'}")
                print(f"  Network: {'yes' if p.network else 'no'}")
                print(f"  Requires API key: {'yes' if p.requires_api_key else 'no'}")
                print()
            print("External LLM research providers are not enabled.")
        return 0
    return None


def handle_provider_targets(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-targets":
        try:
            from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
            from atlas_agent.research.session import ResearchSessionError

            targets = list_disabled_provider_call_targets()
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-targets", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-targets", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_targets_listed",
                "targets": targets,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider call targets")
            for t in targets:
                print(f"  {t['provider_id']}")
                print(f"    Status: {t['status']}")
                print(f"    Enabled: {'yes' if t['enabled'] else 'no'}")
                print(f"    Network: {'yes' if t['network'] else 'no'}")
                print(f"    Description: {t['description']}")
        return 0
    return None


def handle_provider_plan(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-plan":
        try:
            from atlas_agent.research.provider_call_plan import (
                create_provider_call_plan,
                validate_model_id,
                validate_provider_id,
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
                    print("research provider-plan skipped safely: no workspace found")
                return 1

            safe_sandbox_request_id = validate_run_id(args.sandbox_request_id)
            provider_id = validate_provider_id(args.provider)
            model_id = validate_model_id(args.model)

            artifact = create_provider_call_plan(ws, safe_sandbox_request_id, provider_id, model_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_created",
                "provider_call_plan_id": artifact["provider_call_plan_id"],
                "source_sandbox_request_id": artifact["source_sandbox_request_id"],
                "provider_id": artifact["provider_id"],
                "model_id": artifact["model_id"],
                "artifact_path": artifact["artifact_path"],
                "warnings": artifact.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plan created: {artifact['provider_call_plan_id']}")
            print(f"  Source Sandbox: {artifact['source_sandbox_request_id']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    return None


def handle_provider_plan_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-plan-list":
        try:
            from atlas_agent.research.provider_call_plan import iter_provider_call_plan_artifacts
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
                    print("research provider-plan-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_call_plan_artifacts(ws, symbol=symbol_filter)
            items = items[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-plan-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plans_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plans: {len(items)}")
            for item in items:
                print(f"  {item['provider_call_plan_id']}  {item['symbol']}  {item['provider_id']}  {item['model_id']}  {item['artifact_path']}")
        return 0
    return None


def handle_provider_plan_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-plan-show":
        try:
            from atlas_agent.research.provider_call_plan import (
                find_provider_call_plan_by_id,
                load_and_validate_provider_call_plan,
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
                    print("research provider-plan-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            path = find_provider_call_plan_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_call_plan_not_found")
            artifact = load_and_validate_provider_call_plan(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plan: {artifact['provider_call_plan_id']}")
            print(f"  Symbol: {artifact['symbol']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Source Sandbox: {artifact['source_sandbox_request_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    return None


def handle_provider_plan_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-plan-validate":
        try:
            from atlas_agent.research.provider_call_plan import (
                find_provider_call_plan_by_id,
                load_provider_call_plan,
                validate_provider_call_plan_artifact,
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
                    print("research provider-plan-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            path = find_provider_call_plan_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_call_plan_not_found")
            plan_data = load_provider_call_plan(path, ws)
            result = validate_provider_call_plan_artifact(plan_data, workspace_path=ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_validated",
                "provider_call_plan_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider call plan {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_plan_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-plan-replay":
        try:
            from atlas_agent.research.provider_call_plan import replay_provider_call_plan
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
                    print("research provider-plan-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            replay_result = replay_provider_call_plan(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_replayed",
                "provider_call_plan_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider call plan replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_payload_preview(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import create_provider_outbound_payload_preview
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview skipped safely: no workspace found")
                return 1

            result = create_provider_outbound_payload_preview(ws, args.provider_credential_boundary_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {result.get('provider_outbound_payload_preview_id')}: {result.get('payload_preview_status')}")
            print(f"  Payload body stored: {result.get('payload_body_stored', False)}")
            print(f"  Outbound request sent: {result.get('outbound_request_sent', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_payload_preview_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview-list":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import iter_provider_outbound_payload_preview_artifacts
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
                    print("research provider-payload-preview-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_outbound_payload_preview_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-payload-preview-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_previews_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Preview ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_outbound_payload_preview_id', ''):<34} {item.get('payload_preview_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_payload_preview_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview-show":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import (
                find_provider_outbound_payload_preview_by_id,
                load_provider_outbound_payload_preview,
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
                    print("research provider-payload-preview-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            preview_path = find_provider_outbound_payload_preview_by_id(ws, safe_id)
            if preview_path is None:
                raise ResearchSessionError("provider_outbound_payload_preview_not_found")
            artifact = load_provider_outbound_payload_preview(preview_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}:")
            print(f"  Status: {artifact.get('payload_preview_status', '')}")
            print(f"  Scope: {artifact.get('payload_preview_scope', '')}")
            print(f"  Provider: {artifact.get('provider_id', '')}")
            print(f"  Model: {artifact.get('model_id', '')}")
            print(f"  Payload body stored: {artifact.get('payload_body_stored', False)}")
            print(f"  Outbound request sent: {artifact.get('outbound_request_sent', False)}")
            print(f"  Artifact: {artifact.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_payload_preview_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview-validate":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import (
                find_provider_outbound_payload_preview_by_id,
                validate_provider_outbound_payload_preview_artifact,
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
                    print("research provider-payload-preview-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            preview_path = find_provider_outbound_payload_preview_by_id(ws, safe_id)
            if preview_path is None:
                raise ResearchSessionError("provider_outbound_payload_preview_not_found")
            validation = validate_provider_outbound_payload_preview_artifact(preview_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_validated",
                "provider_outbound_payload_preview_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    return None


def handle_provider_payload_preview_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview-replay":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import replay_provider_outbound_payload_preview
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
                    print("research provider-payload-preview-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            replay_result = replay_provider_outbound_payload_preview(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_replayed",
                "provider_outbound_payload_preview_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_payload_preview_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-payload-preview-summary":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import summarize_provider_outbound_payload_preview_state
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
                    print("research provider-payload-preview-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_outbound_payload_preview_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Payload preview summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Payload preview summary for run {safe_id}:")
                print(f"  Preview ID: {result.get('provider_outbound_payload_preview_id') or 'none'}")
                print(f"  Status: {result.get('payload_preview_status', '')}")
                print(f"  Payload body stored: {result.get('payload_body_stored', False)}")
                print(f"  Outbound request sent: {result.get('outbound_request_sent', False)}")
                print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
        return 0
    return None



HANDLERS = {
    "provider-payload-preview": handle_provider_payload_preview,
    "provider-payload-preview-list": handle_provider_payload_preview_list,
    "provider-payload-preview-replay": handle_provider_payload_preview_replay,
    "provider-payload-preview-show": handle_provider_payload_preview_show,
    "provider-payload-preview-summary": handle_provider_payload_preview_summary,
    "provider-payload-preview-validate": handle_provider_payload_preview_validate,
    "provider-plan": handle_provider_plan,
    "provider-plan-list": handle_provider_plan_list,
    "provider-plan-replay": handle_provider_plan_replay,
    "provider-plan-show": handle_provider_plan_show,
    "provider-plan-validate": handle_provider_plan_validate,
    "provider-targets": handle_provider_targets,
    "providers": handle_providers,
}
