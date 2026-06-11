"""Markdown and JSON renderers for report data.

All output is deterministic and contains no fake content.
"""
from __future__ import annotations

import json
from typing import Any

from atlas_agent.reports.models import ReportData


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(data: ReportData) -> str:
    """Render report data as Markdown."""
    lines: list[str] = []
    m = data.metadata

    # Header
    lines.append(f"# Atlas Agent Report: {m.report_type.title()}")
    lines.append("")
    lines.append(f"**Generated:** {m.generated_at}")
    lines.append(f"**Workspace:** {m.workspace}")
    lines.append(f"**Format:** {m.format}")
    lines.append("")

    # Portfolio
    lines.append("## Portfolio Summary")
    lines.append("")
    if data.portfolio.available:
        p = data.portfolio
        lines.append(f"- **Cash:** {_fmt(p.cash)}")
        lines.append(f"- **Equity:** {_fmt(p.equity)}")
        lines.append(f"- **Positions:** {_fmt(p.positions_count)}")
        if p.symbol:
            lines.append(f"- **Symbol:** {p.symbol}")
    else:
        lines.append("No portfolio data available.")
    lines.append("")

    # Backtest
    lines.append("## Backtest Summary")
    lines.append("")
    if data.backtest.available:
        b = data.backtest
        lines.append(f"- **Total Runs:** {b.total_runs}")
        lines.append(f"- **Recent (7d):** {b.recent_count}")
        lines.append(f"- **Latest Run:** {b.latest_run_id}")
        lines.append(f"- **Latest Symbol:** {_fmt(b.latest_symbol)}")
        lines.append(f"- **Latest Return:** {_fmt(b.latest_return_pct)}%")
        lines.append(f"- **Latest Status:** {_fmt(b.latest_status)}")
        lines.append(f"- **Latest Schema Version:** {_fmt(b.latest_schema_version)}")
        lines.append(f"- **Latest Validation Status:** {_fmt(b.latest_validation_status)}")
    else:
        lines.append("No backtest data available.")
    lines.append("")

    # Research
    lines.append("## Research Summary")
    lines.append("")
    if data.research.available:
        r = data.research
        lines.append(f"- **Artifacts:** {r.artifact_count}")
        lines.append(f"- **Evaluations:** {r.recent_evaluations}")
        lines.append(f"- **Plans:** {r.recent_plans}")
        lines.append(f"- **Verifications:** {r.recent_verifications}")
        if r.symbol:
            lines.append(f"- **Symbol:** {r.symbol}")
    else:
        lines.append("No research data available.")
    lines.append("")

    # Risk
    lines.append("## Risk Summary")
    lines.append("")
    if data.risk.available:
        rk = data.risk
        lines.append(f"- **Live Trading:** {_fmt(rk.live_trading_enabled)}")
        lines.append(f"- **Live Submit:** {_fmt(rk.live_submit_enabled)}")
        lines.append(f"- **Kill Switch:** {_fmt(rk.kill_switch_enabled)}")
        lines.append(f"- **Max Daily Loss:** {_fmt(rk.max_daily_loss)}")
        lines.append(f"- **Max Position:** {_fmt(rk.max_position_notional)}")
        lines.append(f"- **Max Trades/Day:** {_fmt(rk.max_trades_per_day)}")
        lines.append(f"- **Leverage Allowed:** {_fmt(rk.allow_leverage)}")
    else:
        lines.append("No risk configuration data available.")
    lines.append("")

    # Audit / Decisions
    lines.append("## Audit / Decision Summary")
    lines.append("")
    if data.audit_decisions.available:
        a = data.audit_decisions
        lines.append(f"- **Recent Events:** {a.recent_events}")
        lines.append(f"- **Risk Approved:** {a.recent_risk_approved}")
        lines.append(f"- **Risk Rejected:** {a.recent_risk_rejected}")
        lines.append(f"- **Backtests Completed:** {a.recent_backtest_completed}")
        lines.append(f"- **Backtests Failed:** {a.recent_backtest_failed}")
    else:
        lines.append("No audit or event data available.")
    lines.append("")

    # System Health
    lines.append("## System Health Summary")
    lines.append("")
    if data.system_health.available:
        h = data.system_health
        lines.append(f"- **Workspace Initialized:** {_fmt(h.workspace_initialized)}")
        lines.append(f"- **Config Readable:** {_fmt(h.config_readable)}")
        lines.append(f"- **Ready for Backtesting:** {_fmt(h.ready_for_backtesting)}")
        lines.append(f"- **Ready for Paper Agentic:** {_fmt(h.ready_for_paper_agentic)}")
        lines.append(f"- **Ready for Live:** {_fmt(h.ready_for_live)}")
        if h.checks:
            lines.append("")
            lines.append("### Checks")
            lines.append("")
            lines.append("| Check | Status | Message |")
            lines.append("| --- | --- | --- |")
            for c in h.checks:
                lines.append(f"| {c.get('id', 'n/a')} | {c.get('status', 'n/a')} | {c.get('message', '')} |")
    else:
        lines.append("No system health data available.")
    lines.append("")

    # Missing Data
    if data.missing_data.missing_sources:
        lines.append("## Missing Data")
        lines.append("")
        lines.append("The following data sources were not available for this report:")
        lines.append("")
        for source in data.missing_data.missing_sources:
            lines.append(f"- {source}")
        lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(f"*{data.disclaimer}*")
    lines.append("")

    return "\n".join(lines)


