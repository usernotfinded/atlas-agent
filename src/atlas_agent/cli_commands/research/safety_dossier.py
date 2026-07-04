"""CLI handlers for `atlas research ...` subcommands."""
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_provider_safety_dossier(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import create_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            result = create_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider safety dossier created")
            print(f"  ID: {result.get('provider_safety_dossier_id', '')}")
            print(f"  Symbol: {result.get('symbol', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Safety Verdict: {result.get('safety_verdict', '')}")
            print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
            print(f"  Chain Complete: {result.get('chain_complete', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    return None


def handle_provider_safety_dossier_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-list":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import iter_provider_safety_dossier_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-list skipped safely: no workspace found")
                return 1

            items = iter_provider_safety_dossier_artifacts(ws, symbol=args.symbol, status_filter=args.status)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_safety_dossiers_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider safety dossiers:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_safety_dossier_id', '')} — {item.get('safe_status', '')}")
                else:
                    print(f"  {item.get('provider_safety_dossier_id', '')} {item.get('safe_status', '')}")
        return 0
    return None


def handle_provider_safety_dossier_latest(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-latest":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import latest_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-latest skipped safely: no workspace found")
                return 1

            result = latest_provider_safety_dossier(ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-latest", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-latest", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if result.get("found"):
                print("Latest provider safety dossier:")
                print(f"  ID: {result.get('artifact_id', '')}")
                print(f"  Hash: {result.get('artifact_hash', '')}")
                print(f"  Created: {result.get('created_at', '')}")
                print(f"  Provider: {result.get('provider_id', '')}")
                print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
                print(f"  Chain Health: {result.get('chain_health', '')}")
                print(f"  Safety Verdict: {result.get('safety_verdict', '')}")
                print(f"  Export Available: {result.get('export_available', False)}")
                print(f"  Safe Status: {result.get('safe_status', '')}")
            else:
                print(f"No provider safety dossier found: {result.get('reason', '')}")
        return 0
    return None


def handle_provider_safety_dossier_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-show":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import (
                find_provider_safety_dossier_by_id,
                load_provider_safety_dossier,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            artifact_path = find_provider_safety_dossier_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "dossier_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider safety dossier not found.")
                return 1
            data = load_provider_safety_dossier(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Safety Verdict: {data.get('safety_verdict', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    return None


def handle_provider_safety_dossier_validate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-validate":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import (
                find_provider_safety_dossier_by_id,
                validate_provider_safety_dossier_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            artifact_path = find_provider_safety_dossier_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "dossier_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider safety dossier not found.")
                return 1
            result = validate_provider_safety_dossier_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-validate", "research command failed")
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


def handle_provider_safety_dossier_replay(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-replay":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import replay_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            result = replay_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-replay", "research command failed")
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


def handle_provider_safety_dossier_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-summary":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import summarize_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier summary for run {safe_id}:")
            print(f"  Dossier ID: {result.get('provider_safety_dossier_id', 'None')}")
            print(f"  Verdict: {result.get('safety_verdict', '')}")
            print(f"  Chain Complete: {result.get('chain_complete', False)}")
            print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
        return 0
    return None


def handle_provider_safety_dossier_doctor(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-doctor":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import doctor_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier doctor for run {safe_id}:")
            print(f"  Health: {result.get('dossier_health', '')}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    return None


def handle_provider_safety_dossier_export(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "provider-safety-dossier-export":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import export_provider_safety_dossier_markdown
            from atlas_agent.research.session import ResearchSessionError, _is_inside_workspace, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-export skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            output_path = Path(args.output).resolve()
            if not _is_inside_workspace(output_path, ws):
                if args.json:
                    print(json.dumps({"ok": False, "status": "export_path_outside_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-export refused: output path must be inside workspace")
                return 1

            result = export_provider_safety_dossier_markdown(ws, safe_id, output_path)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-export", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-export", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider safety dossier exported")
            print(f"  Dossier ID: {result.get('provider_safety_dossier_id', '')}")
            print(f"  Output: {result.get('output_path_relative', '')}")
            print(f"  Format: {result.get('format', '')}")
        return 0
    return None



HANDLERS = {
    "provider-safety-dossier": handle_provider_safety_dossier,
    "provider-safety-dossier-doctor": handle_provider_safety_dossier_doctor,
    "provider-safety-dossier-export": handle_provider_safety_dossier_export,
    "provider-safety-dossier-latest": handle_provider_safety_dossier_latest,
    "provider-safety-dossier-list": handle_provider_safety_dossier_list,
    "provider-safety-dossier-replay": handle_provider_safety_dossier_replay,
    "provider-safety-dossier-show": handle_provider_safety_dossier_show,
    "provider-safety-dossier-summary": handle_provider_safety_dossier_summary,
    "provider-safety-dossier-validate": handle_provider_safety_dossier_validate,
}
