# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/submit_dry_run.py
# PURPOSE: Runs every gate a live submit would run, and then does NOT submit. The
#          rehearsal: it answers "would this order go through, and if not, which
#          lock stops it?" without putting anything at risk.
# DEPS:    the same gates as submit_execution.py — approval, risk, broker sync —
#          minus the broker call itself. That symmetry is the whole value: a dry
#          run that checked different things would be worthless as a rehearsal.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from atlas_agent.brokers.live_sync_validation import validate_live_sync
from atlas_agent.brokers.resolver import BrokerResolver
from atlas_agent.brokers.sync import BrokerSyncService
from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidApprovalIdError,
    InvalidPendingOrderError,
)
from atlas_agent.execution.submit_state import compute_client_order_id
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput


# ==============================================================================
# REPORT MODEL
# ==============================================================================

@dataclass
class DryRunReport:
    ok: bool
    status: str
    order_id: str
    mode: str = "live"
    gates: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    message: str = ""
    risk: dict[str, Any] | None = None
    sync: dict[str, Any] | None = None
    # "preview" is not decoration: compute_client_order_id() is deterministic, so this
    # is the EXACT id a real submit would use. It lets an operator cross-check against
    # the broker for an order that may already exist before deciding to send another.
    client_order_id_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "order_id": self.order_id,
            "mode": self.mode,
            "gates": self.gates,
            "warnings": self.warnings,
            "blocked_reason": self.blocked_reason,
            "message": self.message,
            "risk": self.risk,
            "sync": self.sync,
            "client_order_id_preview": self.client_order_id_preview,
        }


# ==============================================================================
# DRY RUN
# ==============================================================================

