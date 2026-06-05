from __future__ import annotations

import json
import os
import re
from pathlib import Path
from datetime import UTC, datetime
from typing import Any

from atlas_agent.config import AtlasConfig
from atlas_agent.dashboard.models import (
    DashboardAudit,
    DashboardBacktests,
    DashboardLearning,
    DashboardPortfolio,
    DashboardReflections,
    DashboardReports,
    DashboardSafety,
    DashboardSkills,
    DashboardSnapshot,
    DashboardStatusSummary,
    DashboardSystemHealth,
)
from atlas_agent.audit.redaction import redact_payload
from atlas_agent.audit.verify import verify_audit_log, verify_run_manifest
from atlas_agent.providers.catalog import get_provider_profile
from atlas_agent.providers.runtime import resolve_runtime_provider
from atlas_agent.safety.state import KillSwitchState
from atlas_agent.safety.heartbeat import HeartbeatManager


def _collect_provider_summary(config: AtlasConfig) -> DashboardStatusSummary:
    try:
        runtime = resolve_runtime_provider(config)
    except Exception:
        return DashboardStatusSummary(
            status="unknown",
            message="Provider: unknown",
        )

    provider_id = str(runtime.get("provider") or "unknown")
    provider_label = str(runtime.get("provider_label") or provider_id)
    key_source = str(runtime.get("api_key_source") or "missing")
    errors = runtime.get("errors") or []
    profile = get_provider_profile(provider_id)

    if profile is None or provider_id in {"null", "local_command"} or errors:
        status = "unknown"
    elif key_source in {"process_env", "env_atlas", "oauth_adc", "none"}:
        status = "active"
    else:
        status = "missing"

    if key_source in {"process_env", "env_atlas", "oauth_adc"}:
        credential_status = "credentials configured"
    elif key_source == "none":
        credential_status = "credentials not required"
    else:
        credential_status = "credentials missing"

    return DashboardStatusSummary(
        status=status,
        message=f"Provider: {provider_label} ({provider_id}); {credential_status}",
    )


def _collect_system_health(config: AtlasConfig, workspace_root: Path) -> DashboardSystemHealth:
    checks: list[dict[str, Any]] = []
    workspace_initialized = (workspace_root / ".atlas" / "config.toml").exists() or (workspace_root / ".atlas" / "config.json").exists()
    config_readable = (workspace_root / ".atlas" / "config.toml").exists()
    ready_for_backtesting = (workspace_root / ".atlas").exists() and config.data_path is not None and Path(config.data_path).exists()
    ready_for_paper_agentic = workspace_initialized and config_readable
    ready_for_live = "Missing live trading config" if config.trading_mode != "live" else ready_for_paper_agentic

    checks.append({"id": "workspace.initialized", "status": "pass" if workspace_initialized else "fail", "message": "Workspace has .atlas/config"})
    checks.append({"id": "config.readable", "status": "pass" if config_readable else "fail", "message": "Config file exists"})
    checks.append({"id": "backtest.ready", "status": "pass" if ready_for_backtesting else "fail", "message": "Data path exists"})
    checks.append({"id": "paper.ready", "status": "pass" if ready_for_paper_agentic else "fail", "message": "Workspace + config ready"})

    return DashboardSystemHealth(
        available=True,
        workspace_initialized=workspace_initialized,
        config_readable=config_readable,
        ready_for_backtesting=ready_for_backtesting,
        ready_for_paper_agentic=ready_for_paper_agentic,
        ready_for_live=ready_for_live,
        checks=checks,
    )


