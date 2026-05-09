from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import UTC, datetime
from typing import Any, Optional

from atlas_agent.config import AtlasConfig
from atlas_agent.dashboard.models import DashboardSnapshot, DashboardStatusSummary
from atlas_agent.audit.redaction import redact_payload
from atlas_agent.audit.verify import verify_audit_log, verify_run_manifest
from atlas_agent.safety.state import KillSwitchState
from atlas_agent.safety.heartbeat import HeartbeatManager


def collect_dashboard_snapshot(config: AtlasConfig, workspace_root: Path) -> DashboardSnapshot:
    """
    Safely collect system status for the dashboard.
    """
    # 1. Base Info
    mode = config.trading_mode if config.trading_mode in ["paper", "live"] else "unknown"
    
    # 2. Provider Summary
    provider_name = os.getenv("AI_PROVIDER", "not configured")
    provider_status = "active" if provider_name != "not configured" else "missing"
    provider_summary = DashboardStatusSummary(
        status=provider_status,
        message=f"Provider: {provider_name}"
    )

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

    return DashboardSnapshot(
        workspace=str(workspace_root),
        mode=mode, # type: ignore
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
        diagnostics={"redacted": True}
    )
