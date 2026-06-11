"""Local data sources for report generation.

All functions read only local files and return safe defaults when data is missing.
No network calls. No provider or broker APIs.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.reports.models import (
    AuditDecisionSummary,
    BacktestSummary,
    MissingDataSection,
    PortfolioSummary,
    ResearchSummary,
    RiskSummary,
    SystemHealthSummary,
)


def _workspace_path(path: str | Path = ".") -> Path:
    return Path(path)


def load_portfolio_summary(workspace: str | Path = ".") -> PortfolioSummary:
    """Load portfolio summary from local memory files."""
    ws = _workspace_path(workspace)
    portfolio_path = ws / "memory" / "portfolio.md"
    if portfolio_path.exists():
        content = portfolio_path.read_text(encoding="utf-8")
        # Best-effort parsing from markdown
        cash = None
        equity = None
        positions_count = 0
        positions = []
        symbol = None
        for line in content.splitlines():
            line_lower = line.lower()
            if "cash:" in line_lower:
                try:
                    cash = float(line_lower.split("cash:")[1].strip().replace("$", "").replace(",", ""))
                except (ValueError, IndexError):
                    pass
            if "equity:" in line_lower:
                try:
                    equity = float(line_lower.split("equity:")[1].strip().replace("$", "").replace(",", ""))
                except (ValueError, IndexError):
                    pass
            if line.strip().startswith("-") and (":" in line or "$" in line):
                positions_count += 1
                positions.append({"line": line.strip()})
        return PortfolioSummary(
            available=True,
            cash=cash,
            equity=equity,
            positions_count=positions_count,
            positions=positions,
            symbol=symbol,
        )
    return PortfolioSummary(available=False)


def load_backtest_summary(workspace: str | Path = ".") -> BacktestSummary:
    """Load backtest summary from local .atlas/backtests directory."""
    ws = _workspace_path(workspace)
    backtests_dir = ws / ".atlas" / "backtests"
    if not backtests_dir.exists():
        return BacktestSummary(available=False)

    result_files = sorted(backtests_dir.glob("*/result.json"), reverse=True)
    total_runs = len(result_files)
    if total_runs == 0:
        return BacktestSummary(available=False)

    latest = result_files[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        from atlas_agent.backtest.report_schema import get_schema_status
        return BacktestSummary(
            available=True,
            recent_count=min(total_runs, 7),
            latest_run_id=data.get("run_id"),
            latest_symbol=data.get("config", {}).get("symbol"),
            latest_return_pct=data.get("metrics", {}).get("total_return_pct"),
            latest_status=data.get("status"),
            total_runs=total_runs,
            latest_schema_version=data.get("schema_version"),
            latest_validation_status=get_schema_status(data),
        )
    except (json.JSONDecodeError, OSError):
        return BacktestSummary(available=False, total_runs=total_runs)


def load_research_summary(workspace: str | Path = ".") -> ResearchSummary:
    """Load research summary from local .atlas/research directory."""
    ws = _workspace_path(workspace)
    research_dir = ws / ".atlas" / "research"
    if not research_dir.exists():
        return ResearchSummary(available=False)

    artifacts = list(research_dir.rglob("*.json"))
    total = len(artifacts)
    if total == 0:
        return ResearchSummary(available=False)

    evaluations = len(list(research_dir.rglob("evaluations/*.json")))
    plans = len(list(research_dir.rglob("plans/*.json")))
    verifications = len(list(research_dir.rglob("verifications/*.json")))

    # Try to infer symbol from first artifact
    symbol = None
    if artifacts:
        try:
            first = json.loads(artifacts[0].read_text(encoding="utf-8"))
            symbol = first.get("symbol") or first.get("market_symbol")
        except (json.JSONDecodeError, OSError):
            pass

    return ResearchSummary(
        available=True,
        artifact_count=total,
        recent_evaluations=evaluations,
        recent_plans=plans,
        recent_verifications=verifications,
        symbol=symbol,
    )


def load_risk_summary(workspace: str | Path = ".") -> RiskSummary:
    """Load risk summary from local config."""
    ws = _workspace_path(workspace)
    config_path = ws / ".atlas" / "config.toml"
    if not config_path.exists():
        return RiskSummary(available=False)

    try:
        import tomllib
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return RiskSummary(available=False)

    risk = data.get("risk", {})
    broker = data.get("broker", {})
    safety = data.get("safety", {})

    return RiskSummary(
        available=True,
        live_trading_enabled=broker.get("enable_live_trading", False),
        live_submit_enabled=broker.get("enable_live_submit", False),
        kill_switch_enabled=safety.get("kill_switch_enabled", False),
        max_daily_loss=risk.get("max_daily_loss"),
        max_position_notional=risk.get("max_position_notional"),
        max_trades_per_day=risk.get("max_trades_per_day"),
        allow_leverage=risk.get("allow_leverage", False),
    )


def load_audit_decision_summary(workspace: str | Path = ".") -> AuditDecisionSummary:
    """Load audit/decision summary from local event logs."""
    ws = _workspace_path(workspace)
    logs_dir = ws / ".atlas" / "logs"
    if not logs_dir.exists():
        return AuditDecisionSummary(available=False)

    event_files = sorted(logs_dir.glob("*.jsonl"), reverse=True)
    if not event_files:
        return AuditDecisionSummary(available=False)

    recent_events = 0
    risk_approved = 0
    risk_rejected = 0
    backtest_completed = 0
    backtest_failed = 0

    # Read last 7 days of logs, capped at 1000 events
    for log_file in event_files[:7]:
        try:
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    recent_events += 1
                    if recent_events > 1000:
                        break
                    etype = record.get("event_type", "")
                    if etype == "risk_approved":
                        risk_approved += 1
                    elif etype == "risk_rejected":
                        risk_rejected += 1
                    elif etype == "backtest_completed":
                        backtest_completed += 1
                    elif etype == "backtest_failed":
                        backtest_failed += 1
        except OSError:
            continue
        if recent_events > 1000:
            break

    return AuditDecisionSummary(
        available=recent_events > 0,
        recent_events=recent_events,
        recent_risk_approved=risk_approved,
        recent_risk_rejected=risk_rejected,
        recent_backtest_completed=backtest_completed,
        recent_backtest_failed=backtest_failed,
    )


def load_system_health_summary(workspace: str | Path = ".") -> SystemHealthSummary:
    """Load system health from local workspace diagnostics."""
    ws = _workspace_path(workspace)
    workspace_initialized = (ws / ".atlas").exists()
    config_readable = (ws / ".atlas" / "config.toml").exists()

    checks = []
    ready_for_backtesting = workspace_initialized and config_readable
    ready_for_paper_agentic = False
    ready_for_live = False

    if workspace_initialized:
        checks.append({"id": "workspace.initialized", "status": "pass", "message": "Workspace exists"})
    else:
        checks.append({"id": "workspace.initialized", "status": "fail", "message": "Workspace missing"})

    if config_readable:
        checks.append({"id": "config.readable", "status": "pass", "message": "Config readable"})
    else:
        checks.append({"id": "config.readable", "status": "fail", "message": "Config missing"})

    # Try to run diagnostics if config is available
    if config_readable:
        try:
            from atlas_agent.config.schema import AtlasConfig
            from atlas_agent.diagnostics.readiness import run_diagnostics
            config = AtlasConfig(workspace_root=ws)
            report = run_diagnostics(config)
            ready_for_backtesting = report.ready_for_backtesting
            ready_for_paper_agentic = report.ready_for_paper_agentic
            ready_for_live = report.ready_for_live
            checks = [{"id": c.id, "status": c.status, "message": c.message} for c in report.checks]
        except Exception:
            pass

    return SystemHealthSummary(
        available=True,
        workspace_initialized=workspace_initialized,
        config_readable=config_readable,
        ready_for_backtesting=ready_for_backtesting,
        ready_for_paper_agentic=ready_for_paper_agentic,
        ready_for_live=ready_for_live,
        checks=checks,
    )


def collect_missing_data(
    portfolio: PortfolioSummary,
    backtest: BacktestSummary,
    research: ResearchSummary,
    risk: RiskSummary,
    audit: AuditDecisionSummary,
    system_health: SystemHealthSummary,
) -> MissingDataSection:
    """Collect list of data sources that were unavailable."""
    missing = []
    if not portfolio.available:
        missing.append("portfolio")
    if not backtest.available:
        missing.append("backtest")
    if not research.available:
        missing.append("research")
    if not risk.available:
        missing.append("risk")
    if not audit.available:
        missing.append("audit/events")
    if not system_health.available:
        missing.append("system_health")
    return MissingDataSection(missing_sources=missing)
