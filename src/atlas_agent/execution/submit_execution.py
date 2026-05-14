from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.brokers.base import BrokerOperationError
from atlas_agent.brokers.live_sync_validation import validate_live_sync
from atlas_agent.brokers.resolver import BrokerResolver
from atlas_agent.brokers.sync import BrokerSyncService
from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidApprovalIdError,
    InvalidPendingOrderError,
)
from atlas_agent.execution.submit_state import (
    compute_client_order_id,
    is_submit_blocked_by_state,
    load_pending_order,
    mark_submit_requested,
)
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput
from atlas_agent.safety.kill_switch import KillSwitchController


@dataclass
class SubmitExecutionReport:
    ok: bool
    status: str
    order_id: str
    blocked_reason: str | None = None
    message: str = ""
    client_order_id: str | None = None
    gates: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    sync: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "order_id": self.order_id,
            "blocked_reason": self.blocked_reason,
            "message": self.message,
            "client_order_id": self.client_order_id,
            "gates": self.gates,
            "warnings": self.warnings,
            "sync": self.sync,
            "risk": self.risk,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_client_order_id(client_order_id: str | None) -> None:
    """Validate a client_order_id against Alpaca requirements."""
    import re as _re
    if not isinstance(client_order_id, str) or not client_order_id:
        raise BrokerOperationError("invalid client_order_id")
    if len(client_order_id) > 64:
        raise BrokerOperationError("invalid client_order_id")
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", client_order_id):
        raise BrokerOperationError("invalid client_order_id")


