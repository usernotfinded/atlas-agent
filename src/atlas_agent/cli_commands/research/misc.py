# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/misc.py
# PURPOSE: CLI handlers for the research session commands — plan, prompt, run,
#          verify, evaluate, artifacts.
# DEPS:    research.session, research.artifact_store
#
# NOTE:    "misc" is a smell, not a category. At ~1.5k lines this module has no
#          organising theme; splitting it by subcommand family would be an
#          improvement, and the banners below are a stopgap.
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import Any

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


def handle_market(context: CLIContext) -> int | None:
    args = context.args

    if args.command == "research" and args.research_command == "market":
        if args.json:
            _research_error_json("legacy_command_disabled", "research market is legacy and disabled in the frozen local research pipeline.")
        else:
            _research_error_text("research market", "legacy and disabled in the frozen local research pipeline")
        return 1
    return None


def handle_run(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research import ResearchConfigurationError
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "run":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedResearchProviderError,
                run_research_session,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research run skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            artifact = run_research_session(
                symbol=args.symbol,
                workspace_path=ws,
                memory_dir=ws / "memory",
                event_logger=event_logger,
                provider_name=args.provider,
                use_memory=not args.no_memory,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research run skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research run skipped safely: unsupported research provider")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research run", message.lower().rstrip("."))
            return 1
        except ResearchConfigurationError:
            if args.json:
                _research_error_json("configuration_error", "Configuration error.")
            else:
                _research_error_text("research run", "configuration error")
            return 0
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research run", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "created",
                "symbol": artifact.symbol,
                "mode": artifact.mode,
                "provider": artifact.provider,
                "run_id": artifact.run_id,
                "artifact_path": artifact.artifact_path,
                "warnings": artifact.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Research artifact created")
            print(f"  Symbol: {artifact.symbol}")
            print(f"  Mode: {artifact.mode}")
            print(f"  Provider: {artifact.provider}")
            print(f"  Artifact: {artifact.artifact_path}")
            if artifact.warnings:
                print(f"  Warnings: {len(artifact.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_list(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "list":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                iter_research_artifacts,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_research_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "research_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No research artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Warnings':<9} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['run_id']:<34} {item['provider']:<14} {item['warnings_count']:<9} {item['artifact_path']}")
            return 0
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research list", "research command failed")
            return 1
    return None


def handle_show(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "show":
        try:
            from atlas_agent.research.session import (
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                find_research_artifact_by_run_id,
                load_research_artifact,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research show skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)
            artifact_path = find_research_artifact_by_run_id(ws, safe_run_id)
            if artifact_path is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "artifact_not_found"}, indent=2, sort_keys=True))
                else:
                    print("research show skipped safely: artifact not found")
                return 1

            artifact = load_research_artifact(artifact_path, ws)
            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "research_loaded",
                    "artifact": artifact,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                print("Research Artifact")
                print(f"  Run ID: {artifact.get('run_id', '')}")
                print(f"  Symbol: {artifact.get('symbol', '')}")
                print(f"  Created: {artifact.get('created_at', '')}")
                print(f"  Provider: {artifact.get('provider', '')}")
                print(f"  Summary: {artifact.get('summary', '')}")
                print(f"  Thesis: {artifact.get('thesis', '')}")
                risks = artifact.get("risks", [])
                if risks:
                    print("  Risks:")
                    for r in risks:
                        print(f"    - {r}")
                inv = artifact.get("invalidation_conditions", [])
                if inv:
                    print("  Invalidation Conditions:")
                    for i in inv:
                        print(f"    - {i}")
                print(f"  Paper-only Plan: {artifact.get('paper_only_plan', '')}")
                artifact_warnings = artifact.get("warnings", [])
                if artifact_warnings:
                    print(f"  Warnings: {len(artifact_warnings)}")
                else:
                    print("  Warnings: 0")
                print(f"  Artifact: {artifact.get('artifact_path', '')}")
            return 0
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research show", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research show", "research command failed")
            return 1
    return None