def _collect_portfolio(config: AtlasConfig, workspace_root: Path) -> DashboardPortfolio:
    if config.memory_dir:
        portfolio_path = Path(config.memory_dir)
        if not portfolio_path.is_absolute():
            portfolio_path = workspace_root / portfolio_path
    else:
        portfolio_path = workspace_root / "memory"
    portfolio_path = portfolio_path / "portfolio.md"
    if not portfolio_path.exists():
        return DashboardPortfolio(available=False)

    text = portfolio_path.read_text(encoding="utf-8")
    cash: float | None = None
    equity: float | None = None
    positions_count = 0
    symbol: str | None = None

    cash_match = re.search(r"[Cc]ash[:\s]*\$?([\d,]+\.\d{2})", text)
    if cash_match:
        cash = float(cash_match.group(1).replace(",", ""))

    equity_match = re.search(r"[Ee]quity[:\s]*\$?([\d,]+\.\d{2})", text)
    if equity_match:
        equity = float(equity_match.group(1).replace(",", ""))

    # Count position lines like "- AAPL: 10 shares"
    for line in text.splitlines():
        if re.match(r"^\s*[-*]\s+\w+", line):
            positions_count += 1
            if symbol is None:
                sym_match = re.search(r"^\s*[-*]\s+(\w+)", line)
                if sym_match:
                    symbol = sym_match.group(1)

    return DashboardPortfolio(
        available=True,
        cash=cash,
        equity=equity,
        positions_count=positions_count,
        symbol=symbol,
    )


def _collect_backtests(workspace_root: Path) -> DashboardBacktests:
    backtests_dir = workspace_root / ".atlas" / "backtests"
    if not backtests_dir.exists():
        return DashboardBacktests(available=False)

    runs: list[dict[str, Any]] = []
    for run_dir in backtests_dir.iterdir():
        if not run_dir.is_dir():
            continue
        result_path = run_dir / "result.json"
        if not result_path.exists():
            continue
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            runs.append(data)
        except (json.JSONDecodeError, Exception):
            continue

    if not runs:
        return DashboardBacktests(available=False)

    # Sort by some heuristic; try to use run_id or just keep order
    latest = runs[-1]
    metrics = latest.get("metrics", {})
    return DashboardBacktests(
        available=True,
        total_runs=len(runs),
        recent_count=len(runs),
        latest_run_id=latest.get("run_id"),
        latest_symbol=latest.get("config", {}).get("symbol"),
        latest_return_pct=metrics.get("total_return_pct"),
        latest_status=latest.get("status"),
    )


def _collect_reports(workspace_root: Path) -> DashboardReports:
    reports_dir = workspace_root / ".atlas" / "reports"
    if not reports_dir.exists():
        return DashboardReports(available=False)

    report_files = list(reports_dir.glob("*.md")) + list(reports_dir.glob("*.json"))
    if not report_files:
        return DashboardReports(available=False)

    latest = max(report_files, key=lambda p: p.stat().st_mtime)
    report_type = "markdown" if latest.suffix == ".md" else "json"
    return DashboardReports(
        available=True,
        report_count=len(report_files),
        latest_report_type=report_type,
        latest_generated_at=datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat(),
    )


def _collect_reflections(workspace_root: Path) -> DashboardReflections:
    from atlas_agent.reflection.storage import list_artifacts

    try:
        artifacts = list_artifacts(workspace_root)
    except Exception:
        return DashboardReflections(available=False)

    if not artifacts:
        return DashboardReflections(available=False)

    by_status: dict[str, int] = {}
    for a in artifacts:
        status = a.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    return DashboardReflections(
        available=True,
        total_count=len(artifacts),
        by_status=by_status,
    )


def _collect_skills(workspace_root: Path) -> DashboardSkills:
    from atlas_agent.skills.storage import list_candidates
    from atlas_agent.skills.library import list_skills

    try:
        candidates = list_candidates(workspace_root)
    except Exception:
        candidates = []

    try:
        library = list_skills(workspace_root)
    except Exception:
        library = []

    total = len(candidates) + len(library)
    if total == 0:
        return DashboardSkills(available=False)

    by_status: dict[str, int] = {}
    for c in candidates:
        status = c.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    return DashboardSkills(
        available=True,
        candidate_count=len(candidates),
        library_count=len(library),
        by_status=by_status,
    )


