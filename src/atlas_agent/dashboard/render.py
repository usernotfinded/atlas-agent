# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    dashboard/render.py
# PURPOSE: Renders a dashboard snapshot to HTML.
# DEPS:    dashboard.models, html.escape
#
# NOTE:    Everything rendered here originates from files the AGENT wrote — journal
#          entries, reflections, model reasoning. That is untrusted, model-generated
#          content going into a page, which is why `escape` is not optional.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

from atlas_agent.dashboard.models import DashboardSnapshot


# ==============================================================================
# RENDERING HELPERS
# ==============================================================================

def _text(value: Any, default: str = "No data available") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return text if text else default


def _html(value: Any, default: str = "No data available") -> str:
    return escape(_text(value, default))


def _status_class(status: Any) -> str:
    text = str(status or "unknown").lower().replace("_", "-")
    # Normalize dashboard/report-specific statuses to consistent badge classes.
    if text.startswith("invalid:"):
        return "failed"
    text = {
        "completed": "success",
        "valid": "success",
        "unreadable": "failed",
        "legacy": "partial",
    }.get(text, text)
    allowed = {
        "active",
        "compromised",
        "enabled",
        "expired",
        "failed",
        "healthy",
        "locked-down",
        "missing",
        "normal",
        "pass",
        "partial",
        "running",
        "success",
        "unknown",
    }
    return text if text in allowed else "unknown"


def _badge(status: Any, label: Any | None = None) -> str:
    visible = _html(label if label is not None else status, "unknown")
    return f'<span class="status status-{_status_class(status)}">{visible}</span>'


def _row(label: str, value: Any, *, status: Any | None = None, default: str = "No data available") -> str:
    rendered = _badge(status, value) if status is not None else f'<span class="stat-value">{_html(value, default)}</span>'
    return f"""
                    <div class="stat-row">
                        <span class="stat-label">{escape(label)}</span>
                        {rendered}
                    </div>"""


def _empty_if_unavailable(
    available: bool,
    message: str = "No data available",
) -> str:
    if available:
        return ""
    return f'<p class="empty-state">{escape(message)}</p>'


def _status_breakdown(items: dict[str, int]) -> str:
    if not items:
        return '<p class="empty-state">No data available</p>'
    rows = []
    for status, count in sorted(items.items()):
        rows.append(
            f"""
                    <div class="stat-row compact">
                        <span class="stat-label">{_html(status)}</span>
                        <span class="stat-value">{_html(count)}</span>
                    </div>"""
        )
    return "\n".join(rows)


def _list_section(items: list[str], empty: str = "No data available") -> str:
    if not items:
        return f'<p class="empty-state">{escape(empty)}</p>'
    rendered = "\n".join(f"                    <li>{_html(item)}</li>" for item in items)
    return f"""
                <ul class="plain-list">
{rendered}
                </ul>"""