def handle_plan(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "plan":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                create_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research plan skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            plan = create_paper_plan(
                workspace_path=ws,
                run_id=args.run_id,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research plan skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research plan skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research plan", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research plan", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research plan", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "paper_plan_created",
                "symbol": plan.symbol,
                "source_run_id": plan.source_run_id,
                "plan_id": plan.plan_id,
                "artifact_path": plan.artifact_path,
                "warnings": plan.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan created")
            print(f"  Symbol: {plan.symbol}")
            print(f"  Mode: {plan.mode}")
            print(f"  Source Run ID: {plan.source_run_id}")
            print(f"  Plan ID: {plan.plan_id}")
            print(f"  Artifact: {plan.artifact_path}")
            if plan.warnings:
                print(f"  Warnings: {len(plan.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_summary(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "summary":
        try:
            from atlas_agent.research.session import (
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                summarize_research_workspace,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research summary skipped safely: no workspace found")
                return 1

            summary = summarize_research_workspace(ws)
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research summary", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research summary", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_summary",
                "research_count": summary["research_count"],
                "plan_count": summary["plan_count"],
                "symbols": summary["symbols"],
                "warnings": summary["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if summary["research_count"] == 0 and summary["plan_count"] == 0:
                print("No research artifacts found.")
            else:
                print("Research summary")
                print(f"Research artifacts: {summary['research_count']}")
                print(f"Paper plans: {summary['plan_count']}")
                sym_names = [s["symbol"] for s in summary["symbols"]]
                if sym_names:
                    print(f"Symbols: {', '.join(sym_names)}")
                for sym in summary["symbols"]:
                    print()
                    print(f"{sym['symbol']}")
                    if sym["latest_research_run_id"]:
                        print(f"  Latest research: {sym['latest_research_run_id']}")
                    if sym["latest_plan_id"]:
                        print(f"  Latest plan: {sym['latest_plan_id']}")
            if summary["warnings"]:
                print()
                for w in summary["warnings"]:
                    print(f"Warning: {w}")
        return 0
    return None


def handle_verify(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "verify":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                verify_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research verify skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            verification = verify_paper_plan(
                workspace_path=ws,
                plan_id=args.plan_id,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research verify skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research verify skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research verify", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research verify", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research verify", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_verification_created",
                "symbol": verification.symbol,
                "source_plan_id": verification.source_plan_id,
                "verification_id": verification.verification_id,
                "recommendation": verification.recommendation,
                "passed_checks": verification.passed_checks,
                "failed_checks": verification.failed_checks,
                "artifact_path": verification.artifact_path,
                "warnings": verification.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan verification created")
            print(f"  Symbol: {verification.symbol}")
            print(f"  Mode: {verification.mode}")
            print(f"  Source Plan ID: {verification.source_plan_id}")
            print(f"  Verification ID: {verification.verification_id}")
            print(f"  Recommendation: {verification.recommendation}")
            print(f"  Passed checks: {verification.passed_checks}")
            print(f"  Failed checks: {verification.failed_checks}")
            print(f"  Artifact: {verification.artifact_path}")
            if verification.warnings:
                print(f"  Warnings: {len(verification.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_evaluate(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "evaluate":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                evaluate_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research evaluate skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            evaluation = evaluate_paper_plan(
                workspace_path=ws,
                plan_id=args.plan_id,
                data_path=args.data,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research evaluate skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research evaluate skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research evaluate", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research evaluate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research evaluate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_evaluation_created",
                "symbol": evaluation.symbol,
                "source_plan_id": evaluation.source_plan_id,
                "evaluation_id": evaluation.evaluation_id,
                "recommendation": evaluation.recommendation,
                "artifact_path": evaluation.artifact_path,
                "passed_checks": sum(1 for c in evaluation.checks if c["status"] == "pass"),
                "failed_checks": sum(1 for c in evaluation.checks if c["status"] == "fail"),
                "metrics": evaluation.metrics,
                "warnings": evaluation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan evaluation created")
            print(f"  Symbol: {evaluation.symbol}")
            print(f"  Mode: {evaluation.mode}")
            print(f"  Source Plan ID: {evaluation.source_plan_id}")
            print(f"  Evaluation ID: {evaluation.evaluation_id}")
            print(f"  Recommendation: {evaluation.recommendation}")
            print(f"  Rows: {evaluation.metrics.get('row_count', 0)}")
            print(f"  Artifact: {evaluation.artifact_path}")
            if evaluation.warnings:
                print(f"  Warnings: {len(evaluation.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    return None


def handle_check_artifacts(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "check-artifacts":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                check_research_artifacts,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research check-artifacts skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            result = check_research_artifacts(ws, symbol_filter=symbol_filter)
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research check-artifacts skipped safely: invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research check-artifacts", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research check-artifacts", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research check-artifacts", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Research artifact health check")
            print(f"  Research artifacts: {result['counts']['research']}")
            print(f"  Paper plans: {result['counts']['plans']}")
            print(f"  Verifications: {result['counts']['verifications']}")
            print(f"  Evaluations: {result['counts']['evaluations']}")
            print(f"  Provider call plans: {result['counts']['provider_call_plans']}")
            print(f"  Provider execution dry-runs: {result['counts']['provider_execution_dry_runs']}")
            print(f"  Provider execution readiness reports: {result['counts']['provider_execution_readiness_reports']}")
            print(f"  Provider outbound payload previews: {result['counts']['provider_outbound_payload_previews']}")
            total_issues = len(result["issues"])
            total_warnings = len(result["warnings"])
            print(f"  Issues: {total_issues}")
            print(f"  Warnings: {total_warnings}")
            if result["issues"]:
                print("\nIssues:")
                for issue in result["issues"]:
                    print(f"  - {issue['code']}: {issue['path']}")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning['code']}: {warning['path']}")
            if not result["issues"] and not result["warnings"]:
                print("\nNo artifact health issues found.")
        if args.strict and result["issues"]:
            return 2
        return 0
    return None


def handle_timeline(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "timeline":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                build_research_timeline,
                sanitize_symbol,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research timeline skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            run_id_filter = None
            if args.run_id:
                run_id_filter = validate_run_id(args.run_id)

            limit = args.limit
            if limit < 1:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "invalid_limit"}, indent=2, sort_keys=True))
                else:
                    print("research timeline skipped safely: limit must be positive")
                return 1
            if limit > 100:
                limit = 100

            result = build_research_timeline(
                ws,
                symbol_filter=symbol_filter,
                run_id_filter=run_id_filter,
                limit=limit,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research timeline skipped safely: invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research timeline", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research timeline", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research timeline", "research command failed")
            return 1
        if args.json:
            import json
            try:
                print(json.dumps(result, indent=2, sort_keys=True))
            except (ValueError, TypeError):
                print(json.dumps({
                    "ok": False,
                    "status": "research_timeline_failed",
                    "error_code": "research_timeline_serialization_failed",
                    "message": "Research timeline could not be generated safely.",
                }, indent=2, sort_keys=True))
                return 1
        else:
            entries = result.get("entries", [])
            if not entries:
                print("No research timeline entries found.")
            else:
                print("Research timeline")
                for entry in entries:
                    symbol = entry.get("symbol", "")
                    run_id = entry.get("run_id", "")
                    print(f"\n{symbol} — {run_id}")
                    print(f"  Research: {entry.get('research_path', '')}")
                    for plan in entry.get("plans", []):
                        plan_id = plan.get("plan_id", "")
                        print(f"  Plan: {plan_id}")
                        for v in plan.get("verifications", []):
                            vid = v.get("verification_id", "")
                            rec = v.get("recommendation", "")
                            print(f"    Verification: {vid} — {rec}")
                        for e in plan.get("evaluations", []):
                            eid = e.get("evaluation_id", "")
                            rec = e.get("recommendation", "")
                            print(f"    Evaluation: {eid} — {rec}")
                    for prompt in entry.get("prompts", []):
                        prompt_id = prompt.get("prompt_packet_id", "")
                        print(f"  Prompt: {prompt_id}")
                        for pr in prompt.get("provider_responses", []):
                            pr_id = pr.get("provider_response_id", "")
                            provider = pr.get("provider", "")
                            rec = pr.get("recommendation", "")
                            print(f"    Provider response: {pr_id} ({provider}) — {rec}")
                            for rr in pr.get("response_reviews", []):
                                rr_id = rr.get("response_review_id", "")
                                rr_rec = rr.get("recommendation", "")
                                print(f"      Response review: {rr_id} — {rr_rec}")
                        for sr in prompt.get("sandbox_requests", []):
                            sr_id = sr.get("sandbox_request_id", "")
                            print(f"    Sandbox request: {sr_id}")
                            for pcp in sr.get("provider_call_plans", []):
                                pcp_id = pcp.get("provider_call_plan_id", "")
                                print(f"      Provider call plan: {pcp_id}")
                                for ped in pcp.get("provider_execution_dry_runs", []):
                                    ped_id = ped.get("provider_execution_dry_run_id", "")
                                    print(f"        Provider execution dry-run: {ped_id}")
                                    for pes in ped.get("provider_execution_states", []):
                                        pes_id = pes.get("provider_execution_state_id", "")
                                        pes_state = pes.get("state", "")
                                        print(f"          Provider execution state: {pes_id} ({pes_state})")
                                        for peap in pes.get("provider_execution_audit_packets", []):
                                            peap_id = peap.get("provider_execution_audit_packet_id", "")
                                            print(f"            Provider execution audit packet: {peap_id}")
                                            for perr in peap.get("provider_execution_readiness_reports", []):
                                                perr_id = perr.get("provider_execution_readiness_report_id", "")
                                                perr_status = perr.get("readiness_status", "")
                                                perr_score = perr.get("readiness_score", 0)
                                                print(f"              Provider execution readiness report: {perr_id} ({perr_status}, score: {perr_score})")
            timeline_warnings = result.get("warnings", [])
            if timeline_warnings:
                print("\nWarnings:")
                for w in timeline_warnings:
                    print(f"  - {w.get('code', '')}: {w.get('path', '')}")
        return 0
    return None


def handle_prompt(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "prompt":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                generate_prompt_packet,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research prompt skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)

            max_chars = args.max_context_chars
            if not isinstance(max_chars, int) or max_chars <= 0 or max_chars > 20000:
                if args.json:
                    _research_error_json("invalid_max_context_chars", "Invalid max-context-chars value.")
                else:
                    _research_error_text("research prompt", "invalid max-context-chars value")
                return 1

            event_logger = EventLogger(ws / "events")

            packet = generate_prompt_packet(
                ws,
                safe_run_id,
                max_context_chars=max_chars,
                event_logger=event_logger,
            )

            if args.json:
                import json

                out = {
                    "ok": True,
                    "status": "research_prompt_packet_created",
                    "symbol": packet["symbol"],
                    "source_run_id": packet["source_run_id"],
                    "prompt_packet_id": packet["prompt_packet_id"],
                    "artifact_path": packet["artifact_path"],
                    "warnings": packet.get("warnings", []),
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                print("Research prompt packet created")
                print(f"Symbol: {packet['symbol']}")
                print(f"Mode: {packet['mode']}")
                print(f"Source Run ID: {packet['source_run_id']}")
                print(f"Prompt Packet ID: {packet['prompt_packet_id']}")
                print(f"Artifact: {packet['artifact_path']}")
            return 0
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research prompt", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research prompt", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research prompt", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research prompt", "research command failed")
            return 1
    return None


def handle_simulate_provider(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "simulate-provider":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                simulate_provider_response,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research simulate-provider skipped safely: no workspace found")
                return 1

            safe_prompt_id = validate_run_id(args.prompt_packet_id)

            event_logger = EventLogger(ws / "events")

            result = simulate_provider_response(
                workspace_path=ws,
                prompt_packet_id=safe_prompt_id,
                provider=args.provider,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research simulate-provider", "invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json

                print(
                    json.dumps(
                        {"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."},
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print("research simulate-provider skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research simulate-provider", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research simulate-provider", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research simulate-provider", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_provider_response_created",
                "symbol": result["symbol"],
                "source_prompt_packet_id": result["source_prompt_packet_id"],
                "provider_response_id": result["provider_response_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Simulated provider response created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Provider: {result['provider']}")
            print(f"  Source Prompt Packet ID: {result['source_prompt_packet_id']}")
            print(f"  Provider Response ID: {result['provider_response_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    return None


def handle_review_response(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "review-response":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                review_provider_response,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research review-response skipped safely: no workspace found")
                return 1

            safe_response_id = validate_run_id(args.provider_response_id)

            event_logger = EventLogger(ws / "events")

            result = review_provider_response(
                workspace_path=ws,
                provider_response_id=safe_response_id,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research review-response", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research review-response", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research review-response", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research review-response", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_response_review_created",
                "symbol": result["symbol"],
                "source_provider_response_id": result["source_provider_response_id"],
                "response_review_id": result["response_review_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider response review created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Provider: {result['provider']}")
            print(f"  Source Provider Response ID: {result['source_provider_response_id']}")
            print(f"  Response Review ID: {result['response_review_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    return None


def handle_dossier(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import EventLogger
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "dossier":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                build_dossier,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research dossier skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)

            events_dir = ws / "events"
            event_logger = EventLogger(events_dir)

            result = build_dossier(
                workspace_path=ws,
                run_id=safe_run_id,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research dossier", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research dossier", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research dossier", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research dossier", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_dossier_created",
                "symbol": result["symbol"],
                "source_run_id": result["source_run_id"],
                "dossier_id": result["dossier_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Research dossier created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Source Run ID: {result['source_run_id']}")
            print(f"  Dossier ID: {result['dossier_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    return None


def handle_import_provider_response(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.events import generate_run_id
    from atlas_agent.research.errors import safe_research_session_error

    if args.command == "research" and args.research_command == "import-provider-response":
        try:
            from atlas_agent.research.sandbox_contracts import (
                artifact_sha256,
                sanitize_contract_text,
                validate_contract_lineage_id,
                validate_contract_symbol,
                validate_external_provider_response_payload,
            )
            from atlas_agent.research.session import (
                RESEARCH_ARTIFACT_SCHEMA_VERSION,
                RESEARCH_DIR,
                ResearchSessionError,
                find_sandbox_request_by_id,
                load_sandbox_request,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research import-provider-response skipped safely: no workspace found")
                return 1

            safe_sandbox_id = validate_run_id(args.sandbox_request_id)
            sandbox_path = find_sandbox_request_by_id(ws, safe_sandbox_id)
            if sandbox_path is None:
                raise ResearchSessionError("sandbox_request_not_found")
            sandbox = load_sandbox_request(sandbox_path, ws)

            file_path = args.file
            if not file_path.exists() or not file_path.is_file():
                raise ResearchSessionError("provider_response_file_not_found")
            if file_path.is_symlink():
                try:
                    resolved = file_path.resolve()
                    ws_resolved = ws.resolve()
                    resolved.relative_to(ws_resolved)
                except ValueError:
                    raise ResearchSessionError("artifact_path_not_allowed")

            try:
                import json
                raw_data: dict[str, Any] = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                raise ResearchSessionError("provider_response_malformed")

            summary = sanitize_contract_text(raw_data.get("summary", ""), 4000)
            sections = raw_data.get("sections", [])
            if not isinstance(sections, list):
                sections = []
            safe_sections = []
            for sec in sections:
                if isinstance(sec, dict):
                    safe_sections.append({
                        "title": sanitize_contract_text(str(sec.get("title", "")), 200),
                        "content": sanitize_contract_text(str(sec.get("content", "")), 4000),
                    })

            safety_checks = raw_data.get("safety_checks", [])
            if not isinstance(safety_checks, list):
                safety_checks = []
            safe_checks = []
            for chk in safety_checks:
                if isinstance(chk, dict):
                    safe_checks.append({
                        "name": sanitize_contract_text(str(chk.get("name", "")), 200),
                        "status": str(chk.get("status", "warn")),
                        "notes": sanitize_contract_text(str(chk.get("notes", "")), 1000),
                    })

            limitations = raw_data.get("limitations", [])
            if not isinstance(limitations, list):
                limitations = []
            safe_limitations = [sanitize_contract_text(str(l), 500) for l in limitations]

            symbol = validate_contract_symbol(sandbox.get("symbol", ""))
            prompt_packet_id = validate_contract_lineage_id(sandbox.get("prompt_packet_id", ""), "prompt_packet_id")
            source_run_id = validate_contract_lineage_id(sandbox.get("source_run_id", ""), "source_run_id")

            provider_response_id = generate_run_id()
            created_at = datetime.now(UTC)

            artifact_path_rel = f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json"
            artifact_path = ws / artifact_path_rel

            response_payload: dict[str, Any] = {
                "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                "artifact_type": "provider_response",
                "provider_response_id": provider_response_id,
                "source_sandbox_request_id": safe_sandbox_id,
                "source_prompt_packet_id": prompt_packet_id,
                "source_run_id": source_run_id,
                "created_at": created_at.isoformat(),
                "symbol": symbol,
                "mode": "paper",
                "provider": "external-local-import",
                "provider_status": "imported_untrusted",
                "response_summary": summary,
                "response_sections": safe_sections,
                "safety_checks": safe_checks,
                "limitations": safe_limitations,
                "artifact_path": artifact_path_rel,
            }

            validation = validate_external_provider_response_payload(response_payload)
            if not validation.valid:
                resp_warnings = validation.warnings + ["Imported provider response failed contract validation."]
            else:
                resp_warnings = validation.warnings

            response_payload["recommendation"] = validation.recommendation
            response_payload["redaction_summary"] = {"redacted_fragments_count": 0, "truncated": False}
            response_payload["warnings"] = resp_warnings
            response_payload["content_hash"] = artifact_sha256(response_payload)

            responses_dir = ws / RESEARCH_DIR / symbol / "provider_responses"
            responses_dir.mkdir(parents=True, exist_ok=True)

            artifact_path.write_text(json.dumps(response_payload, indent=2, sort_keys=True), encoding="utf-8")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research import-provider-response", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research import-provider-response", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_imported",
                "provider_response_id": provider_response_id,
                "source_sandbox_request_id": safe_sandbox_id,
                "artifact_path": artifact_path_rel,
                "recommendation": validation.recommendation,
                "warnings": resp_warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response imported: {provider_response_id}")
            print(f"  Source Sandbox: {safe_sandbox_id}")
            print(f"  Artifact: {artifact_path_rel}")
            print(f"  Recommendation: {validation.recommendation}")
        return 0
    return None



HANDLERS = {
    "check-artifacts": handle_check_artifacts,
    "dossier": handle_dossier,
    "evaluate": handle_evaluate,
    "import-provider-response": handle_import_provider_response,
    "list": handle_list,
    "market": handle_market,
    "plan": handle_plan,
    "prompt": handle_prompt,
    "review-response": handle_review_response,
    "run": handle_run,
    "show": handle_show,
    "simulate-provider": handle_simulate_provider,
    "summary": handle_summary,
    "timeline": handle_timeline,
    "verify": handle_verify,
}