def render_json(data: ReportData) -> dict[str, Any]:
    """Render report data as a JSON-serializable dict."""
    return {
        "metadata": {
            "report_type": data.metadata.report_type,
            "generated_at": data.metadata.generated_at,
            "format": data.metadata.format,
            "version": data.metadata.version,
            "workspace": data.metadata.workspace,
        },
        "portfolio": {
            "available": data.portfolio.available,
            "cash": data.portfolio.cash,
            "equity": data.portfolio.equity,
            "positions_count": data.portfolio.positions_count,
            "positions": data.portfolio.positions,
            "symbol": data.portfolio.symbol,
        },
        "backtest": {
            "available": data.backtest.available,
            "recent_count": data.backtest.recent_count,
            "latest_run_id": data.backtest.latest_run_id,
            "latest_symbol": data.backtest.latest_symbol,
            "latest_return_pct": data.backtest.latest_return_pct,
            "latest_status": data.backtest.latest_status,
            "total_runs": data.backtest.total_runs,
            "latest_schema_version": data.backtest.latest_schema_version,
            "latest_validation_status": data.backtest.latest_validation_status,
        },
        "research": {
            "available": data.research.available,
            "artifact_count": data.research.artifact_count,
            "recent_evaluations": data.research.recent_evaluations,
            "recent_plans": data.research.recent_plans,
            "recent_verifications": data.research.recent_verifications,
            "symbol": data.research.symbol,
        },
        "risk": {
            "available": data.risk.available,
            "live_trading_enabled": data.risk.live_trading_enabled,
            "live_submit_enabled": data.risk.live_submit_enabled,
            "kill_switch_enabled": data.risk.kill_switch_enabled,
            "max_daily_loss": data.risk.max_daily_loss,
            "max_position_notional": data.risk.max_position_notional,
            "max_trades_per_day": data.risk.max_trades_per_day,
            "allow_leverage": data.risk.allow_leverage,
        },
        "audit_decisions": {
            "available": data.audit_decisions.available,
            "recent_events": data.audit_decisions.recent_events,
            "recent_risk_approved": data.audit_decisions.recent_risk_approved,
            "recent_risk_rejected": data.audit_decisions.recent_risk_rejected,
            "recent_backtest_completed": data.audit_decisions.recent_backtest_completed,
            "recent_backtest_failed": data.audit_decisions.recent_backtest_failed,
        },
        "system_health": {
            "available": data.system_health.available,
            "workspace_initialized": data.system_health.workspace_initialized,
            "config_readable": data.system_health.config_readable,
            "ready_for_backtesting": data.system_health.ready_for_backtesting,
            "ready_for_paper_agentic": data.system_health.ready_for_paper_agentic,
            "ready_for_live": data.system_health.ready_for_live,
            "checks": data.system_health.checks,
        },
        "missing_data": data.missing_data.missing_sources,
        "disclaimer": data.disclaimer,
    }


def render_json_string(data: ReportData) -> str:
    """Render report data as a formatted JSON string."""
    payload = render_json(data)
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