def _diagnostics_html(diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return '<p class="empty-state">No diagnostics available.</p>'
    if diagnostics.get("redacted"):
        return '<p class="empty-state">Diagnostics redacted.</p>'
    return f'<pre>{escape(json.dumps(diagnostics, indent=2))}</pre>'


def _diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return "No diagnostics available."
    if diagnostics.get("redacted"):
        return "Diagnostics redacted."
    return f"```json\n{json.dumps(diagnostics, indent=2)}\n```"


def _markdown_cell(value: Any, default: str = "N/A") -> str:
    return _text(value, default).replace("|", r"\|").replace("\n", " ")


def _backtest_summary_html(snapshot: DashboardSnapshot) -> str:
    backtests = snapshot.backtests
    if not backtests.available:
        return _empty_if_unavailable(
            False,
            "No backtest runs found. Run a local backtest to populate this section.",
        )

    rows = [
        ("Total runs", backtests.total_runs, None),
        ("Recent runs", backtests.recent_count, None),
        ("Latest run", backtests.latest_run_id, None),
        ("Latest symbol", backtests.latest_symbol, None),
        ("Latest return pct", backtests.latest_return_pct, None),
        ("Latest status", backtests.latest_status, backtests.latest_status),
        ("Latest schema version", backtests.latest_schema_version, None),
        (
            "Latest validation status",
            backtests.latest_validation_status,
            backtests.latest_validation_status,
        ),
    ]
    rendered_rows = []
    for label, value, status in rows:
        rendered_value = _badge(status, value) if status is not None else _html(value)
        rendered_rows.append(
            f"""
                    <tr>
                        <th scope="row">{escape(label)}</th>
                        <td>{rendered_value}</td>
                    </tr>"""
        )
    return f"""
                <table class="summary-table">
                    <thead>
                        <tr>
                            <th scope="col">Metric</th>
                            <th scope="col">Value</th>
                        </tr>
                    </thead>
                    <tbody>
{''.join(rendered_rows)}
                    </tbody>
                </table>"""


def _backtest_summary_markdown(snapshot: DashboardSnapshot) -> list[str]:
    backtests = snapshot.backtests
    if not backtests.available:
        return [
            "No backtest runs found. Run a local backtest to populate this section.",
        ]

    rows = [
        ("Total Runs", backtests.total_runs),
        ("Recent Runs", backtests.recent_count),
        ("Latest Run", backtests.latest_run_id),
        ("Latest Symbol", backtests.latest_symbol),
        ("Latest Return Pct", backtests.latest_return_pct),
        ("Latest Status", backtests.latest_status),
        ("Latest Schema Version", backtests.latest_schema_version),
        ("Latest Validation Status", backtests.latest_validation_status),
    ]
    lines = [
        "| Metric | Value |",
        "| :--- | ---: |",
    ]
    lines.extend(
        f"| {_markdown_cell(label)} | {_markdown_cell(value)} |"
        for label, value in rows
    )
    return lines


def render_dashboard_html(snapshot: DashboardSnapshot, output_path: Path) -> Path:
    """
    Render DashboardSnapshot to a static HTML file.
    """
    ks = snapshot.kill_switch_summary
    ks_mode = ks.get("mode", "UNKNOWN")
    ks_status = ks.get("status", "Unknown")
    
    port = snapshot.portfolio_summary
    orders = snapshot.open_orders_summary
    audit = snapshot.audit_summary
    
    mode_label = snapshot.mode if snapshot.mode != "unknown" else "paper_or_sandbox"
    safety_status = "locked_down" if snapshot.safety.kill_switch_active else "normal"
    system_health = snapshot.system_health
    portfolio = snapshot.portfolio
    backtests = snapshot.backtests
    reports = snapshot.reports
    reflections = snapshot.reflections
    skills = snapshot.skills
    learning = snapshot.learning
    audit_model = snapshot.audit
    safety = snapshot.safety

    system_checks = ""
    if system_health.checks:
        rendered_checks = []
        for check in system_health.checks:
            check_status = check.get("status", "unknown")
            rendered_checks.append(
                f"""
                    <li>
                        {_badge(check_status)}
                        <span>{_html(check.get("id", "unknown"))}: {_html(check.get("message", ""))}</span>
                    </li>"""
            )
        system_checks = f"""
                <h3>Checks</h3>
                <ul class="check-list">
{''.join(rendered_checks)}
                </ul>"""
    else:
        system_checks = '<p class="empty-state">No data available</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Atlas Agent Dashboard</title>
    <style>
        :root {{ color-scheme: light; --bg: #f7f7f4; --panel: #ffffff; --ink: #1d2525; --muted: #5d6866; --line: #d8ded9; --accent: #275c56; --warn: #7a4d00; --warn-bg: #fff7df; --danger: #8b1e24; --danger-bg: #fff0f0; --ok: #1f6b3a; --ok-bg: #ecf8ef; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--ink); line-height: 1.5; margin: 0; }}
        .container {{ max-width: 1240px; margin: 0 auto; padding: 2rem; }}
        header {{ border-bottom: 1px solid var(--line); padding-bottom: 1rem; margin-bottom: 1.5rem; }}
        .header-top {{ display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }}
        h1 {{ margin: 0; font-size: 1.75rem; color: var(--accent); letter-spacing: 0; }}
        h2 {{ margin: 0 0 1rem 0; font-size: 1.05rem; color: var(--ink); }}
        h3 {{ margin: 1rem 0 0.5rem 0; font-size: 0.95rem; color: var(--muted); }}
        .timestamp, .workspace, .meta {{ color: var(--muted); font-size: 0.86rem; }}
        .workspace {{ overflow-wrap: anywhere; margin-top: 0.2rem; }}
        .meta-bar {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }}
        .pill {{ display: inline-flex; align-items: center; min-height: 1.75rem; padding: 0.2rem 0.6rem; border: 1px solid var(--line); border-radius: 999px; background: #eef3ef; color: var(--ink); font-size: 0.82rem; font-weight: 650; }}
        .banner {{ border: 1px solid var(--line); border-left: 5px solid var(--accent); background: var(--panel); border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }}
        .banner strong {{ display: block; margin-bottom: 0.4rem; }}
        .banner p {{ margin: 0.25rem 0; color: var(--muted); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; align-items: start; }}
        .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1rem; min-width: 0; }}
        .card.wide {{ grid-column: 1 / -1; }}
        .status {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; }}
        .status-success, .status-active, .status-healthy, .status-pass, .status-normal, .status-enabled {{ background: var(--ok-bg); color: var(--ok); }}
        .status-failed, .status-missing, .status-expired, .status-compromised, .status-locked-down {{ background: var(--danger-bg); color: var(--danger); }}
        .status-running, .status-partial {{ background: var(--warn-bg); color: var(--warn); }}
        .status-unknown {{ background: #eef0f0; color: var(--muted); }}
        .stat-row {{ display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        .stat-row.compact {{ margin-bottom: 0.25rem; }}
        .stat-label {{ color: var(--muted); padding-right: 1rem; }}
        .stat-value {{ font-weight: 500; }}
        .empty-state {{ margin: 0.25rem 0 0; color: var(--muted); font-style: italic; }}
        .plain-list, .check-list {{ margin: 0; padding-left: 1.1rem; }}
        .plain-list li, .check-list li {{ margin: 0.35rem 0; }}
        .check-list li {{ display: flex; gap: 0.5rem; align-items: baseline; }}
        .summary-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; font-variant-numeric: tabular-nums; }}
        .summary-table th, .summary-table td {{ border-bottom: 1px solid var(--line); padding: 0.45rem 0; }}
        .summary-table thead th {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; }}
        .summary-table th:first-child {{ text-align: left; padding-right: 1rem; }}
        .summary-table th:last-child, .summary-table td:last-child {{ text-align: right; }}
        .summary-table tbody th {{ color: var(--muted); font-weight: 400; }}
        pre {{ background: #f1f3f1; border: 1px solid var(--line); padding: 0.75rem; border-radius: 6px; font-size: 0.78rem; overflow-x: auto; color: var(--ink); }}
        footer {{ margin-top: 1.5rem; color: var(--muted); font-size: 0.9rem; }}
        @media (max-width: 720px) {{ .container {{ padding: 1rem; }} .header-top {{ display: block; }} .timestamp {{ margin-top: 0.75rem; }} .stat-row {{ display: block; }} .stat-label {{ display: block; padding-right: 0; }} }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <div>
                    <h1>Atlas Agent Dashboard</h1>
                    <div class="workspace">Workspace: {_html(snapshot.workspace)}</div>
                </div>
                <div class="timestamp">
                    <div>Generated: {_html(snapshot.generated_at)}</div>
                    <div>Export timestamp: {_html(snapshot.generated_at)}</div>
                </div>
            </div>
            <div class="meta-bar" aria-label="Dashboard mode indicators">
                <span class="pill">dashboard: {_html(snapshot.dashboard_mode)}</span>
                <span class="pill">local</span>
                <span class="pill">mode: {_html(mode_label)}</span>
                <span class="pill">execution surface: paper_or_sandbox</span>
            </div>
        </header>

        <section class="banner" aria-labelledby="safety-status">
            <strong id="safety-status">Safety status: {_html(safety_status)}</strong>
            <p>This dashboard is read-only.</p>
            <p>This dashboard does not execute trades.</p>
            <p>This dashboard does not call providers or brokers.</p>
            <p>This dashboard is not financial advice.</p>
        </section>

        <div class="grid">
            <section class="card wide" aria-labelledby="system-health-heading">
                <h2 id="system-health-heading">System Health</h2>
                {_row("Available", system_health.available)}
                {_row("Configured", snapshot.configured)}
                {_row("Workspace initialized", system_health.workspace_initialized)}
                {_row("Config readable", system_health.config_readable)}
                {_row("Ready for backtesting", system_health.ready_for_backtesting)}
                {_row("Ready for paper agentic review", system_health.ready_for_paper_agentic)}
                {_row("Ready for live", system_health.ready_for_live)}
{system_checks}
            </section>

            <section class="card" aria-labelledby="portfolio-heading">
                <h2 id="portfolio-heading">Portfolio Summary</h2>
                {_empty_if_unavailable(portfolio.available, "No local portfolio snapshot found.")}
                {_row("Cash", portfolio.cash)}
                {_row("Equity", portfolio.equity)}
                {_row("Positions", portfolio.positions_count)}
                {_row("Primary symbol", portfolio.symbol)}
            </section>

            <section class="card" aria-labelledby="backtests-heading">
                <h2 id="backtests-heading">Backtest Summary</h2>
                {_backtest_summary_html(snapshot)}
            </section>

            <section class="card" aria-labelledby="reports-heading">
                <h2 id="reports-heading">Report Summary</h2>
                {_empty_if_unavailable(reports.available, "No local report exports found.")}
                {_row("Report count", reports.report_count)}
                {_row("Latest type", reports.latest_report_type)}
                {_row("Latest generated", reports.latest_generated_at)}
            </section>

            <section class="card" aria-labelledby="reflections-heading">
                <h2 id="reflections-heading">Reflection Summary</h2>
                {_empty_if_unavailable(reflections.available, "No local reflection artifacts found.")}
                {_row("Total reflections", reflections.total_count)}
                <h3>Status breakdown</h3>
                {_status_breakdown(reflections.by_status)}
            </section>

            <section class="card" aria-labelledby="skills-heading">
                <h2 id="skills-heading">Skills Summary</h2>
                {_empty_if_unavailable(skills.available, "No local skill candidates or library entries found.")}
                {_row("Skill candidates", skills.candidate_count)}
                {_row("Library entries", skills.library_count)}
                <h3>Candidate status breakdown</h3>
                {_status_breakdown(skills.by_status)}
            </section>

            <section class="card" aria-labelledby="learning-heading">
                <h2 id="learning-heading">Learning Summary</h2>
                {_empty_if_unavailable(learning.available, "No local learning suggestions found.")}
                {_row("Suggestions", learning.suggestion_count)}
                <h3>Suggestion status breakdown</h3>
                {_status_breakdown(learning.by_status)}
            </section>

            <section class="card" aria-labelledby="audit-events-heading">
                <h2 id="audit-events-heading">Audit / Event Summary</h2>
                {_empty_if_unavailable(audit_model.available, "No local audit events found.")}
                {_row("Recent events", audit_model.recent_events)}
                {_row("Risk approved", audit_model.recent_risk_approved)}
                {_row("Risk rejected", audit_model.recent_risk_rejected)}
                {_row("Backtests completed", audit_model.recent_backtest_completed)}
                {_row("Backtests failed", audit_model.recent_backtest_failed)}
                {_row("Manifest integrity", audit.get("integrity", "unknown"), status=audit.get("integrity", "unknown"))}
            </section>

            <section class="card" aria-labelledby="safety-heading">
                <h2 id="safety-heading">Safety Status</h2>
                {_row("Kill switch mode", safety.kill_switch_mode, status=safety.kill_switch_mode)}
                {_row("Kill switch active", safety.kill_switch_active)}
                {_row("Legacy kill switch mode", ks_mode)}
                {_row("Legacy kill switch status", ks_status)}
                {_row("Heartbeat", safety.heartbeat_status, status=safety.heartbeat_status)}
                {_row("Last heartbeat", snapshot.heartbeat_summary.last_updated)}
                {_row("Live trading enabled", safety.live_trading_enabled)}
                {_row("Live submit enabled", safety.live_submit_enabled)}
            </section>

            <section class="card" aria-labelledby="provider-broker-heading">
                <h2 id="provider-broker-heading">Provider / Broker Sync Status</h2>
                {_row("Provider summary", snapshot.provider_summary.message)}
                {_row("Provider status", snapshot.provider_summary.status, status=snapshot.provider_summary.status)}
                {_row("Broker sync status", snapshot.broker_sync_summary.status, status=snapshot.broker_sync_summary.status)}
                {_row("Broker sync positions", port.get("position_count", 0))}
                {_row("Open orders", orders.get("order_count", 0))}
                {_row("Last broker sync", snapshot.broker_sync_summary.last_updated)}
            </section>

            <section class="card" aria-labelledby="warnings-heading" role="status">
                <h2 id="warnings-heading">Warnings</h2>
                {_list_section(snapshot.warnings, "No dashboard warnings.")}
            </section>

            <section class="card" aria-labelledby="missing-data-heading" role="status">
                <h2 id="missing-data-heading">Missing Data</h2>
                {_list_section(snapshot.missing_data, "No missing data detected.")}
            </section>

            <section class="card wide" aria-labelledby="diagnostics-heading">
                <h2 id="diagnostics-heading">Recent Diagnostics</h2>
                {_diagnostics_html(snapshot.diagnostics)}
            </section>
        </div>

        <footer>
            Research-only local dashboard. It is not a trading interface, not financial advice, and contains no execution controls.
        </footer>
    </div>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def render_dashboard_markdown(snapshot: DashboardSnapshot) -> str:
    """Render DashboardSnapshot as a Markdown summary."""
    lines: list[str] = []
    lines.append("# Atlas Agent Dashboard")
    lines.append("")
    lines.append(f"**Workspace:** {snapshot.workspace}")
    lines.append(f"**Generated:** {snapshot.generated_at}")
    lines.append(f"**Export Timestamp:** {snapshot.generated_at}")
    mode_label = snapshot.mode if snapshot.mode != "unknown" else "paper_or_sandbox"
    lines.append(f"**Mode:** {mode_label}")
    lines.append(f"**Dashboard Mode:** {snapshot.dashboard_mode}")
    lines.append("")

    lines.append("## Safety Notice")
    lines.append("")
    lines.append("- This dashboard is read-only.")
    lines.append("- This dashboard does not execute trades.")
    lines.append("- This dashboard does not call providers or brokers.")
    lines.append("- This dashboard is not financial advice.")
    lines.append("")

    if snapshot.warnings:
        lines.append("## Warnings")
        for warning in snapshot.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## System Health")
    sh = snapshot.system_health
    lines.append(f"- **Available:** {sh.available}")
    lines.append(f"- **Workspace Initialized:** {sh.workspace_initialized}")
    lines.append(f"- **Config Readable:** {sh.config_readable}")
    lines.append(f"- **Ready for Backtesting:** {sh.ready_for_backtesting}")
    lines.append(f"- **Ready for Paper Agentic:** {sh.ready_for_paper_agentic}")
    lines.append(f"- **Ready for Live:** {sh.ready_for_live}")
    if sh.checks:
        lines.append("- **Checks:**")
        for check in sh.checks:
            lines.append(f"  - [{check.get('status', '?')}] {check.get('id', '?')}: {check.get('message', '')}")
    lines.append("")

    lines.append("## Portfolio")
    pf = snapshot.portfolio
    lines.append(f"- **Available:** {pf.available}")
    lines.append(f"- **Cash:** {pf.cash if pf.cash is not None else 'N/A'}")
    lines.append(f"- **Equity:** {pf.equity if pf.equity is not None else 'N/A'}")
    lines.append(f"- **Positions:** {pf.positions_count}")
    lines.append("")

    lines.append("## Backtests")
    lines.extend(_backtest_summary_markdown(snapshot))
    lines.append("")

    lines.append("## Reports")
    rp = snapshot.reports
    lines.append(f"- **Available:** {rp.available}")
    lines.append(f"- **Report Count:** {rp.report_count}")
    lines.append(f"- **Latest Type:** {rp.latest_report_type or 'N/A'}")
    lines.append("")

    lines.append("## Reflections")
    rf = snapshot.reflections
    lines.append(f"- **Available:** {rf.available}")
    lines.append(f"- **Total Count:** {rf.total_count}")
    if rf.by_status:
        lines.append("- **By Status:**")
        for status, count in rf.by_status.items():
            lines.append(f"  - {status}: {count}")
    lines.append("")

    lines.append("## Skills")
    sk = snapshot.skills
    lines.append(f"- **Available:** {sk.available}")
    lines.append(f"- **Candidates:** {sk.candidate_count}")
    lines.append(f"- **Library:** {sk.library_count}")
    if sk.by_status:
        lines.append("- **By Status:**")
        for status, count in sk.by_status.items():
            lines.append(f"  - {status}: {count}")
    lines.append("")

    lines.append("## Learning Suggestions")
    lr = snapshot.learning
    lines.append(f"- **Available:** {lr.available}")
    lines.append(f"- **Suggestion Count:** {lr.suggestion_count}")
    if lr.by_status:
        lines.append("- **By Status:**")
        for status, count in lr.by_status.items():
            lines.append(f"  - {status}: {count}")
    lines.append("")

    lines.append("## Audit")
    au = snapshot.audit
    lines.append(f"- **Available:** {au.available}")
    lines.append(f"- **Recent Events:** {au.recent_events}")
    lines.append(f"- **Risk Approved:** {au.recent_risk_approved}")
    lines.append(f"- **Risk Rejected:** {au.recent_risk_rejected}")
    lines.append(f"- **Backtest Completed:** {au.recent_backtest_completed}")
    lines.append(f"- **Backtest Failed:** {au.recent_backtest_failed}")
    lines.append("")

    lines.append("## Safety")
    sf = snapshot.safety
    lines.append(f"- **Available:** {sf.available}")
    lines.append(f"- **Kill Switch Mode:** {sf.kill_switch_mode}")
    lines.append(f"- **Kill Switch Active:** {sf.kill_switch_active}")
    lines.append(f"- **Heartbeat Status:** {sf.heartbeat_status}")
    lines.append(f"- **Live Trading Enabled:** {sf.live_trading_enabled}")
    lines.append(f"- **Live Submit Enabled:** {sf.live_submit_enabled}")
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    lines.append(_diagnostics_markdown(snapshot.diagnostics))
    lines.append("")

    if snapshot.missing_data:
        lines.append("## Missing Data")
        for item in snapshot.missing_data:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*This dashboard is read-only, local, and research-only. It is not a trading interface, not financial advice, and does not expose execution controls.*")
    lines.append("")

    return "\n".join(lines)
