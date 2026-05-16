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
from atlas_agent.execution.order import Order
from atlas_agent.execution.quotes import (
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    MarketQuote,
    QuoteProvider,
    conservative_price_for_side,
    validate_market_quote,
)
from atlas_agent.execution.submit_state import (
    compute_client_order_id,
    is_submit_blocked_by_state,
    load_pending_order,
    mark_acknowledged,
    mark_submit_failed,
    mark_submit_prepare_failed,
    mark_submit_requested,
    mark_submit_uncertain,
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


def _reconstruct_order(order_dict: dict[str, Any]) -> Order:
    """Reconstruct an Order from a pending payload order dict.

    The pending payload stores created_at as an ISO string; parse it back
    to a datetime before constructing the Order dataclass.
    """
    from copy import deepcopy

    d = deepcopy(order_dict)
    created_at_raw = d.get("created_at")
    if isinstance(created_at_raw, str):
        d["created_at"] = datetime.fromisoformat(created_at_raw)
    return Order(**d)


def _broker_error_code(exc: BrokerOperationError) -> str:
    """Map BrokerOperationError static messages to safe internal error codes.

    Exact matching only.
    No substring routing.
    Unknown messages become "unknown".
    """
    msg = str(exc)

    if msg == "broker rejected order":
        return "broker_rejected_order"
    if msg == "broker unavailable":
        return "broker_unavailable"
    if msg == "broker transport request failed":
        return "broker_transport_failed"
    if msg == "malformed broker response":
        return "malformed_broker_response"
    if msg == "client_order_id mismatch":
        return "client_order_id_mismatch"

    return "unknown"


def _broker_rejected_report(
    order_id: str,
    cid: str,
    gates: dict[str, str],
    risk_dict: dict[str, Any] | None,
    sync_warnings: list[str],
    warnings: list[str],
) -> SubmitExecutionReport:
    return SubmitExecutionReport(
        ok=False,
        status="blocked",
        order_id=order_id,
        gates={**gates, "broker_submit": "rejected"},
        blocked_reason="broker_rejected_order",
        message="Broker rejected order.",
        client_order_id=cid,
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        warnings=warnings,
    )


def _reconciliation_required_report(
    order_id: str,
    cid: str,
    gates: dict[str, str],
    risk_dict: dict[str, Any] | None,
    sync_warnings: list[str],
    warnings: list[str],
) -> SubmitExecutionReport:
    return SubmitExecutionReport(
        ok=False,
        status="blocked",
        order_id=order_id,
        gates={**gates, "broker_submit": "uncertain"},
        blocked_reason="reconciliation_required",
        message="Broker response received, but local state update failed. Run --reconcile first.",
        client_order_id=cid,
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        warnings=warnings,
    )


def _ack_local_write_failed_report(
    order_id: str,
    cid: str,
    gates: dict[str, str],
    risk_dict: dict[str, Any] | None,
    sync_warnings: list[str],
    warnings: list[str],
) -> SubmitExecutionReport:
    return SubmitExecutionReport(
        ok=False,
        status="blocked",
        order_id=order_id,
        gates={**gates, "broker_submit": "uncertain"},
        blocked_reason="reconciliation_required",
        message="Broker acknowledged order, but local state update failed. Run --reconcile first.",
        client_order_id=cid,
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        warnings=warnings,
    )


def _uncertain_report(
    order_id: str,
    cid: str,
    gates: dict[str, str],
    risk_dict: dict[str, Any] | None,
    sync_warnings: list[str],
    warnings: list[str],
) -> SubmitExecutionReport:
    return SubmitExecutionReport(
        ok=False,
        status="blocked",
        order_id=order_id,
        gates={**gates, "broker_submit": "uncertain"},
        blocked_reason="reconciliation_required",
        message="Broker submission outcome is uncertain. Run --reconcile first.",
        client_order_id=cid,
        risk=risk_dict,
        sync={"status": "success", "warnings": sync_warnings},
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Main execution skeleton
# ---------------------------------------------------------------------------

def _emit_live_submit_blocked(
    audit_writer: Any,
    order_id: str,
    client_order_id: str | None,
    broker_id: str,
    blocked_reason: str,
    gate: str,
) -> None:
    """Best-effort audit emission for live-submit blocked events.

    Never raises. Never leaks raw values.
    """
    if audit_writer is None:
        return
    try:
        audit_writer.write_event(
            "live_submit_blocked",
            run_id="submit-execution",
            payload={
                "mode": "live",
                "broker_id": broker_id,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "reason_code": blocked_reason,
                "gate": gate,
                "status": "blocked",
            },
        )
    except Exception:
        pass


def _emit_live_submit_attempted(
    audit_writer: Any,
    order_id: str,
    client_order_id: str,
    broker_id: str,
) -> None:
    """Best-effort audit emission for live-submit attempted events.

    Emitted immediately before broker.place_order.
    Never raises. Never leaks raw values.
    """
    if audit_writer is None:
        return
    try:
        audit_writer.write_event(
            "live_submit_attempted",
            run_id="submit-execution",
            payload={
                "mode": "live",
                "broker_id": broker_id,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "status": "attempted",
            },
        )
    except Exception:
        pass


def run_submit_execution(
    order_id: str,
    config: Any,
    approval_manager: ApprovalManager,
    audit_writer: Any | None = None,
    quote_provider: QuoteProvider | None = None,
) -> SubmitExecutionReport:
    """Execute the submit-approved-order skeleton through the broker boundary.

    Performs all safety gates, fresh live sync, and risk revalidation.

    Production path (can_submit=false, default):
      - Remains read-only and does not mutate pending files.
      - Fails closed before broker.place_order, resolve_execution_broker,
        or OrderRouter.route.

    Opt-in live path (can_submit=true):
      - Requires broker.enable_live_submit=true plus all multi-factor opt-in
        conditions (kill switch normal, trading_mode=live, live trading enabled,
        approval not disabled, leverage off, credentials present, valid opt-in
        audit record, live-submit hard limits satisfied).
      - May prepare submit_requested state and proceed through the broker
        submit boundary (reconstruct Order, resolve execution broker,
        place_order, map response).
      - Only reachable after explicit CLI opt-in with typed confirmation.

    This is the ONLY function permitted to call resolve_execution_broker("live")
    for live submissions. No other CLI or runtime path may do so.
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
        _emit_live_submit_blocked(
            audit_writer, order_id, None,
            getattr(config, "live_broker", "none"),
            "invalid_pending_order", "integrity",
        )
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
    if current_status == "acknowledged":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="already_submitted",
            message="Order has already been submitted.",
        )
    if current_status == "submit_prepare_failed":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="submit_prepare_failed",
            message="Order preparation failed. Review config and retry.",
        )
    if current_status == "failed":
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "idempotency": "fail"},
            blocked_reason="submit_failed",
            message="Order is in a terminal failed state.",
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
        _emit_live_submit_blocked(
            audit_writer, order_id, None,
            getattr(config, "live_broker", "none"),
            "live_trading_disabled", "live_trading_enabled",
        )
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
        _emit_live_submit_blocked(
            audit_writer, order_id, None,
            getattr(config, "live_broker", "none"),
            "kill_switch_active", "kill_switch",
        )
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
            _emit_live_submit_blocked(
                audit_writer, order_id, None,
                getattr(config, "live_broker", "none"),
                "invalid_client_order_id", "client_order_id",
            )
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
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "broker_sync_unavailable", "can_sync",
        )
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
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "broker_sync_unavailable", "fresh_sync",
        )
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
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "live_sync_failed", "fresh_sync",
        )
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
        quote_ok = False
        quote_reason = "market_price_unavailable"
        if quote_provider is not None:
            try:
                quote = quote_provider.get_quote(order_dict["symbol"])
                quote_ok, quote_reason = validate_market_quote(
                    quote,
                    expected_symbol=order_dict["symbol"],
                    max_age_seconds=getattr(
                        config, "max_quote_age_seconds", DEFAULT_MAX_QUOTE_AGE_SECONDS
                    ),
                )
                if quote_ok and quote is not None:
                    try:
                        price = conservative_price_for_side(quote, order_dict["side"])
                    except ValueError:
                        quote_ok = False
                        quote_reason = "market_quote_invalid"
            except Exception:
                quote_ok = False
                quote_reason = "market_quote_unavailable"

        if not quote_ok:
            _emit_live_submit_blocked(
                audit_writer, order_id, cid,
                broker_status.broker_id,
                quote_reason, "market_price",
            )
            return SubmitExecutionReport(
                ok=False,
                status="blocked",
                order_id=order_id,
                gates={**gates, "market_price": "fail"},
                blocked_reason=quote_reason,
                message="Market order requires a fresh validated quote.",
                client_order_id=cid,
                sync={"status": "success", "warnings": sync_warnings},
                warnings=warnings,
            )

        # quote_ok is True and price was set above
        # type ignore because mypy does not see the quote assignment path
        price = float(price)  # type: ignore[has-type]
        gates["market_price"] = "pass"
    else:
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
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "risk_revalidation_failed", "risk_revalidation",
        )
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

    # 16. Live-submit hard limits revalidation (defense-in-depth)
    # Only evaluated when broker_status.can_submit is true.
    # If any limit fails, the pending file MUST remain unchanged.
    if broker_status.can_submit:
        live_submit_max = (
            config.risk.live_submit_max_order_notional
            or config.risk.max_order_notional
        )
        if risk_input.notional > live_submit_max:
            _emit_live_submit_blocked(
                audit_writer, order_id, cid,
                broker_status.broker_id,
                "live_submit_max_notional_exceeded", "live_submit_limits",
            )
            return SubmitExecutionReport(
                ok=False,
                status="blocked",
                order_id=order_id,
                gates={**gates, "live_submit_limits": "fail"},
                blocked_reason="live_submit_max_notional_exceeded",
                message="Order notional exceeds live submit hard limit.",
                client_order_id=cid,
                risk=risk_dict,
                sync={"status": "success", "warnings": sync_warnings},
                warnings=warnings,
            )

        live_submit_symbols = (
            config.risk.live_submit_allowed_symbols
            or config.risk.symbol_allowlist
        )
        if live_submit_symbols is not None:
            normalized_symbols = {str(s).upper() for s in live_submit_symbols}
            if risk_input.symbol.upper() not in normalized_symbols:
                _emit_live_submit_blocked(
                    audit_writer, order_id, cid,
                    broker_status.broker_id,
                    "live_submit_symbol_not_allowed", "live_submit_limits",
                )
                return SubmitExecutionReport(
                    ok=False,
                    status="blocked",
                    order_id=order_id,
                    gates={**gates, "live_submit_limits": "fail"},
                    blocked_reason="live_submit_symbol_not_allowed",
                    message="Symbol is not in the live submit allowlist.",
                    client_order_id=cid,
                    risk=risk_dict,
                    sync={"status": "success", "warnings": sync_warnings},
                    warnings=warnings,
                )

        live_submit_sides = config.risk.live_submit_allowed_sides
        if live_submit_sides is not None and risk_input.side.lower() not in {s.lower() for s in live_submit_sides}:
            _emit_live_submit_blocked(
                audit_writer, order_id, cid,
                broker_status.broker_id,
                "live_submit_side_not_allowed", "live_submit_limits",
            )
            return SubmitExecutionReport(
                ok=False,
                status="blocked",
                order_id=order_id,
                gates={**gates, "live_submit_limits": "fail"},
                blocked_reason="live_submit_side_not_allowed",
                message="Order side is not allowed for live submit.",
                client_order_id=cid,
                risk=risk_dict,
                sync={"status": "success", "warnings": sync_warnings},
                warnings=warnings,
            )

        gates["live_submit_limits"] = "pass"

    # 17. Check can_submit
    if not broker_status.can_submit:
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "can_submit_false", "can_submit",
        )
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

    # Reconstruct Order before any mutation.
    try:
        order = _reconstruct_order(payload["order"])
    except Exception:
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "invalid_pending_order", "order_reconstruction",
        )
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "order_reconstruction": "fail"},
            blocked_reason="invalid_pending_order",
            message="Pending order file is invalid or corrupted.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    # Crash-recovery anchor.
    try:
        mark_submit_requested(
            path,
            order_id=order_id,
            client_order_id=cid,
            actor="submit:cli",
        )
    except Exception:
        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "submit_state_mutation_failed", "submit_state_mutation",
        )
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "submit_state_mutation": "fail"},
            blocked_reason="submit_state_mutation_failed",
            message="Submit state could not be prepared.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    resolution = resolver.resolve_execution_broker("live")
    execution_broker = resolution.execution_broker

    if execution_broker is None:
        try:
            mark_submit_prepare_failed(
                path,
                error_code="execution_broker_unavailable",
                now=datetime.now(UTC),
            )
        except Exception:
            pass

        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "execution_broker_unavailable", "execution_broker",
        )
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "execution_broker": "unavailable"},
            blocked_reason="execution_broker_unavailable",
            message="Execution broker is not available.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    if not callable(getattr(execution_broker, "place_order", None)):
        try:
            mark_submit_prepare_failed(
                path,
                error_code="execution_broker_invalid",
                now=datetime.now(UTC),
            )
        except Exception:
            pass

        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "execution_broker_invalid", "execution_broker",
        )
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "execution_broker": "invalid"},
            blocked_reason="execution_broker_invalid",
            message="Execution broker is not valid.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    # Final kill switch check immediately before broker contact.
    ks_ok, _ks_reason = _check_kill_switch(config)
    if not ks_ok:
        try:
            mark_submit_prepare_failed(
                path,
                error_code="kill_switch_active",
                now=datetime.now(UTC),
            )
        except Exception:
            pass

        _emit_live_submit_blocked(
            audit_writer, order_id, cid,
            broker_status.broker_id,
            "kill_switch_active", "kill_switch",
        )
        return SubmitExecutionReport(
            ok=False,
            status="blocked",
            order_id=order_id,
            gates={**gates, "kill_switch": "fail"},
            blocked_reason="kill_switch_active",
            message="Kill switch is active.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    _emit_live_submit_attempted(
        audit_writer, order_id, cid, broker_status.broker_id,
    )
    try:
        result = execution_broker.place_order(order, client_order_id=cid)

    except BrokerOperationError as exc:
        code = _broker_error_code(exc)

        if code == "broker_rejected_order":
            try:
                mark_submit_failed(
                    path,
                    error_code=code,
                    now=datetime.now(UTC),
                )
                return _broker_rejected_report(
                    order_id,
                    cid,
                    gates,
                    risk_dict,
                    sync_warnings,
                    warnings,
                )
            except Exception:
                try:
                    mark_submit_uncertain(
                        path,
                        error_code="unknown",
                        now=datetime.now(UTC),
                    )
                except Exception:
                    pass

                return _reconciliation_required_report(
                    order_id,
                    cid,
                    gates,
                    risk_dict,
                    sync_warnings,
                    warnings,
                )

        try:
            mark_submit_uncertain(
                path,
                error_code=code,
                now=datetime.now(UTC),
            )
            return _uncertain_report(
                order_id,
                cid,
                gates,
                risk_dict,
                sync_warnings,
                warnings,
            )
        except Exception:
            pass

        return _reconciliation_required_report(
            order_id,
            cid,
            gates,
            risk_dict,
            sync_warnings,
            warnings,
        )

    except Exception:
        try:
            mark_submit_uncertain(
                path,
                error_code="unknown",
                now=datetime.now(UTC),
            )
            return _uncertain_report(
                order_id,
                cid,
                gates,
                risk_dict,
                sync_warnings,
                warnings,
            )
        except Exception:
            pass

        return _reconciliation_required_report(
            order_id,
            cid,
            gates,
            risk_dict,
            sync_warnings,
            warnings,
        )

    # Map normal result.
    if result.accepted and result.order_id:
        try:
            mark_acknowledged(
                path,
                broker_order_id=result.order_id,
                broker_status=result.status,
                now=datetime.now(UTC),
            )
        except Exception:
            try:
                mark_submit_uncertain(
                    path,
                    error_code="unknown",
                    now=datetime.now(UTC),
                )
            except Exception:
                pass

            return _ack_local_write_failed_report(
                order_id,
                cid,
                gates,
                risk_dict,
                sync_warnings,
                warnings,
            )

        return SubmitExecutionReport(
            ok=True,
            status="acknowledged",
            order_id=order_id,
            gates={**gates, "broker_submit": "acknowledged"},
            blocked_reason=None,
            message="Broker acknowledged order.",
            client_order_id=cid,
            risk=risk_dict,
            sync={"status": "success", "warnings": sync_warnings},
            warnings=warnings,
        )

    # accepted=True but missing broker_order_id — malformed broker response.
    if result.accepted:
        try:
            mark_submit_uncertain(
                path,
                error_code="malformed_broker_response",
                now=datetime.now(UTC),
            )
            return _uncertain_report(
                order_id,
                cid,
                gates,
                risk_dict,
                sync_warnings,
                warnings,
            )
        except Exception:
            pass

        return _reconciliation_required_report(
            order_id,
            cid,
            gates,
            risk_dict,
            sync_warnings,
            warnings,
        )

    # accepted=False.
    try:
        mark_submit_failed(
            path,
            error_code="broker_rejected_order",
            now=datetime.now(UTC),
        )
        return _broker_rejected_report(
            order_id,
            cid,
            gates,
            risk_dict,
            sync_warnings,
            warnings,
        )
    except Exception:
        try:
            mark_submit_uncertain(
                path,
                error_code="unknown",
                now=datetime.now(UTC),
            )
        except Exception:
            pass

        return _reconciliation_required_report(
            order_id,
            cid,
            gates,
            risk_dict,
            sync_warnings,
            warnings,
        )
