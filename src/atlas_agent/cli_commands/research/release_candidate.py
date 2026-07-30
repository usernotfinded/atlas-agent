# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/release_candidate.py
# PURPOSE: CLI handlers for the research release-candidate flow — readiness and
#          cutover.
# DEPS:    research.release_candidate_readiness, .._cutover
# ==============================================================================

"""CLI handlers for `atlas research ...` subcommands."""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path


from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._envelope import print_json, research_envelope
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


@research_envelope("release-candidate-readiness")
def handle_release_candidate_readiness(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import create_release_candidate_readiness
    from atlas_agent import __version__
    result = create_release_candidate_readiness(ws, args.symbol, __version__)

    if args.json:
        print_json(result)
    else:
        print("Release candidate readiness report created")
        print(f"  ID: {result.get('release_candidate_readiness_report_id', '')}")
        print(f"  Symbol: {result.get('symbol', '')}")
        print(f"  Version: {result.get('version', '')}")
        print(f"  Readiness Status: {result.get('readiness_status', '')}")
        print(f"  Readiness Score: {result.get('readiness_score', 0)}")
        blockers = result.get("blockers", [])
        if blockers:
            print(f"  Blockers: {', '.join(blockers)}")
    return 0


@research_envelope("release-candidate-readiness-list")
def handle_release_candidate_readiness_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import iter_release_candidate_readiness_artifacts
    result = iter_release_candidate_readiness_artifacts(ws, symbol=args.symbol)

    if args.json:
        print_json({"ok": True, "status": "research_release_candidate_readiness_list", "items": result})
    else:
        print(f"Release candidate readiness reports: {len(result)}")
        for item in result:
            print(f"  {item.get('release_candidate_readiness_report_id', '')} | {item.get('symbol', '')} | {item.get('readiness_status', '')} | {item.get('readiness_score', 0)}")
    return 0


@research_envelope("release-candidate-readiness-show")
def handle_release_candidate_readiness_show(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import (
        find_release_candidate_readiness_by_id,
        load_release_candidate_readiness,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate readiness report not found.")
        return 1
    data = load_release_candidate_readiness(artifact_path, ws)

    if args.json:
        print_json(data)
    else:
        print("Release candidate readiness report")
        print(f"  ID: {data.get('release_candidate_readiness_report_id', '')}")
        print(f"  Symbol: {data.get('symbol', '')}")
        print(f"  Version: {data.get('version', '')}")
        print(f"  Status: {data.get('readiness_status', '')}")
        print(f"  Score: {data.get('readiness_score', 0)}")
        print(f"  Sandbox Only: {data.get('sandbox_only', True)}")
        print(f"  Paper First: {data.get('paper_first', True)}")
        print(f"  Offline Safe: {data.get('offline_safe', True)}")
    return 0


@research_envelope("release-candidate-readiness-validate")
def handle_release_candidate_readiness_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import (
        find_release_candidate_readiness_by_id,
        validate_release_candidate_readiness_artifact,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate readiness report not found.")
        return 1
    result = validate_release_candidate_readiness_artifact(artifact_path, ws)

    output = {
        "ok": result.valid,
        "status": "research_release_candidate_readiness_validated" if result.valid else "research_release_candidate_readiness_validation_failed",
        "valid": result.valid,
        "structurally_valid": result.structurally_valid,
        "readiness_valid": result.readiness_valid,
        "readiness_status": result.readiness_status,
        "blockers": result.blockers,
        "passed_checks": result.passed_checks,
        "failed_checks": result.failed_checks,
        "recommendation": result.recommendation,
        "warnings": result.warnings,
    }
    if args.json:
        print_json(output)
    else:
        print(f"Release candidate readiness validation: {'PASS' if result.valid else 'FAIL'}")
        print(f"  Passed: {result.passed_checks}")
        print(f"  Failed: {result.failed_checks}")
        print(f"  Recommendation: {result.recommendation}")
        if result.warnings:
            for w in result.warnings:
                print(f"  Warning: {w}")
    if args.strict and not result.valid:
        return 1
    return 0


@research_envelope("release-candidate-readiness-summary")
def handle_release_candidate_readiness_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import (
        find_release_candidate_readiness_by_id,
        summarize_release_candidate_readiness,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate readiness report not found.")
        return 1
    result = summarize_release_candidate_readiness(artifact_path, ws)

    if args.json:
        print_json(result)
    else:
        print("Release candidate readiness summary")
        print(f"  ID: {result.get('release_candidate_readiness_report_id', '')}")
        print(f"  Status: {result.get('readiness_status', '')}")
        print(f"  Score: {result.get('readiness_score', 0)}")
        print(f"  Checks: {result.get('total_checks', 0)} total, {result.get('passed_checks', 0)} passed, {result.get('failed_checks', 0)} failed")
        blockers = result.get("blockers", [])
        if blockers:
            print(f"  Blockers: {', '.join(blockers)}")
    return 0


@research_envelope("release-candidate-readiness-doctor")
def handle_release_candidate_readiness_doctor(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_readiness import (
        find_release_candidate_readiness_by_id,
        doctor_release_candidate_readiness,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate readiness report not found.")
        return 1
    result = doctor_release_candidate_readiness(artifact_path, ws)

    if args.json:
        print_json(result)
    else:
        print("Release candidate readiness doctor")
        print(f"  Valid: {result.get('valid', False)}")
        print(f"  Structurally Valid: {result.get('structurally_valid', False)}")
        print(f"  Readiness Valid: {result.get('readiness_valid', False)}")
        print(f"  Readiness Status: {result.get('readiness_status', '')}")
        print(f"  Passed: {result.get('passed_checks', 0)}")
        print(f"  Failed: {result.get('failed_checks', 0)}")
        print(f"  Recommendation: {result.get('recommendation', '')}")
        if result.get("mismatched_fields"):
            print(f"  Mismatched Fields: {', '.join(result['mismatched_fields'])}")
        if result.get("blockers"):
            print(f"  Blockers: {', '.join(result['blockers'])}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  Warning: {w}")
    return 0


@research_envelope("release-candidate-cutover-dry-run")
def handle_release_candidate_cutover_dry_run(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_cutover import create_release_candidate_cutover_dry_run
    result = create_release_candidate_cutover_dry_run(ws, args.target_version)

    if args.json:
        print_json(result)
    else:
        print("Release candidate cutover dry run")
        print(f"  Status: {result.get('cutover_status', '')}")
        print(f"  Target: {result.get('target_version', '')}")
        print(f"  Score: {result.get('cutover_score', 0)}")
        if result.get("blockers"):
            print(f"  Blockers: {', '.join(result['blockers'])}")
        print("  Dry run only: no tag, push, or publish executed.")
    return 0 if result.get("ok") else 1


@research_envelope("release-candidate-cutover-dry-run-list")
def handle_release_candidate_cutover_dry_run_list(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_cutover import iter_release_candidate_cutover_artifacts

    # This handler had no `ResearchSessionError` clause: everything landed on
    # `except Exception` as `research_error`. Keeping that clause inside the body
    # preserves it -- letting the envelope handle it would map a
    # `ResearchSessionError` to a specific status instead, changing the envelope.
    try:
        result = iter_release_candidate_cutover_artifacts(ws)
    except Exception:
        if args.json:
            _research_error_json("research_error", "Research command failed.")
        else:
            _research_error_text("research release-candidate-cutover-dry-run-list", "research command failed")
        return 1

    if args.json:
        print_json({"ok": True, "status": "research_release_candidate_cutover_dry_run_list", "items": result})
    else:
        print(f"Release candidate cutover dry runs: {len(result)}")
        for item in result:
            print(f"  {item.get('release_candidate_cutover_dry_run_id', '')} | {item.get('target_version', '')} | {item.get('cutover_status', '')} | {item.get('cutover_score', 0)}")
    return 0


@research_envelope("release-candidate-cutover-dry-run-validate")
def handle_release_candidate_cutover_dry_run_validate(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_cutover import (
        find_release_candidate_cutover_by_id,
        validate_release_candidate_cutover_artifact,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate cutover dry-run report not found.")
        return 1
    result = validate_release_candidate_cutover_artifact(artifact_path, ws)

    output = {
        "ok": result.valid,
        "status": "research_release_candidate_cutover_dry_run_validated" if result.valid else "research_release_candidate_cutover_dry_run_validation_failed",
        "valid": result.valid,
        "structurally_valid": result.structurally_valid,
        "cutover_valid": result.cutover_valid,
        "cutover_status": result.cutover_status,
        "blockers": result.blockers,
        "passed_checks": result.passed_checks,
        "failed_checks": result.failed_checks,
        "recommendation": result.recommendation,
        "warnings": result.warnings,
        "mismatched_fields": result.mismatched_fields,
    }
    if args.json:
        print_json(output)
    else:
        print(f"Release candidate cutover dry-run validation: {'PASS' if result.valid else 'FAIL'}")
        print(f"  Status: {result.cutover_status}")
        if result.blockers:
            print(f"  Blockers: {', '.join(result.blockers)}")
    if args.strict and not result.valid:
        return 1
    return 0


@research_envelope("release-candidate-cutover-dry-run-summary")
def handle_release_candidate_cutover_dry_run_summary(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_cutover import (
        find_release_candidate_cutover_by_id,
        summarize_release_candidate_cutover,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate cutover dry-run report not found.")
        return 1
    result = summarize_release_candidate_cutover(artifact_path, ws)

    if args.json:
        print_json(result)
    else:
        print("Release candidate cutover dry-run summary")
        print(f"  Status: {result.get('cutover_status', '')}")
        print(f"  Target: {result.get('target_version', '')}")
        print(f"  Score: {result.get('cutover_score', 0)}")
        if result.get("blockers"):
            print(f"  Blockers: {', '.join(result['blockers'])}")
    return 0


@research_envelope("release-candidate-cutover-dry-run-doctor")
def handle_release_candidate_cutover_dry_run_doctor(context: CLIContext, ws: Path) -> int:
    args = context.args
    from atlas_agent.research.release_candidate_cutover import (
        doctor_release_candidate_cutover,
        find_release_candidate_cutover_by_id,
    )
    from atlas_agent.research.session import validate_run_id
    safe_id = validate_run_id(args.report_id)
    artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
    if artifact_path is None:
        if args.json:
            print_json({"ok": False, "status": "report_not_found"})
        else:
            print("Release candidate cutover dry-run report not found.")
        return 1
    result = doctor_release_candidate_cutover(artifact_path, ws)

    if args.json:
        print_json(result)
    else:
        print("Release candidate cutover dry-run doctor")
        print(f"  Valid: {result.get('valid', False)}")
        print(f"  Status: {result.get('cutover_status', '')}")
        if result.get("blockers"):
            print(f"  Blockers: {', '.join(result['blockers'])}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  Warning: {w}")
    return 0



HANDLERS = {
    "release-candidate-cutover-dry-run": handle_release_candidate_cutover_dry_run,
    "release-candidate-cutover-dry-run-doctor": handle_release_candidate_cutover_dry_run_doctor,
    "release-candidate-cutover-dry-run-list": handle_release_candidate_cutover_dry_run_list,
    "release-candidate-cutover-dry-run-summary": handle_release_candidate_cutover_dry_run_summary,
    "release-candidate-cutover-dry-run-validate": handle_release_candidate_cutover_dry_run_validate,
    "release-candidate-readiness": handle_release_candidate_readiness,
    "release-candidate-readiness-doctor": handle_release_candidate_readiness_doctor,
    "release-candidate-readiness-list": handle_release_candidate_readiness_list,
    "release-candidate-readiness-show": handle_release_candidate_readiness_show,
    "release-candidate-readiness-summary": handle_release_candidate_readiness_summary,
    "release-candidate-readiness-validate": handle_release_candidate_readiness_validate,
}
