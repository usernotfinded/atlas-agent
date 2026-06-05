from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.dashboard.models import DashboardSnapshot


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
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Atlas Agent Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0a0a0c; color: #e0e0e6; line-height: 1.5; padding: 2rem; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #303036; padding-bottom: 1rem; margin-bottom: 2rem; }}
        h1 {{ margin: 0; font-size: 1.5rem; color: #ff4500; text-transform: uppercase; letter-spacing: 2px; }}
        .timestamp {{ color: #80808a; font-size: 0.8rem; }}
        .workspace {{ color: #a0a0ab; font-size: 0.8rem; margin-top: 0.2rem; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }}
        .card {{ background: #16161a; border: 1px solid #303036; border-radius: 8px; padding: 1.5rem; transition: border-color 0.2s; }}
        .card:hover {{ border-color: #40404a; }}
        .card h2 {{ margin: 0 0 1rem 0; font-size: 1.1rem; color: #ff8c00; border-bottom: 1px solid #25252b; padding-bottom: 0.5rem; }}
        
        .status {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; }}
        .status-success, .status-active, .status-healthy {{ background: #1b3d20; color: #4caf50; }}
        .status-failed, .status-missing, .status-expired, .status-compromised {{ background: #4a1c1c; color: #f44336; }}
        .status-running, .status-partial {{ background: #3d3b1b; color: #ffeb3b; }}
        .status-unknown {{ background: #303036; color: #80808a; }}
        
        .stat-row {{ display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        .stat-label {{ color: #a0a0ab; }}
        .stat-value {{ font-weight: 500; }}
        
        pre {{ background: #000; padding: 0.5rem; border-radius: 4px; font-size: 0.75rem; overflow-x: auto; color: #00ff00; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Atlas Agent</h1>
                <div class="workspace">{snapshot.workspace}</div>
            </div>
            <div class="timestamp">Generated: {snapshot.generated_at}</div>
        </header>

        <div class="grid">
            <div class="card">
                <h2>System Status</h2>
                <div class="stat-row">
                    <span class="stat-label">Mode</span>
                    <span class="stat-value">{snapshot.mode.upper()}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">AI Provider</span>
                    <span class="status status-{snapshot.provider_summary.status}">{snapshot.provider_summary.status}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Configured</span>
                    <span class="stat-value">{snapshot.configured}</span>
                </div>
            </div>

            <div class="card">
                <h2>Kill Switch</h2>
                <div class="stat-row">
                    <span class="stat-label">Mode</span>
                    <span class="stat-value" style="color: {'#f44336' if ks_mode != 'NORMAL' else 'inherit'}">{ks_mode}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Status</span>
                    <span class="stat-value">{ks_status}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Heartbeat</span>
                    <span class="status status-{snapshot.heartbeat_summary.status}">{snapshot.heartbeat_summary.status}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Last Heartbeat</span>
                    <span class="stat-value">{snapshot.heartbeat_summary.last_updated or 'None'}</span>
                </div>
            </div>

            <div class="card">
                <h2>Broker Sync</h2>
                <div class="stat-row">
                    <span class="stat-label">Status</span>
                    <span class="status status-{snapshot.broker_sync_summary.status}">{snapshot.broker_sync_summary.status}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Positions</span>
                    <span class="stat-value">{port.get('position_count', 0)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Open Orders</span>
                    <span class="stat-value">{orders.get('order_count', 0)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Last Sync</span>
                    <span class="stat-value">{snapshot.broker_sync_summary.last_updated or 'None'}</span>
                </div>
            </div>

            <div class="card">
                <h2>Audit Health</h2>
                <div class="stat-row">
                    <span class="stat-label">Integrity</span>
                    <span class="status status-{audit.get('integrity', 'unknown')}">{audit.get('integrity', 'unknown')}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Total Runs</span>
                    <span class="stat-value">{audit.get('manifest_count', 0)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Latest Status</span>
                    <span class="stat-value">{audit.get('latest_status', 'unknown')}</span>
                </div>
            </div>

            <div class="card">
                <h2>Risk Manager</h2>
                <div class="stat-row">
                    <span class="stat-label">Status</span>
                    <span class="status status-{snapshot.risk_summary.status}">{snapshot.risk_summary.status}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Rules</span>
                    <span class="stat-value">Position, Exposure, Symbol, Confidence</span>
                </div>
            </div>

            <div class="card">
                <h2>Recent Diagnostics</h2>
                <pre>{json.dumps(snapshot.diagnostics, indent=2)}</pre>
            </div>
        </div>
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
    lines.append(f"**Mode:** {snapshot.mode}")
    lines.append(f"**Dashboard Mode:** {snapshot.dashboard_mode}")
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
    bt = snapshot.backtests
    lines.append(f"- **Available:** {bt.available}")
    lines.append(f"- **Total Runs:** {bt.total_runs}")
    lines.append(f"- **Latest Run:** {bt.latest_run_id or 'N/A'}")
    lines.append(f"- **Latest Symbol:** {bt.latest_symbol or 'N/A'}")
    lines.append(f"- **Latest Return:** {bt.latest_return_pct if bt.latest_return_pct is not None else 'N/A'}%")
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