def _collect_learning(workspace_root: Path) -> DashboardLearning:
    from atlas_agent.learning.storage import list_suggestions

    try:
        suggestions = list_suggestions(workspace_root)
    except Exception:
        return DashboardLearning(available=False)

    if not suggestions:
        return DashboardLearning(available=False)

    by_status: dict[str, int] = {}
    for s in suggestions:
        status = s.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    return DashboardLearning(
        available=True,
        suggestion_count=len(suggestions),
        by_status=by_status,
    )


def _collect_audit(config: AtlasConfig) -> DashboardAudit:
    audit_events_path = config.audit_dir / "events.jsonl"
    recent_events = 0
    recent_risk_approved = 0
    recent_risk_rejected = 0
    recent_backtest_completed = 0
    recent_backtest_failed = 0

    if audit_events_path.exists():
        try:
            with open(audit_events_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    recent_events += 1
                    if "risk_approved" in line:
                        recent_risk_approved += 1
                    elif "risk_rejected" in line:
                        recent_risk_rejected += 1
                    elif "backtest_completed" in line:
                        recent_backtest_completed += 1
                    elif "backtest_failed" in line:
                        recent_backtest_failed += 1
        except Exception:
            pass

    available = audit_events_path.exists() or recent_events > 0
    return DashboardAudit(
        available=available,
        recent_events=recent_events,
        recent_risk_approved=recent_risk_approved,
        recent_risk_rejected=recent_risk_rejected,
        recent_backtest_completed=recent_backtest_completed,
        recent_backtest_failed=recent_backtest_failed,
    )


def _collect_safety(config: AtlasConfig, workspace_root: Path) -> DashboardSafety:
    safety_dir = workspace_root / ".atlas" / "safety"
    ks_state = KillSwitchState(safety_dir / "kill_switch.json")
    ks_status = ks_state.load()

    hb_manager = HeartbeatManager(safety_dir / "heartbeat.json")
    hb_expired = hb_manager.is_expired()
    last_hb = hb_manager.last_heartbeat()
    heartbeat_status = "expired" if hb_expired else "healthy" if last_hb else "unknown"

    return DashboardSafety(
        available=True,
        kill_switch_mode=ks_status.mode,
        kill_switch_active=ks_status.mode != "normal",
        heartbeat_status=heartbeat_status,
        live_trading_enabled=config.trading_mode == "live",
        live_submit_enabled=False,
    )


def collect_dashboard_snapshot(config: AtlasConfig, workspace_root: Path) -> DashboardSnapshot:
    """
    Safely collect system status for the dashboard.
    """
    # 1. Base Info
    mode = config.trading_mode if config.trading_mode in ["paper", "live"] else "unknown"

    # 2. Provider Summary
    provider_summary = _collect_provider_summary(config)

    # 3. Broker Sync Summary (Safe collection)
    broker_sync_summary = DashboardStatusSummary(status="unknown", message="No recent sync data")
    portfolio_summary = {"position_count": 0, "cash": 0.0, "equity": 0.0}
    open_orders_summary = {"order_count": 0}

    # Attempt to read latest sync from events or state if we had a persistence layer for it.
    # For now, we'll look at the audit log for the latest sync event if possible.
    audit_events_path = config.audit_dir / "events.jsonl"
    if audit_events_path.exists():
        try:
            # Very naive tail read for status
            with open(audit_events_path, "r", encoding="utf-8") as f:
                last_sync = None
                for line in f:
                    if "broker_sync_completed" in line or "broker_sync_failed" in line:
                        last_sync = json.loads(line)

                if last_sync:
                    payload = last_sync.get("payload", {})
                    broker_sync_summary.status = payload.get("status", "unknown")
                    broker_sync_summary.last_updated = last_sync.get("timestamp")
                    portfolio_summary["position_count"] = payload.get("position_count", 0)
                    open_orders_summary["order_count"] = payload.get("open_order_count", 0)
        except Exception:
            pass

    # 4. Kill Switch & Heartbeat
    safety_dir = workspace_root / ".atlas" / "safety"
    ks_state = KillSwitchState(safety_dir / "kill_switch.json")
    ks_status = ks_state.load()
    kill_switch_summary = {
        "mode": ks_status.mode.upper(),
        "status": "ACTIVE" if ks_status.mode != "normal" else "Inactive",
        "reason": ks_status.reason,
        "updated_at": ks_status.updated_at
    }

    hb_manager = HeartbeatManager(safety_dir / "heartbeat.json")
    hb_expired = hb_manager.is_expired()
    last_hb = hb_manager.last_heartbeat()
    heartbeat_summary = DashboardStatusSummary(
        status="expired" if hb_expired else "healthy" if last_hb else "unknown",
        message="Dead-man heartbeat expired" if hb_expired else "Heartbeat healthy",
        last_updated=last_hb.isoformat() if last_hb else None
    )

    # 5. Audit Summary
    manifest_dir = config.audit_dir / "manifests"
    audit_summary = {"manifest_count": 0, "latest_status": "unknown", "integrity": "unknown"}
    if manifest_dir.exists():
        manifests = list(manifest_dir.glob("*.json"))
        audit_summary["manifest_count"] = len(manifests)
        if manifests:
            latest_manifest_path = max(manifests, key=os.path.getmtime)
            try:
                m_data = json.loads(latest_manifest_path.read_text(encoding="utf-8"))
                audit_summary["latest_status"] = m_data.get("status")

                # Check integrity of the latest one
                v_res = verify_run_manifest(latest_manifest_path)
                audit_summary["integrity"] = "valid" if v_res.valid else "compromised"
            except Exception:
                pass

    # 6. Safety Plan Summary
    # In a real app we might store these in a DB or specific dir.
    # For now we'll peek at diagnostics of latest audit events.
    safety_plan_summary = {"pending_plans": 0, "last_plan_mode": "none"}

    # 7. Recent Events
    recent_events = []
    events_dir = config.events_dir
    # Peer into standard EventLogger files if they exist
    # For now, let's keep it empty or safe.

    # 8. New data-layer view models
    system_health = _collect_system_health(config, workspace_root)
    portfolio = _collect_portfolio(config, workspace_root)
    backtests = _collect_backtests(workspace_root)
    reports = _collect_reports(workspace_root)
    reflections = _collect_reflections(workspace_root)
    skills = _collect_skills(workspace_root)
    learning = _collect_learning(workspace_root)
    audit = _collect_audit(config)
    safety = _collect_safety(config, workspace_root)

    # 9. Warnings and missing data
    warnings: list[str] = []
    missing_data: list[str] = []

    if config.trading_mode == "live":
        warnings.append("Live trading mode is enabled. Ensure all safety checks are in place.")

    if not system_health.workspace_initialized:
        missing_data.append("workspace_config")
    if not portfolio.available:
        missing_data.append("portfolio")
    if not backtests.available:
        missing_data.append("backtests")
    if not reports.available:
        missing_data.append("reports")
    if not reflections.available:
        missing_data.append("reflections")
    if not skills.available:
        missing_data.append("skills")
    if not learning.available:
        missing_data.append("learning")
    if not audit.available:
        missing_data.append("audit_events")

    return DashboardSnapshot(
        workspace=str(workspace_root),
        mode=mode,  # type: ignore
        configured=True,
        provider_summary=provider_summary,
        broker_sync_summary=broker_sync_summary,
        portfolio_summary=portfolio_summary,
        open_orders_summary=open_orders_summary,
        risk_summary=DashboardStatusSummary(status="enabled", message="Deterministic gates active"),
        kill_switch_summary=kill_switch_summary,
        heartbeat_summary=heartbeat_summary,
        audit_summary=audit_summary,
        safety_plan_summary=safety_plan_summary,
        recent_events=recent_events,
        diagnostics={"redacted": True},
        system_health=system_health,
        portfolio=portfolio,
        backtests=backtests,
        reports=reports,
        reflections=reflections,
        skills=skills,
        learning=learning,
        audit=audit,
        safety=safety,
        warnings=warnings,
        missing_data=missing_data,
    )
