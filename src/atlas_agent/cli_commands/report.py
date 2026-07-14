# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/report.py
# PURPOSE: CLI handler for `atlas report` — daily, weekly and ad-hoc reports from
#          local data.
# DEPS:    reports.daily, reports.weekly, reports.adhoc
# ==============================================================================

"""CLI handler for `atlas report`."""

# --- IMPORTS ---
from __future__ import annotations

import sys

from pathlib import Path

from atlas_agent.cli_context import CLIContext


def handle_report(context: CLIContext) -> int | None:
    args = context.args
    import json
    from atlas_agent.backtest import render_json_report
    from atlas_agent.backtest import render_markdown_report
    from atlas_agent.reports.daily import generate_daily_report
    from atlas_agent.reports.generator import generate_report
    from atlas_agent.reports.renderers import render_json_string
    from atlas_agent.reports.renderers import render_markdown

    if args.command == "report":
        if args.report_command == "daily":
            print(generate_daily_report())
            return 0
        if args.report_command == "generate":
            run_id = getattr(args, "run_id", None)
            report_type = getattr(args, "type", "daily")
            fmt = getattr(args, "format", "text")
            output = getattr(args, "output", "stdout")

            # Legacy backtest-specific report path
            if run_id:
                result_path = Path(".atlas/backtests") / run_id / "result.json"
                if not result_path.exists():
                    print(f"Error: No backtest result found for run_id '{run_id}'", file=sys.stderr)
                    return 1
                import json as _json
                data = _json.loads(result_path.read_text(encoding="utf-8"))
                from atlas_agent.backtest.models import BacktestResult as _BR
                loaded_result = _BR.model_validate(data)

                if fmt == "json":
                    content = json.dumps(render_json_report(loaded_result), indent=2, sort_keys=True, default=str)
                elif fmt == "markdown":
                    content = render_markdown_report(loaded_result)
                else:
                    content = render_markdown_report(loaded_result)

                if output == "stdout":
                    print(content)
                else:
                    out_path = Path(output)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
                    print(f"Report written to: {out_path}")
                return 0

            # New local report generator path
            report_data = generate_report(
                report_type,  # type: ignore[arg-type]
                workspace=".",
                output_format="json" if fmt == "json" else "markdown",
            )
            if fmt == "json":
                content = render_json_string(report_data)
            else:
                content = render_markdown(report_data)

            if output == "stdout":
                print(content)
            else:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"Report written to: {out_path}")
            return 0
        print("Error: Use 'atlas report --help' for usage.")
        return 1
    return None

