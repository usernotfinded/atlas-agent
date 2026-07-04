"""CLI handlers for `atlas research ...` subcommands."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_execution_dry_run(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-dry-run":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                create_provider_execution_dry_run,
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
                    print("research provider-execution-dry-run skipped safely: no workspace found")
                return 1

            safe_plan_id = validate_run_id(args.provider_call_plan_id)
            artifact = create_provider_execution_dry_run(ws, safe_plan_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-dry-run", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-dry-run", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_created",
                "provider_execution_dry_run_id": artifact["provider_execution_dry_run_id"],
                "source_provider_call_plan_id": artifact["source_provider_call_plan_id"],
                "provider_id": artifact["provider_id"],
                "model_id": artifact["model_id"],
                "artifact_path": artifact["artifact_path"],
                "warnings": artifact.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-run created: {artifact['provider_execution_dry_run_id']}")
            print(f"  Source Plan: {artifact['source_provider_call_plan_id']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    return None


def handle_provider_execution_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-list":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                iter_provider_execution_dry_run_artifacts,
            )
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
                    print("research provider-execution-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_execution_dry_run_artifacts(ws, symbol=symbol_filter)
            items = items[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-execution-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_runs_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-runs: {len(items)}")
            for item in items:
                print(f"  {item['provider_execution_dry_run_id']}  {item['symbol']}  {item['provider_id']}  {item['model_id']}  {item['artifact_path']}")
        return 0
    return None


def handle_provider_execution_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-show":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                find_provider_execution_dry_run_by_id,
                load_and_validate_provider_execution_dry_run,
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
                    print("research provider-execution-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            path = find_provider_execution_dry_run_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_execution_dry_run_not_found")
            artifact = load_and_validate_provider_execution_dry_run(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-run: {artifact['provider_execution_dry_run_id']}")
            print(f"  Symbol: {artifact['symbol']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Source Plan: {artifact['source_provider_call_plan_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    return None


def handle_provider_execution_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-validate":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                find_provider_execution_dry_run_by_id,
                load_provider_execution_dry_run,
                validate_provider_execution_dry_run_artifact,
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
                    print("research provider-execution-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            path = find_provider_execution_dry_run_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_execution_dry_run_not_found")
            dry_run_data = load_provider_execution_dry_run(path, ws)
            result = validate_provider_execution_dry_run_artifact(dry_run_data, workspace_path=ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_validated",
                "provider_execution_dry_run_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution dry-run {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_execution_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-replay":
        try:
            from atlas_agent.research.provider_execution_dry_run import replay_provider_execution_dry_run
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
                    print("research provider-execution-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            replay_result = replay_provider_execution_dry_run(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_replayed",
                "provider_execution_dry_run_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution dry-run replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_execution_state(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-state":
        try:
            from atlas_agent.research.provider_execution_state import create_provider_execution_state
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
                    print("research provider-execution-state skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            result = create_provider_execution_state(ws, safe_id, args.requested_state)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if result.get("ok"):
                print(f"Provider execution state {result.get('provider_execution_state_id')}: {result.get('state')}")
            else:
                print(f"Provider execution state transition blocked: {', '.join(result.get('blocking_reasons', []))}")
        return 0 if result.get("ok") else 1
    return None


def handle_provider_execution_state_list(context: CLIContext) -> int | None:
    args = context.args
    import json

    if args.command == "research" and args.research_command == "provider-execution-state-list":
        try:
            from atlas_agent.research.provider_execution_state import iter_provider_execution_state_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state-list skipped safely: no workspace found")
                return 1

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100
            items = iter_provider_execution_state_artifacts(ws, symbol=args.symbol)
            items = items[:limit]
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_states_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution states: {len(items)} found")
            for item in items:
                sid = item.get("provider_execution_state_id", "<invalid>")
                st = item.get("state", "<invalid>")
                print(f"  {sid}: {st}")
        return 0
    return None


def handle_provider_execution_state_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-state-show":
        try:
            from atlas_agent.research.provider_execution_state import (
                find_provider_execution_state_by_id,
                load_and_validate_provider_execution_state,
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
                    print("research provider-execution-state-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            state_path = find_provider_execution_state_by_id(ws, safe_id)
            if state_path is None:
                raise ResearchSessionError("provider_execution_state_not_found")
            artifact = load_and_validate_provider_execution_state(state_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution state {safe_id}: {artifact.get('state')}")
        return 0
    return None


def handle_provider_execution_state_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-state-validate":
        try:
            from atlas_agent.research.provider_execution_state import (
                find_provider_execution_state_by_id,
                validate_provider_execution_state_artifact,
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
                    print("research provider-execution-state-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            state_path = find_provider_execution_state_by_id(ws, safe_id)
            if state_path is None:
                raise ResearchSessionError("provider_execution_state_not_found")
            import json
            data = json.loads(state_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_state_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_validated",
                "provider_execution_state_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution state {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_execution_state_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-state-replay":
        try:
            from atlas_agent.research.provider_execution_state import replay_provider_execution_state
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
                    print("research provider-execution-state-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            replay_result = replay_provider_execution_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_replayed",
                "provider_execution_state_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution state replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_execution_audit(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-audit":
        try:
            from atlas_agent.research.provider_execution_audit_packet import create_provider_execution_audit_packet
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
                    print("research provider-execution-audit skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            result = create_provider_execution_audit_packet(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution audit packet {result.get('provider_execution_audit_packet_id')}: {result.get('audit_status')}")
        return 0
    return None


def handle_provider_execution_audit_list(context: CLIContext) -> int | None:
    args = context.args
    import json

    if args.command == "research" and args.research_command == "provider-execution-audit-list":
        try:
            from atlas_agent.research.provider_execution_audit_packet import iter_provider_execution_audit_packet_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit-list skipped safely: no workspace found")
                return 1

            items = iter_provider_execution_audit_packet_artifacts(ws, symbol=args.symbol)
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": True,
                "status": "research_provider_execution_audit_packets_listed",
                "items": list(items)[:args.limit],
            }, indent=2, sort_keys=True))
        else:
            print("Provider execution audit packets:")
            for item in list(items)[:args.limit]:
                sid = item.get("provider_execution_audit_packet_id", "<invalid>")
                st = item.get("audit_status", "<invalid>")
                print(f"  {sid}: {st}")
        return 0
    return None


def handle_provider_execution_audit_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-audit-show":
        try:
            from atlas_agent.research.provider_execution_audit_packet import (
                find_provider_execution_audit_packet_by_id,
                load_and_validate_provider_execution_audit_packet,
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
                    print("research provider-execution-audit-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            audit_path = find_provider_execution_audit_packet_by_id(ws, safe_id)
            if audit_path is None:
                raise ResearchSessionError("provider_execution_audit_packet_not_found")
            artifact = load_and_validate_provider_execution_audit_packet(audit_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": True,
                "status": "research_provider_execution_audit_packet_loaded",
                "artifact": artifact,
            }, indent=2, sort_keys=True))
        else:
            print(f"Provider execution audit packet {safe_id}:")
            print(f"  audit_status: {artifact.get('audit_status')}")
            print(f"  execution_status: {artifact.get('execution_status')}")
            print(f"  latest_state: {artifact.get('latest_state')}")
        return 0
    return None


def handle_provider_execution_audit_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-audit-validate":
        try:
            from atlas_agent.research.provider_execution_audit_packet import (
                find_provider_execution_audit_packet_by_id,
                validate_provider_execution_audit_packet_artifact,
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
                    print("research provider-execution-audit-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            audit_path = find_provider_execution_audit_packet_by_id(ws, safe_id)
            if audit_path is None:
                raise ResearchSessionError("provider_execution_audit_packet_not_found")
            import json
            data = json.loads(audit_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_audit_packet_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_audit_packet_validated",
                "provider_execution_audit_packet_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution audit packet {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_execution_audit_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-audit-replay":
        try:
            from atlas_agent.research.provider_execution_audit_packet import replay_provider_execution_audit_packet
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
                    print("research provider-execution-audit-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            replay_result = replay_provider_execution_audit_packet(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_audit_packet_replayed",
                "provider_execution_audit_packet_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution audit packet replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_execution_readiness(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-readiness":
        try:
            from atlas_agent.research.provider_execution_readiness_report import create_provider_execution_readiness_report
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness skipped safely: no workspace found")
                return 1

            result = create_provider_execution_readiness_report(ws, args.provider_execution_audit_packet_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution readiness report {result.get('provider_execution_readiness_report_id')}: {result.get('readiness_status')} (score: {result.get('readiness_score')})")
        return 0
    return None


def handle_provider_execution_readiness_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-readiness-list":
        try:
            from atlas_agent.research.provider_execution_readiness_report import iter_provider_execution_readiness_report_artifacts
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
                    print("research provider-execution-readiness-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_execution_readiness_report_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-execution-readiness-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_reports_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if not items:
                print("No provider execution readiness reports found.")
            else:
                print(f"{'Created At':<24} {'Symbol':<8} {'Report ID':<34} {'Status':<24} {'Score':<6} {'Artifact'}")
                for item in items:
                    created = item.get("created_at", "")[:19]
                    print(f"{created:<24} {item['symbol']:<8} {item['provider_execution_readiness_report_id']:<34} {item['readiness_status']:<24} {item['readiness_score']:<6} {item['artifact_path']}")
        return 0
    return None


def handle_provider_execution_readiness_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-readiness-show":
        try:
            from atlas_agent.research.provider_execution_readiness_report import (
                find_provider_execution_readiness_report_by_id,
                load_and_validate_provider_execution_readiness_report,
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
                    print("research provider-execution-readiness-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            report_path = find_provider_execution_readiness_report_by_id(ws, safe_id)
            if report_path is None:
                raise ResearchSessionError("provider_execution_readiness_report_not_found")
            artifact = load_and_validate_provider_execution_readiness_report(report_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider execution readiness report")
            print(f"  Report ID: {artifact.get('provider_execution_readiness_report_id', '')}")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Readiness status: {artifact.get('readiness_status', '')}")
            print(f"  Readiness score: {artifact.get('readiness_score', 0)}")
            print(f"  Chain health: {artifact.get('chain_health', '')}")
            print(f"  Execution status: {artifact.get('execution_status', '')}")
            print(f"  Artifact: {artifact.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_execution_readiness_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-readiness-validate":
        try:
            from atlas_agent.research.provider_execution_readiness_report import (
                find_provider_execution_readiness_report_by_id,
                validate_provider_execution_readiness_report_artifact,
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
                    print("research provider-execution-readiness-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            report_path = find_provider_execution_readiness_report_by_id(ws, safe_id)
            if report_path is None:
                raise ResearchSessionError("provider_execution_readiness_report_not_found")
            import json as _json
            data = _json.loads(report_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_readiness_report_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_validated",
                "provider_execution_readiness_report_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution readiness report validation {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_execution_readiness_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-readiness-replay":
        try:
            from atlas_agent.research.provider_execution_readiness_report import replay_provider_execution_readiness_report
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
                    print("research provider-execution-readiness-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            replay_result = replay_provider_execution_readiness_report(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_replayed",
                "provider_execution_readiness_report_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution readiness report replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    return None


def handle_provider_execution_chain_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-chain-doctor":
        try:
            from atlas_agent.research.provider_execution_readiness_report import provider_execution_chain_doctor
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
                    print("research provider-execution-chain-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = provider_execution_chain_doctor(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-chain-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-chain-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Chain doctor: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Chain doctor for run {safe_id}:")
                print(f"  Symbol: {result.get('symbol', '')}")
                print(f"  Chain health: {result.get('chain_health', '')}")
                print(f"  Readiness status: {result.get('readiness_status', '')}")
                if result.get("missing_artifacts"):
                    print(f"  Missing: {', '.join(result['missing_artifacts'])}")
                if result.get("invalid_artifacts"):
                    print(f"  Invalid: {', '.join(result['invalid_artifacts'])}")
                if result.get("blocking_reasons"):
                    print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
        return 0
    return None


def handle_provider_execution_unlock_state(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state":
        try:
            from atlas_agent.research.provider_execution_unlock_state import create_provider_execution_unlock_state
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
                    print("research provider-execution-unlock-state skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_result_id)
            result = create_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock state created:")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Source review result: {result.get('source_provider_response_review_result_id', '')}")
            print(f"  Status: {result.get('unlock_state_status', '')}")
            print(f"  State: {result.get('unlock_state', '')}")
            print(f"  Current state: {result.get('current_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_execution_unlock_state_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-list":
        try:
            from atlas_agent.research.provider_execution_unlock_state import iter_provider_execution_unlock_state_artifacts
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
                    print("research provider-execution-unlock-state-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            items = iter_provider_execution_unlock_state_artifacts(ws, symbol=safe_symbol)
            if args.limit:
                items = items[:args.limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_execution_unlock_state_list", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock states:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_execution_unlock_state_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_execution_unlock_state_id', '')}: {item.get('unlock_state_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_execution_unlock_state_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-show":
        try:
            from atlas_agent.research.provider_execution_unlock_state import (
                find_provider_execution_unlock_state_by_id,
                load_provider_execution_unlock_state,
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
                    print("research provider-execution-unlock-state-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            path = find_provider_execution_unlock_state_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-execution-unlock-state-show skipped safely: artifact not found")
                return 1
            data = load_provider_execution_unlock_state(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_unlock_state_shown",
                "provider_execution_unlock_state_id": data.get("provider_execution_unlock_state_id"),
                "unlock_state_status": data.get("unlock_state_status"),
                "unlock_state": data.get("unlock_state"),
                "current_state": data.get("current_state"),
                "manual_unlock_required": data.get("manual_unlock_required"),
                "manual_unlock_granted": data.get("manual_unlock_granted"),
                "provider_execution_unlocked": data.get("provider_execution_unlocked"),
                "provider_call_allowed": data.get("provider_call_allowed"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock state:")
            print(f"  ID: {data.get('provider_execution_unlock_state_id', '')}")
            print(f"  Status: {data.get('unlock_state_status', '')}")
            print(f"  State: {data.get('unlock_state', '')}")
            print(f"  Current state: {data.get('current_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_execution_unlock_state_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-validate":
        try:
            from atlas_agent.research.provider_execution_unlock_state import (
                find_provider_execution_unlock_state_by_id,
                validate_provider_execution_unlock_state_artifact,
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
                    print("research provider-execution-unlock-state-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            path = find_provider_execution_unlock_state_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-execution-unlock-state-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_execution_unlock_state_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-validate", message.lower().rstrip("."))
            return 2 if args.strict else 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": result.valid,
                "status": "research_provider_execution_unlock_state_validated",
                "provider_execution_unlock_state_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state validation: {result.valid}")
            for check in result.checks:
                status = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_execution_unlock_state_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-replay":
        try:
            from atlas_agent.research.provider_execution_unlock_state import replay_provider_execution_unlock_state
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
                    print("research provider-execution-unlock-state-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            result = replay_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_execution_unlock_state_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-summary":
        try:
            from atlas_agent.research.provider_execution_unlock_state import summarize_provider_execution_unlock_state
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
                    print("research provider-execution-unlock-state-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Status: {result.get('unlock_state_status', '')}")
            print(f"  State: {result.get('unlock_state', '')}")
            print(f"  Current state: {result.get('current_state', '')}")
            print(f"  Provider execution unlocked: {result.get('provider_execution_unlocked', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Manual unlock granted: {result.get('manual_unlock_granted', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_execution_unlock_state_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-execution-unlock-state-doctor":
        try:
            from atlas_agent.research.provider_execution_unlock_state import doctor_provider_execution_unlock_state
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
                    print("research provider-execution-unlock-state-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state doctor for run {safe_id}:")
            print(f"  Health: {result.get('unlock_health', '')}")
            print(f"  Provider execution unlocked: {result.get('provider_execution_unlocked', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Manual unlock granted: {result.get('manual_unlock_granted', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    return None



HANDLERS = {
    "provider-execution-audit": handle_provider_execution_audit,
    "provider-execution-audit-list": handle_provider_execution_audit_list,
    "provider-execution-audit-replay": handle_provider_execution_audit_replay,
    "provider-execution-audit-show": handle_provider_execution_audit_show,
    "provider-execution-audit-validate": handle_provider_execution_audit_validate,
    "provider-execution-chain-doctor": handle_provider_execution_chain_doctor,
    "provider-execution-dry-run": handle_provider_execution_dry_run,
    "provider-execution-list": handle_provider_execution_list,
    "provider-execution-readiness": handle_provider_execution_readiness,
    "provider-execution-readiness-list": handle_provider_execution_readiness_list,
    "provider-execution-readiness-replay": handle_provider_execution_readiness_replay,
    "provider-execution-readiness-show": handle_provider_execution_readiness_show,
    "provider-execution-readiness-validate": handle_provider_execution_readiness_validate,
    "provider-execution-replay": handle_provider_execution_replay,
    "provider-execution-show": handle_provider_execution_show,
    "provider-execution-state": handle_provider_execution_state,
    "provider-execution-state-list": handle_provider_execution_state_list,
    "provider-execution-state-replay": handle_provider_execution_state_replay,
    "provider-execution-state-show": handle_provider_execution_state_show,
    "provider-execution-state-validate": handle_provider_execution_state_validate,
    "provider-execution-unlock-state": handle_provider_execution_unlock_state,
    "provider-execution-unlock-state-doctor": handle_provider_execution_unlock_state_doctor,
    "provider-execution-unlock-state-list": handle_provider_execution_unlock_state_list,
    "provider-execution-unlock-state-replay": handle_provider_execution_unlock_state_replay,
    "provider-execution-unlock-state-show": handle_provider_execution_unlock_state_show,
    "provider-execution-unlock-state-summary": handle_provider_execution_unlock_state_summary,
    "provider-execution-unlock-state-validate": handle_provider_execution_unlock_state_validate,
    "provider-execution-validate": handle_provider_execution_validate,
}