def run_submit_dry_run(
    order_id: str,
    config: Any,
    approval_manager: ApprovalManager,
) -> DryRunReport:
    """Validate all live submit gates for an approved pending order without executing.

    Returns a DryRunReport. Never raises for expected validation failures.
    Only InvalidApprovalIdError may escape for path-traversal attempts.
    """
    gates: dict[str, str] = {}
    warnings: list[str] = []

    # 1. Load pending order file (path traversal is handled by path_for)
    try:
        path = approval_manager.path_for(order_id)
    except InvalidApprovalIdError:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={"path_traversal": "fail"},
            blocked_reason="invalid order id",
            message="Invalid pending order id.",
        )

    if not path.exists():
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={"pending_file": "fail"},
            blocked_reason="pending order not found",
            message="Pending order not found.",
        )

    # 2. Read and validate payload (schema, hash, order fields)
    try:
        payload = approval_manager._read_payload(path)
    except (InvalidPendingOrderError, json.JSONDecodeError):
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={"pending_file": "fail", "integrity": "fail"},
            blocked_reason="pending order file is invalid or corrupted",
            message="Pending order file is invalid or corrupted.",
        )

    gates["pending_file"] = "pass"
    gates["integrity"] = "pass"

    # 3. Idempotency state check (before approved gate, because these states
    # are "approved" flag-wise but not actionable)
    current_status = payload.get("status")
    if current_status in ("submit_uncertain", "reconciliation_required", "submit_requested"):
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="reconciliation_required",
            message="Order is in submit_uncertain or reconciliation_required state. Run --reconcile first.",
        )

    # 4. Must be approved
    if not payload.get("approved") or current_status != "approved":
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "approved": "fail"},
            blocked_reason="order not approved",
            message="Order is not approved.",
        )
    gates["approved"] = "pass"

    # 5. Must not be expired
    expires_at_raw = payload.get("expires_at")
    if not expires_at_raw:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "not_expired": "fail"},
            blocked_reason="missing expiry",
            message="Approval expiry is missing.",
        )
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except (ValueError, TypeError):
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "not_expired": "fail"},
            blocked_reason="invalid expiry",
            message="Approval expiry is invalid.",
        )
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "not_expired": "fail"},
            blocked_reason="approval expired",
            message="Approval has expired.",
        )
    gates["not_expired"] = "pass"

    # 6. Must not already have client_order_id
    if payload.get("client_order_id") is not None:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="client_order_id_already_present",
            message="Order already has a client_order_id. Run --reconcile before any further submit action.",
        )
    gates["idempotency"] = "pass"

    # 6. Must not already have broker_order_id
    if payload.get("broker_order_id") is not None:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "no_broker_order_id": "fail"},
            blocked_reason="already has broker_order_id",
            message="Order already has a broker_order_id.",
        )
    gates["no_broker_order_id"] = "pass"

    # 7. Must have no submit attempts
    if payload.get("submit_attempts"):
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "no_submit_attempts": "fail"},
            blocked_reason="prior submit attempts exist",
            message="Order has prior submit attempts.",
        )
    gates["no_submit_attempts"] = "pass"

    # 8. Live trading must be enabled
    if not config.enable_live_trading:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "live_trading_enabled": "fail"},
            blocked_reason="live trading disabled",
            message="Live trading is not enabled.",
        )
    gates["live_trading_enabled"] = "pass"

    # 9. Broker status
    resolver = BrokerResolver(config)
    broker_status = resolver.resolve_status("live")
    gates["can_sync"] = "pass" if broker_status.can_sync else "fail"
    gates["can_submit"] = "pass" if broker_status.can_submit else "fail_expected"

    if not broker_status.can_sync:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates=gates,
            blocked_reason="broker sync unavailable",
            message="Broker sync is not available.",
        )

    # 10. Resolve sync provider and perform sync
    resolution = resolver.resolve_sync_provider("live")
    if resolution.sync_provider is None:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "fresh_sync": "fail"},
            blocked_reason="no sync provider",
            message="No live sync provider available.",
        )

    sync_service = BrokerSyncService(
        broker=resolution.sync_provider,
        audit_writer=None,
        run_id="dry-run",
    )
    sync_result = sync_service.sync()

    # 11. Validate sync result
    sync_warnings, sync_error = validate_live_sync(sync_result, broker_status)
    if sync_error is not None:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "fresh_sync": "fail"},
            blocked_reason="live broker sync failed",
            message="Live broker sync failed.",
            sync={
                "status": "failed",
                "warnings": [],
            },
        )

    for w in sync_warnings:
        warnings.append(f"sync warning: {w['operation']}")
    gates["fresh_sync"] = "pass"

    # 12. Build PortfolioSnapshot
    portfolio_snapshot = sync_service.get_portfolio_snapshot(
        sync_result, broker_id=broker_status.broker_id
    )

    # 13. Build OrderRiskInput from pending order
    order_dict = payload["order"]
    limit_price = order_dict.get("limit_price")
    price = limit_price if limit_price is not None else 0.0

    risk_input = OrderRiskInput(
        symbol=order_dict["symbol"],
        side=order_dict["side"],
        quantity=order_dict["quantity"],
        price=price,
        notional=order_dict["quantity"] * price,
        leverage=order_dict.get("leverage", 1.0),
        confidence=order_dict.get("confidence"),
        stop_loss=order_dict.get("stop_loss"),
    )

    # 14. Run risk evaluation
    risk_limits = RiskLimits(
        max_position_notional=config.max_position_size,
        max_single_trade_notional=config.max_order_notional,
        allowed_symbols=config.symbol_allowlist,
        blocked_symbols=config.symbol_blocklist or set(),
        live_trading_enabled=config.enable_live_trading,
        paper_only=not config.enable_live_trading,
        require_stop_loss_live=getattr(config, "require_stop_loss_live", True),
    )
    risk_manager = RiskManager(
        limits=risk_limits,
        audit_writer=None,
        run_id="dry-run",
    )
    decision = risk_manager.evaluate_order(
        risk_input, portfolio_snapshot, mode="live"
    )

    risk_dict: dict[str, Any] = {
        "allowed": decision.allowed,
        "status": decision.status,
        "reason": decision.reason,
        "violations": [v.model_dump() for v in decision.violations],
        "classification": decision.classification,
    }

    if not decision.allowed:
        return DryRunReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "risk_revalidation": "fail"},
            blocked_reason="blocked_by_risk_revalidation",
            message="Risk revalidation failed.",
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
        )

    gates["risk_revalidation"] = "pass"

    # 15. Compute client_order_id preview (never persisted)
    cid_preview = compute_client_order_id(order_id, payload["order_hash"])

    # 16. Dry-run success
    return DryRunReport(
        ok=True,
        status="dry_run_ready",
        order_id=order_id,
        gates=gates,
        warnings=warnings,
        message="Dry-run passed. Live submit remains disabled.",
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        client_order_id_preview=cid_preview,
    )
