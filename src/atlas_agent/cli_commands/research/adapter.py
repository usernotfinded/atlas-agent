"""CLI handlers for `atlas research ...` subcommands."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_adapter_interface_contract(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import create_provider_adapter_interface_contract
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
                    print("research provider-adapter-interface-contract skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            result = create_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contract created:")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Source unlock state: {result.get('source_provider_execution_unlock_state_id', '')}")
            print(f"  Status: {result.get('adapter_contract_status', '')}")
            print(f"  State: {result.get('adapter_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_adapter_interface_contract_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-list":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import iter_provider_adapter_interface_contract_artifacts
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
                    print("research provider-adapter-interface-contract-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            items = iter_provider_adapter_interface_contract_artifacts(ws, symbol=safe_symbol)
            if args.limit:
                items = items[:args.limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_adapter_interface_contract_list", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contracts:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_adapter_interface_contract_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_adapter_interface_contract_id', '')}: {item.get('adapter_contract_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_adapter_interface_contract_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-show":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import (
                find_provider_adapter_interface_contract_by_id,
                load_provider_adapter_interface_contract,
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
                    print("research provider-adapter-interface-contract-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_adapter_interface_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-adapter-interface-contract-show skipped safely: artifact not found")
                return 1
            data = load_provider_adapter_interface_contract(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_adapter_interface_contract_shown",
                "artifact": data,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contract:")
            print(f"  ID: {data.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Status: {data.get('adapter_contract_status', '')}")
            print(f"  State: {data.get('adapter_state', '')}")
            print(f"  Adapter present: {data.get('adapter_present', False)}")
            print(f"  Adapter enabled: {data.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {data.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {data.get('provider_call_allowed', False)}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_adapter_interface_contract_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-validate":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import (
                find_provider_adapter_interface_contract_by_id,
                validate_provider_adapter_interface_contract_artifact,
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
                    print("research provider-adapter-interface-contract-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_adapter_interface_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-adapter-interface-contract-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_adapter_interface_contract_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-validate", message.lower().rstrip("."))
            return 2 if args.strict else 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_adapter_interface_contract_validated",
                "provider_adapter_interface_contract_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for check in result.checks:
                print(f"    {'✓' if check['passed'] else '✗'} {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_adapter_interface_contract_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-replay":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import replay_provider_adapter_interface_contract
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
                    print("research provider-adapter-interface-contract-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            result = replay_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_adapter_interface_contract_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-summary":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import summarize_provider_adapter_interface_contract
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
                    print("research provider-adapter-interface-contract-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Status: {result.get('adapter_contract_status', '')}")
            print(f"  State: {result.get('adapter_state', '')}")
            print(f"  Adapter present: {result.get('adapter_present', False)}")
            print(f"  Adapter enabled: {result.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {result.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_adapter_interface_contract_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-doctor":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import doctor_provider_adapter_interface_contract
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
                    print("research provider-adapter-interface-contract-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract doctor for run {safe_id}:")
            print(f"  Health: {result.get('adapter_health', '')}")
            print(f"  Adapter present: {result.get('adapter_present', False)}")
            print(f"  Adapter enabled: {result.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {result.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    return None


def handle_provider_adapter_disabled_smoke(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-adapter-disabled-smoke":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import run_disabled_adapter_smoke
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            safe_id = validate_run_id(args.contract_id)
            result = run_disabled_adapter_smoke(safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-disabled-smoke", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-disabled-smoke", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Disabled adapter smoke test: {'PASS' if result.get('ok') else 'FAIL'}")
            print(f"  Contract ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Send failed closed: {result.get('send_failed_closed', False)}")
            print(f"  Static safe error: {result.get('static_safe_error', False)}")
            print(f"  Provider response received: {result.get('provider_response_received', False)}")
            print(f"  Network call attempted: {result.get('network_call_attempted', False)}")
            print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0 if result.get("ok") else 1
    return None



HANDLERS = {
    "provider-adapter-disabled-smoke": handle_provider_adapter_disabled_smoke,
    "provider-adapter-interface-contract": handle_provider_adapter_interface_contract,
    "provider-adapter-interface-contract-doctor": handle_provider_adapter_interface_contract_doctor,
    "provider-adapter-interface-contract-list": handle_provider_adapter_interface_contract_list,
    "provider-adapter-interface-contract-replay": handle_provider_adapter_interface_contract_replay,
    "provider-adapter-interface-contract-show": handle_provider_adapter_interface_contract_show,
    "provider-adapter-interface-contract-summary": handle_provider_adapter_interface_contract_summary,
    "provider-adapter-interface-contract-validate": handle_provider_adapter_interface_contract_validate,
}
