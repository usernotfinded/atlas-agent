# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/dashboard.py
# PURPOSE: CLI handler for `atlas dashboard` — renders the workspace snapshot to HTML.
# DEPS:    dashboard.collectors, dashboard.render
# ==============================================================================

"""CLI handler for `atlas dashboard`."""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext


def handle_dashboard(context: CLIContext) -> int | None:
    args = context.args
    config = context.config

    if args.command == "dashboard":
        from atlas_agent.dashboard.collectors import collect_dashboard_snapshot
        from atlas_agent.dashboard.render import render_dashboard_html, render_dashboard_markdown

        snapshot = collect_dashboard_snapshot(config, Path.cwd())

        if args.json:
            print(snapshot.model_dump_json(indent=2))
            return 0

        fmt = getattr(args, "format", "html")
        if fmt == "markdown":
            md = render_dashboard_markdown(snapshot)
            print(md)
            return 0

        dashboard_path = config.workspace_root / ".atlas" / "dashboard" / "index.html"
        render_dashboard_html(snapshot, dashboard_path)
        print(f"Dashboard generated: {dashboard_path}")

        if args.open:
            import webbrowser
            webbrowser.open(f"file://{dashboard_path.resolve()}")
        return 0
    return None