def _check_expiry(payload: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason) for expiry check."""
    expires_at_raw = payload.get("expires_at")
    if not expires_at_raw:
        return False, "missing expiry"
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except (ValueError, TypeError):
        return False, "invalid expiry"
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        return False, "approval expired"
    return True, ""


def _check_kill_switch(config: Any) -> tuple[bool, str]:
    """Return (ok, reason) for kill-switch check."""
    try:
        controller = KillSwitchController(
            state_path=Path(config.memory_dir) / "kill_switch_state.json",
            enabled_flag_path=Path(config.memory_dir) / "kill_switch.enabled",
        )
        state = controller.status()
    except Exception:
        # If kill switch state is unreadable, fail closed
        return False, "kill switch state unreadable"
    if state.enabled and state.mode != "normal":
        return False, f"kill switch active (mode={state.mode})"
    return True, ""


# ---------------------------------------------------------------------------
# Main execution skeleton
# ---------------------------------------------------------------------------

def run_submit_execution(
    order_id: str,
    config: Any,
    approval_manager: ApprovalManager,
) -> SubmitExecutionReport:
    """Execute the submit-approved-order skeleton up to the can_submit gate.

    Performs all safety gates, fresh live sync, and risk revalidation.
    Fails closed at can_submit=false without calling broker.place_order,
    resolve_execution_broker, or OrderRouter.route.
    Never mutates the pending file. Never persists client_order_id.
    """
    gates: dict[str, str] = {}
    warnings: list[str] = []

    # 1. Validate pending order id
    try:
        path = approval_manager.path_for(order_id)
    except InvalidApprovalIdError:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id="<invalid>",
            gates={"path_traversal": "fail"},
            blocked_reason="invalid_pending_order_id",
            message="Invalid pending order id.",
        )

    if not path.exists():
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={"pending_file": "fail"},
            blocked_reason="pending_order_not_found",
            message="Pending order not found.",
        )
    gates["path_traversal"] = "pass"
    gates["pending_file"] = "pass"

    # 2. Load and validate pending file
    try:
        payload = load_pending_order(path)
    except (InvalidPendingOrderError, json.JSONDecodeError):
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "integrity": "fail"},
            blocked_reason="invalid_pending_order",
            message="Pending order file is invalid or corrupted.",
        )
    gates["integrity"] = "pass"

    # 3. Read current status
    current_status = payload.get("status")

    # 4. Idempotency / terminal-state gate (before approved check)
    if current_status == "submitted":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="already_submitted",
            message="Order has already been submitted.",
        )
    if current_status == "duplicate_reconciled":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="already_reconciled",
            message="Order has already been reconciled.",
        )
    if current_status == "submit_uncertain":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="reconciliation_required",
            message="Order is in submit_uncertain state. Run --reconcile first.",
        )
    if current_status == "reconciliation_required":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="reconciliation_required",
            message="Order requires reconciliation. Run --reconcile first.",
        )
    if current_status == "submit_requested":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="reconciliation_required",
            message="Order is in submit_requested state. Run --reconcile first.",
        )
    if current_status in ("cancelled", "rejected", "expired"):
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="terminal_state",
            message=f"Order is in terminal state: {current_status}.",
        )

    # 5. Require status == "approved"
    if not payload.get("approved") or current_status != "approved":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "approved": "fail"},
            blocked_reason="not_approved",
            message="Order is not approved.",
        )
    gates["approved"] = "pass"

    # 6. Require approval not expired
    expiry_ok, expiry_reason = _check_expiry(payload)
    if not expiry_ok:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "not_expired": "fail"},
            blocked_reason="approval_expired",
            message=f"Approval {expiry_reason}.",
        )
    gates["not_expired"] = "pass"

    # 7. Require live trading enabled
    if not getattr(config, "enable_live_trading", False):
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "live_trading_enabled": "fail"},
            blocked_reason="live_trading_disabled",
            message="Live trading is not enabled.",
        )
    gates["live_trading_enabled"] = "pass"

    # 8. Require kill switch normal
    ks_ok, ks_reason = _check_kill_switch(config)
    if not ks_ok:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "kill_switch": "fail"},
            blocked_reason="kill_switch_active",
            message=f"Kill switch is active: {ks_reason}.",
        )
    gates["kill_switch"] = "pass"

    # 9. Resolve/validate client_order_id
    existing_cid = payload.get("client_order_id")
    if existing_cid is not None:
        try:
            _validate_client_order_id(existing_cid)
        except BrokerOperationError:
            return SubmitExecutionReport(
                ok=False,
                status="blocked",
                order_id=order_id,
                gates={**gates, "client_order_id": "fail"},
                blocked_reason="invalid_client_order_id",
                message="Invalid client_order_id.",
            )
        cid = existing_cid
    else:
        cid = compute_client_order_id(order_id, payload["order_hash"])
    gates["client_order_id"] = "pass"

    # 10. Resolve live sync provider
    resolver = BrokerResolver(config)
    broker_status = resolver.resolve_status("live")
    gates["can_sync"] = "pass" if broker_status.can_sync else "fail"

    if not broker_status.can_sync:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates=gates,
            blocked_reason="broker_sync_unavailable",
            message="Broker sync is not available.",
            client_order_id=cid,
        )

    # 11. Fresh live sync
    resolution = resolver.resolve_sync_provider("live")
    if resolution.sync_provider is None:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "fresh_sync": "fail"},
            blocked_reason="broker_sync_unavailable",
            message="No live sync provider available.",
            client_order_id=cid,
        )

    sync_service = BrokerSyncService(
        broker=resolution.sync_provider,
        audit_writer=None,
        run_id="submit-execution",
    )
    sync_result = sync_service.sync()

    # 12. Validate live sync
    sync_warnings, sync_error = validate_live_sync(sync_result, broker_status)
    if sync_error is not None:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "fresh_sync": "fail"},
            blocked_reason="live_sync_failed",
            message="Live broker sync failed.",
            client_order_id=cid,
            sync={"status": "failed", "warnings": []},
        )

    for w in sync_warnings:
        warnings.append(f"sync warning: {w['operation']}")
    gates["fresh_sync"] = "pass"

    # 13. Convert sync result to PortfolioSnapshot
    portfolio_snapshot = sync_service.get_portfolio_snapshot(
        sync_result, broker_id=broker_status.broker_id
    )

    # 14. Build OrderRiskInput from pending order
    order_dict = payload["order"]
    order_type = order_dict.get("order_type", "market")

    if order_type == "market":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "market_price": "fail"},
            blocked_reason="market_price_unavailable",
            message="Market order submit execution requires a safe quote source before risk revalidation.",
            client_order_id=cid,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

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

    # 15. RiskManager.evaluate_order(..., mode="live")
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
        run_id="submit-execution",
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
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "risk_revalidation": "fail"},
            blocked_reason="risk_revalidation_failed",
            message="Risk revalidation failed.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    gates["risk_revalidation"] = "pass"

    # 16. Check can_submit
    if not broker_status.can_submit:
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "can_submit": "fail"},
            blocked_reason="can_submit_false",
            message="All safety gates passed, but live submit remains disabled.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    gates["can_submit"] = "pass"

    # Batch 4.7: Atomically transition to submit_requested, then hard-block
    # before broker submission. This validates the mutation boundary under
    # mocked can_submit=True while keeping production (can_submit=False) unchanged.
    mark_submit_requested(
        path,
        order_id=order_id,
        client_order_id=cid,
        actor="submit:cli",
    )

    return SubmitExecutionReport(
        ok=False,
        status="blocked",
        order_id=order_id,
        gates={**gates, "broker_submit": "not_implemented"},
        blocked_reason="broker_submit_not_implemented",
        message="Submit state prepared, but broker submission is not implemented in this release.",
        client_order_id=cid,
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        warnings=warnings,
    )
