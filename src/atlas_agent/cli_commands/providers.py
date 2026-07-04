"""CLI handler for `atlas providers`."""
from __future__ import annotations

import sys

from datetime import UTC
from datetime import datetime
from pathlib import Path

from atlas_agent.cli_context import CLIContext


def handle_providers(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.cli_io import display_path
    from atlas_agent.cli_io import emit_cli_error
    from atlas_agent.cli_io import emit_cli_success

    if args.command == "providers" and args.providers_command == "list":
        print("openai_compatible, anthropic, openrouter")
        return 0
    if args.command == "providers" and args.providers_command == "capability-inventory":
        import json
        from atlas_agent.providers.provider_readiness import generate_capability_inventory
        try:
            inventory = generate_capability_inventory()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                if not getattr(args, "json", False):
                    print(f"Generated capability inventory at {display_path(args.output)}")
            if getattr(args, "json", False):
                return emit_cli_success("atlas providers capability-inventory", {"inventory": inventory})
            elif not args.output:
                print(json.dumps(inventory, indent=2, sort_keys=True))
            return 0
        except Exception as e:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers capability-inventory", "capability_inventory_error", str(e))
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.command == "providers" and args.providers_command == "readiness-check":
        import json
        from atlas_agent.providers.provider_readiness import evaluate_provider_readiness
        from atlas_agent.providers.provider_preflight import PreflightValidationError
        try:
            report = evaluate_provider_readiness(
                provider_id=args.provider,
                model_id=args.model,
                purpose=args.purpose,
                max_context_chars=args.max_context_chars,
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                if not getattr(args, "json", False):
                    print(f"Generated readiness report at {display_path(args.output)}")
            if getattr(args, "json", False):
                return emit_cli_success("atlas providers readiness-check", {"report": report})
            elif not args.output:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers readiness-check", "preflight_validation_error", str(exc))
            print(f"Validation error: {exc}", file=sys.stderr)
            return 2
        except Exception as e:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers readiness-check", "readiness_check_error", str(e))
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.command == "providers" and args.providers_command == "evidence-index":
        if args.evidence_command == "build":
            from atlas_agent.providers.provider_evidence_index import build_provider_evidence_index
            try:
                index = build_provider_evidence_index(root=args.root, output=args.output)
                # Check for findings (invalid or unsafe artifacts)
                if index.get("findings"):
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index build", {"index": index, "status": "findings"})
                    print(f"Provider evidence index built but contains invalid artifacts.")
                    if args.output:
                        print(f"Index written to {display_path(args.output)}")
                    return 1
                else:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index build", {"index": index, "status": "success"})
                    if args.output:
                        print(f"Provider evidence index written to {display_path(args.output)}")
                    return 0
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index build", "evidence_index_error", str(e))
                print(f"Provider evidence index build failed: {e}", file=sys.stderr)
                return 2
        elif args.evidence_command == "inspect":
            from atlas_agent.providers.provider_evidence_index import inspect_provider_evidence_index, EvidenceIndexError
            try:
                data = inspect_provider_evidence_index(args.index_path)
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index inspect", {"index": data, "status": "valid"})
                print("Provider evidence index is valid.")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index inspect", "inspection_error", str(e))
                print(f"Provider evidence index inspection failed: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index inspect", "inspection_error", str(e))
                print(f"Provider evidence index inspection failed: {e}", file=sys.stderr)
                return 1
        elif args.evidence_command == "report":
            from atlas_agent.providers.provider_evidence_index import generate_provider_evidence_report, EvidenceIndexError
            try:
                result = generate_provider_evidence_report(args.index_path, output=args.output)
                is_valid = result.get("is_valid", False)
                if not is_valid:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index report", {"report_generated": True, "status": "unsafe_or_invalid_index", "findings": result.get("error_message")})
                    print(f"Provider evidence report generated to {display_path(args.output)}, but index was invalid or unsafe.")
                    return 1
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index report", {"report_generated": True, "status": "valid"})
                print(f"Provider evidence report written to {display_path(args.output)}")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index report", "report_generation_error", str(e))
                print(f"Provider evidence report generation failed: {e}", file=sys.stderr)
                return 2
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index report", "report_generation_error", str(e))
                print(f"Provider evidence report generation failed: {e}", file=sys.stderr)
                return 2
        elif args.evidence_command == "export-summary":
            from atlas_agent.providers.provider_evidence_index import export_provider_evidence_summary, EvidenceIndexError
            try:
                summary = export_provider_evidence_summary(args.index_path, output=args.output)
                is_valid = summary.get("valid", False)
                if not is_valid:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index export-summary", {"summary_exported": True, "status": "unsafe_or_invalid_index"})
                    print(f"Provider evidence summary exported to {display_path(args.output)}, but index was invalid or unsafe.")
                    return 1
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index export-summary", {"summary_exported": True, "status": "valid"})
                print(f"Provider evidence summary exported to {display_path(args.output)}")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index export-summary", "summary_export_error", str(e))
                print(f"Provider evidence summary export failed: {e}", file=sys.stderr)
                return 2
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index export-summary", "summary_export_error", str(e))
                print(f"Provider evidence summary export failed: {e}", file=sys.stderr)
                return 2
    if args.command == "providers" and args.providers_command == "validate-preflight":
        import json
        from atlas_agent.providers.provider_preflight import (
            validate_call_plan_artifact,
            PreflightValidationError,
        )
        artifact_path = Path(args.artifact_path)
        if not artifact_path.exists():
            print(f"File not found: {artifact_path}", file=sys.stderr)
            return 2
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers validate-preflight",
                    code="json_parse_error",
                    message=f"Invalid JSON: {exc}"
                )
            print(f"Invalid JSON: {exc}", file=sys.stderr)
            return 2

        try:
            validate_call_plan_artifact(artifact)
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers validate-preflight",
                    code="preflight_validation_error",
                    message=str(exc)
                )
            print(f"Validation failed: {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            return emit_cli_success("atlas providers validate-preflight", {"valid": True})
        print("Artifact is valid and safe.")
        return 0
    if args.command == "providers" and args.providers_command == "preflight":
        import json
        from atlas_agent.providers.provider_preflight import (
            generate_call_plan_artifact,
            PreflightValidationError,
        )
        try:
            artifact = generate_call_plan_artifact(
                provider_id=args.provider,
                model_id=args.model,
                purpose=args.purpose,
                max_context_chars=args.max_context_chars,
            )
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers preflight",
                    code="preflight_validation_error",
                    message=str(exc)
                )
            print(f"Validation error: {exc}", file=sys.stderr)
            return 2

        if args.output:
            out_path = args.output
        else:
            now_for_path = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out_path = Path("artifacts/provider_preflight") / f"{now_for_path}-call-plan.json"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        if getattr(args, "json", False):
            return emit_cli_success("atlas providers preflight", {"artifact_path": str(out_path)})

        print(f"Generated dry-run call-plan artifact at {display_path(out_path)}")
        return 0
    return None

