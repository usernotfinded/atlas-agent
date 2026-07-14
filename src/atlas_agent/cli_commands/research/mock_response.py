# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/mock_response.py
# PURPOSE: CLI handlers for the MOCK response pipeline — simulate, review, import,
#          seal. It exists so the whole research response path can be exercised
#          end-to-end without a real provider call, and so a candidate response can
#          be reviewed before anything is trusted.
# DEPS:    research.provider_mock_response_* modules
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_mock_response_simulate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-simulate":
        try:
            from atlas_agent.research.provider_mock_response_simulation import create_provider_mock_response_simulation
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
                    print("research provider-mock-response-simulate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            result = create_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-simulate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-simulate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response simulation created")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('mock_simulation_status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_provider_mock_response_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-list":
        try:
            from atlas_agent.research.provider_mock_response_simulation import iter_provider_mock_response_simulation_artifacts
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
                    print("research provider-mock-response-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_simulation_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_simulations_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response simulation artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_simulation_status']:<24} {item['artifact_path']}")
            return 0
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-list", "research command failed")
            return 1
    return None


def handle_provider_mock_response_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-show":
        try:
            from atlas_agent.research.provider_mock_response_simulation import (
                find_provider_mock_response_simulation_by_id,
                load_provider_mock_response_simulation,
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
                    print("research provider-mock-response-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            path = find_provider_mock_response_simulation_by_id(ws, safe_id)
            if not path:
                if args.json:
                    _research_error_json("not_found", "Provider mock response simulation not found.")
                else:
                    _research_error_text("research provider-mock-response-show", "not found")
                return 1

            data = load_provider_mock_response_simulation(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation: {data.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {data.get('mock_simulation_status', '')}")
            print(f"  State: {data.get('mock_simulation_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Mock adapter used: {data.get('mock_adapter_used', False)}")
            print(f"  Mock response simulated: {data.get('mock_response_simulated', False)}")
            print(f"  Mock only: {data.get('mock_only', False)}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
            if data.get("warnings"):
                print(f"  Warnings: {len(data['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_provider_mock_response_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-validate":
        try:
            from atlas_agent.research.provider_mock_response_simulation import (
                find_provider_mock_response_simulation_by_id,
                validate_provider_mock_response_simulation_artifact,
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
                    print("research provider-mock-response-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            path = find_provider_mock_response_simulation_by_id(ws, safe_id)
            if not path:
                if args.json:
                    _research_error_json("not_found", "Provider mock response simulation not found.")
                else:
                    _research_error_text("research provider-mock-response-validate", "not found")
                return 1

            result = validate_provider_mock_response_simulation_artifact(path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-validate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": result.valid,
                "status": "research_provider_mock_response_simulation_validated" if result.valid else "research_provider_mock_response_simulation_validation_failed",
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed checks: {result.passed_checks}")
            print(f"  Failed checks: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            if result.warnings:
                for w in result.warnings:
                    print(f"  Warning: {w}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_mock_response_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-replay":
        try:
            from atlas_agent.research.provider_mock_response_simulation import replay_provider_mock_response_simulation
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
                    print("research provider-mock-response-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            result = replay_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_mock_response_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-summary":
        try:
            from atlas_agent.research.provider_mock_response_simulation import summarize_provider_mock_response_simulation
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
                    print("research provider-mock-response-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('mock_simulation_status', '')}")
            print(f"  State: {result.get('mock_simulation_state', '')}")
            print(f"  Mock response simulated: {result.get('mock_response_simulated', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider request sent: {result.get('real_provider_request_sent', False)}")
            print(f"  Real provider response received: {result.get('real_provider_response_received', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    return None


def handle_provider_mock_response_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-doctor":
        try:
            from atlas_agent.research.provider_mock_response_simulation import doctor_provider_mock_response_simulation
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
                    print("research provider-mock-response-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_response_health', '')}")
            print(f"  Mock response simulated: {result.get('mock_response_simulated', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider request sent: {result.get('real_provider_request_sent', False)}")
            print(f"  Real provider response received: {result.get('real_provider_response_received', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None


def handle_provider_mock_response_import_candidate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import create_provider_mock_response_import_candidate
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
                    print("research provider-mock-response-import-candidate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            result = create_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response import candidate created")
            print(f"  ID: {result.get('provider_mock_response_import_candidate_id', '')}")
            print(f"  Source mock simulation: {result.get('source_provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_provider_mock_response_import_candidate_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-list":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import iter_provider_mock_response_import_candidate_artifacts
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
                    print("research provider-mock-response-import-candidate-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_import_candidate_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_import_candidates_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response import candidate artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_import_candidate_status']:<24} {item['artifact_path']}")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-list", "research command failed")
            return 1
        return 0
    return None


def handle_provider_mock_response_import_candidate_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-show":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import (
                find_provider_mock_response_import_candidate_by_id,
                load_and_validate_provider_mock_response_import_candidate,
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
                    print("research provider-mock-response-import-candidate-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            artifact_path = find_provider_mock_response_import_candidate_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("candidate_not_found", "Provider mock response import candidate not found.")
                else:
                    _research_error_text("research provider-mock-response-import-candidate-show", "candidate not found")
                return 1

            data = load_and_validate_provider_mock_response_import_candidate(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate: {safe_id}")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Status: {data.get('mock_import_candidate_status', '')}")
            print(f"  State: {data.get('mock_import_candidate_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_mock_response_import_candidate_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-validate":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import (
                find_provider_mock_response_import_candidate_by_id,
                validate_provider_mock_response_import_candidate_artifact,
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
                    print("research provider-mock-response-import-candidate-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            artifact_path = find_provider_mock_response_import_candidate_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("candidate_not_found", "Provider mock response import candidate not found.")
                else:
                    _research_error_text("research provider-mock-response-import-candidate-validate", "candidate not found")
                return 1

            result = validate_provider_mock_response_import_candidate_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-validate", "research command failed")
            return 1
        if args.json:
            import json
            payload = {
                "ok": result.valid,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate validation: {safe_id}")
            print(f"  Valid: {result.valid}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for c in result.checks:
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] {c['name']}: {c['message']}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_mock_response_import_candidate_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-replay":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import replay_provider_mock_response_import_candidate
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
                    print("research provider-mock-response-import-candidate-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            result = replay_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate replay: {safe_id}")
            print(f"  Match: {result.get('match', False)}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_mock_response_import_candidate_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-summary":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import summarize_provider_mock_response_import_candidate
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
                    print("research provider-mock-response-import-candidate-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate summary for run {safe_id}:")
            print(f"  Candidate ID: {result.get('provider_mock_response_import_candidate_id', 'None')}")
            print(f"  Status: {result.get('mock_import_candidate_status', '')}")
            print(f"  State: {result.get('mock_import_candidate_state', '')}")
            print(f"  Mock import candidate recorded: {result.get('mock_response_import_candidate_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider response imported: {result.get('real_provider_response_imported', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    return None


def handle_provider_mock_response_import_candidate_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-doctor":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import doctor_provider_mock_response_import_candidate
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
                    print("research provider-mock-response-import-candidate-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_import_health', '')}")
            print(f"  Mock import candidate recorded: {result.get('mock_response_import_candidate_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider response imported: {result.get('real_provider_response_imported', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None


def handle_provider_mock_response_review_sandbox(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import create_provider_mock_response_review_sandbox
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
                    print("research provider-mock-response-review-sandbox skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.import_candidate_id)
            result = create_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response review sandbox created")
            print(f"  ID: {result.get('provider_mock_response_review_sandbox_id', '')}")
            print(f"  Source import candidate: {result.get('source_provider_mock_response_import_candidate_id', '')}")
            print(f"  Status: {result.get('status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_provider_mock_response_review_sandbox_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-list":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import iter_provider_mock_response_review_sandbox_artifacts
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
                    print("research provider-mock-response-review-sandbox-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_review_sandbox_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_review_sandboxes_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response review sandbox artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_review_sandbox_status']:<24} {item['artifact_path']}")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-list", "research command failed")
            return 1
        return 0
    return None


def handle_provider_mock_response_review_sandbox_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-show":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import (
                find_provider_mock_response_review_sandbox_by_id,
                load_and_validate_provider_mock_response_review_sandbox,
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
                    print("research provider-mock-response-review-sandbox-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            artifact_path = find_provider_mock_response_review_sandbox_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("sandbox_not_found", "Provider mock response review sandbox not found.")
                else:
                    _research_error_text("research provider-mock-response-review-sandbox-show", "sandbox not found")
                return 1

            data = load_and_validate_provider_mock_response_review_sandbox(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox: {safe_id}")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Status: {data.get('mock_review_sandbox_status', '')}")
            print(f"  State: {data.get('mock_review_sandbox_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_mock_response_review_sandbox_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-validate":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import (
                find_provider_mock_response_review_sandbox_by_id,
                validate_provider_mock_response_review_sandbox_artifact,
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
                    print("research provider-mock-response-review-sandbox-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            artifact_path = find_provider_mock_response_review_sandbox_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("sandbox_not_found", "Provider mock response review sandbox not found.")
                else:
                    _research_error_text("research provider-mock-response-review-sandbox-validate", "sandbox not found")
                return 1

            result = validate_provider_mock_response_review_sandbox_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-validate", "research command failed")
            return 1
        if args.json:
            import json
            payload = {
                "ok": result.valid,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox validation: {safe_id}")
            print(f"  Valid: {result.valid}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for c in result.checks:
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] {c['name']}: {c['message']}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_mock_response_review_sandbox_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-replay":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import replay_provider_mock_response_review_sandbox
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
                    print("research provider-mock-response-review-sandbox-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            result = replay_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox replay: {safe_id}")
            print(f"  Match: {result.get('match', False)}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_mock_response_review_sandbox_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-summary":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import summarize_provider_mock_response_review_sandbox
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
                    print("research provider-mock-response-review-sandbox-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox summary for run {safe_id}:")
            print(f"  Sandbox ID: {result.get('provider_mock_response_review_sandbox_id', 'None')}")
            print(f"  Status: {result.get('mock_review_sandbox_status', '')}")
            print(f"  State: {result.get('mock_review_sandbox_state', '')}")
            print(f"  Mock review sandbox recorded: {result.get('mock_review_sandbox_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Sandbox review only: {result.get('sandbox_review_only', False)}")
            print(f"  Real provider response reviewed: {result.get('real_provider_response_reviewed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    return None


def handle_provider_mock_response_review_sandbox_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-doctor":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import doctor_provider_mock_response_review_sandbox
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
                    print("research provider-mock-response-review-sandbox-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_review_health', '')}")
            print(f"  Mock review sandbox recorded: {result.get('mock_review_sandbox_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Sandbox review only: {result.get('sandbox_review_only', False)}")
            print(f"  Real provider response reviewed: {result.get('real_provider_response_reviewed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import create_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_sandbox_id)
            result = create_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response trust decision blocker created")
            print(f"  ID: {result.get('provider_mock_response_trust_decision_blocker_id', '')}")
            print(f"  Source review sandbox: {result.get('source_provider_mock_response_review_sandbox_id', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-list":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import iter_provider_mock_response_trust_decision_blocker_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-list skipped safely: no workspace found")
                return 1

            items = iter_provider_mock_response_trust_decision_blocker_artifacts(ws, symbol=args.symbol)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_mock_response_trust_decision_blockers_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider mock response trust decision blockers:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_mock_response_trust_decision_blocker_id', '')} — {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_mock_response_trust_decision_blocker_id', '')} {item.get('symbol', '')} {item.get('trust_decision_blocker_status', '')}")
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-show":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
                find_provider_mock_response_trust_decision_blocker_by_id,
                load_provider_mock_response_trust_decision_blocker,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            artifact_path = find_provider_mock_response_trust_decision_blocker_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "blocker_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response trust decision blocker not found.")
                return 1
            data = load_provider_mock_response_trust_decision_blocker(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Status: {data.get('trust_decision_blocker_status', '')}")
            print(f"  State: {data.get('trust_decision_blocker_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-validate":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
                find_provider_mock_response_trust_decision_blocker_by_id,
                validate_provider_mock_response_trust_decision_blocker_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            artifact_path = find_provider_mock_response_trust_decision_blocker_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "blocker_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response trust decision blocker not found.")
                return 1
            result = validate_provider_mock_response_trust_decision_blocker_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-validate", "research command failed")
            return 1
        payload = {
            "ok": True,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            for check in result.checks:
                status_str = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status_str}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-replay":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import replay_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            result = replay_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-replay", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Replay: {'MATCH' if result.get('match') else 'MISMATCH'}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-summary":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import summarize_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker summary for run {safe_id}:")
            print(f"  Blocker ID: {result.get('provider_mock_response_trust_decision_blocker_id', 'None')}")
            print(f"  Status: {result.get('trust_decision_blocker_status', '')}")
            print(f"  State: {result.get('trust_decision_blocker_state', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    return None


def handle_provider_mock_response_trust_decision_blocker_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-doctor":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import doctor_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker doctor for run {safe_id}:")
            print(f"  Health: {result.get('trust_health', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None


def handle_provider_mock_response_final_safety_seal(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import create_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            result = create_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response final safety seal created")
            print(f"  ID: {result.get('provider_mock_response_final_safety_seal_id', '')}")
            print(f"  Source trust decision blocker: {result.get('source_provider_mock_response_trust_decision_blocker_id', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-list":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import iter_provider_mock_response_final_safety_seal_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-list skipped safely: no workspace found")
                return 1

            items = iter_provider_mock_response_final_safety_seal_artifacts(ws, symbol=args.symbol)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_mock_response_final_safety_seals_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider mock response final safety seals:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_mock_response_final_safety_seal_id', '')} — {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_mock_response_final_safety_seal_id', '')} {item.get('symbol', '')} {item.get('final_safety_seal_status', '')}")
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-show":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import (
                find_provider_mock_response_final_safety_seal_by_id,
                load_provider_mock_response_final_safety_seal,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            artifact_path = find_provider_mock_response_final_safety_seal_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "seal_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response final safety seal not found.")
                return 1
            data = load_provider_mock_response_final_safety_seal(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Status: {data.get('final_safety_seal_status', '')}")
            print(f"  State: {data.get('final_safety_seal_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-validate":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import (
                find_provider_mock_response_final_safety_seal_by_id,
                validate_provider_mock_response_final_safety_seal_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            artifact_path = find_provider_mock_response_final_safety_seal_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "seal_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response final safety seal not found.")
                return 1
            result = validate_provider_mock_response_final_safety_seal_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-validate", "research command failed")
            return 1
        payload = {
            "ok": True,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            for check in result.checks:
                status_str = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status_str}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-replay":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import replay_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            result = replay_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-replay", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Replay: {'MATCH' if result.get('match') else 'MISMATCH'}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-summary":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import summarize_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal summary for run {safe_id}:")
            print(f"  Seal ID: {result.get('provider_mock_response_final_safety_seal_id', 'None')}")
            print(f"  Status: {result.get('final_safety_seal_status', '')}")
            print(f"  State: {result.get('final_safety_seal_state', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    return None


def handle_provider_mock_response_final_safety_seal_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-doctor":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import doctor_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal doctor for run {safe_id}:")
            print(f"  Health: {result.get('seal_health', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None



HANDLERS = {
    "provider-mock-response-doctor": handle_provider_mock_response_doctor,
    "provider-mock-response-final-safety-seal": handle_provider_mock_response_final_safety_seal,
    "provider-mock-response-final-safety-seal-doctor": handle_provider_mock_response_final_safety_seal_doctor,
    "provider-mock-response-final-safety-seal-list": handle_provider_mock_response_final_safety_seal_list,
    "provider-mock-response-final-safety-seal-replay": handle_provider_mock_response_final_safety_seal_replay,
    "provider-mock-response-final-safety-seal-show": handle_provider_mock_response_final_safety_seal_show,
    "provider-mock-response-final-safety-seal-summary": handle_provider_mock_response_final_safety_seal_summary,
    "provider-mock-response-final-safety-seal-validate": handle_provider_mock_response_final_safety_seal_validate,
    "provider-mock-response-import-candidate": handle_provider_mock_response_import_candidate,
    "provider-mock-response-import-candidate-doctor": handle_provider_mock_response_import_candidate_doctor,
    "provider-mock-response-import-candidate-list": handle_provider_mock_response_import_candidate_list,
    "provider-mock-response-import-candidate-replay": handle_provider_mock_response_import_candidate_replay,
    "provider-mock-response-import-candidate-show": handle_provider_mock_response_import_candidate_show,
    "provider-mock-response-import-candidate-summary": handle_provider_mock_response_import_candidate_summary,
    "provider-mock-response-import-candidate-validate": handle_provider_mock_response_import_candidate_validate,
    "provider-mock-response-list": handle_provider_mock_response_list,
    "provider-mock-response-replay": handle_provider_mock_response_replay,
    "provider-mock-response-review-sandbox": handle_provider_mock_response_review_sandbox,
    "provider-mock-response-review-sandbox-doctor": handle_provider_mock_response_review_sandbox_doctor,
    "provider-mock-response-review-sandbox-list": handle_provider_mock_response_review_sandbox_list,
    "provider-mock-response-review-sandbox-replay": handle_provider_mock_response_review_sandbox_replay,
    "provider-mock-response-review-sandbox-show": handle_provider_mock_response_review_sandbox_show,
    "provider-mock-response-review-sandbox-summary": handle_provider_mock_response_review_sandbox_summary,
    "provider-mock-response-review-sandbox-validate": handle_provider_mock_response_review_sandbox_validate,
    "provider-mock-response-show": handle_provider_mock_response_show,
    "provider-mock-response-simulate": handle_provider_mock_response_simulate,
    "provider-mock-response-summary": handle_provider_mock_response_summary,
    "provider-mock-response-trust-decision-blocker": handle_provider_mock_response_trust_decision_blocker,
    "provider-mock-response-trust-decision-blocker-doctor": handle_provider_mock_response_trust_decision_blocker_doctor,
    "provider-mock-response-trust-decision-blocker-list": handle_provider_mock_response_trust_decision_blocker_list,
    "provider-mock-response-trust-decision-blocker-replay": handle_provider_mock_response_trust_decision_blocker_replay,
    "provider-mock-response-trust-decision-blocker-show": handle_provider_mock_response_trust_decision_blocker_show,
    "provider-mock-response-trust-decision-blocker-summary": handle_provider_mock_response_trust_decision_blocker_summary,
    "provider-mock-response-trust-decision-blocker-validate": handle_provider_mock_response_trust_decision_blocker_validate,
    "provider-mock-response-validate": handle_provider_mock_response_validate,
}
