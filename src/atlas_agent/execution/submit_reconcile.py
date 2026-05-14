from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
from atlas_agent.brokers.base import BrokerConfigurationError, BrokerOperationError
from atlas_agent.brokers.resolver import BrokerResolver
from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidApprovalIdError,
    InvalidPendingOrderError,
)
from atlas_agent.execution.submit_state import (
    load_pending_order,
    mark_duplicate_reconciled,
    mark_reconciliation_required,
)


@dataclass
class ReconcileReport:
    ok: bool
    status: str
    order_id: str
    broker_order_id: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "message": self.message,
        }


def _validate_client_order_id(client_order_id: str | None) -> None:
    """Validate a client_order_id against Alpaca requirements.

    Reimplementation of the helper from alpaca.py to avoid tight coupling.
    """
    import re as _re
    if not isinstance(client_order_id, str) or not client_order_id:
        raise BrokerOperationError("invalid client_order_id")
    if len(client_order_id) > 64:
        raise BrokerOperationError("invalid client_order_id")
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", client_order_id):
        raise BrokerOperationError("invalid client_order_id")


def _is_allowed_reconcile_status(status: str) -> bool:
    return status in ("approved", "submit_uncertain", "reconciliation_required", "duplicate_reconciled")


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


def run_reconcile(
    order_id: str,
    config: Any,
    approval_manager: ApprovalManager,
) -> ReconcileReport:
    """Reconcile an approved pending order against the live broker.

    Queries the broker read-only via AlpacaBrokerAdapter.get_order_by_client_order_id.
    Never calls place_order. Never calls resolve_execution_broker.
    """
    # 1. Validate pending order id
    try:
        path = approval_manager.path_for(order_id)
    except InvalidApprovalIdError:
        return ReconcileReport(
            ok=False,
            status="reconcile_invalid_order_id",
            order_id=order_id,
            message="Invalid pending order id.",
        )

    if not path.exists():
        return ReconcileReport(
            ok=False,
            status="reconcile_not_found",
            order_id=order_id,
            message="Pending order not found.",
        )

    # 2. Load and validate pending file
    try:
        payload = load_pending_order(path)
    except (InvalidPendingOrderError, json.JSONDecodeError):
        return ReconcileReport(
            ok=False,
            status="reconcile_invalid",
            order_id=order_id,
            message="Pending order file is invalid or corrupted.",
        )

    # 3. Require allowed status
    current_status = payload.get("status")
    if not _is_allowed_reconcile_status(current_status):
        return ReconcileReport(
            ok=False,
            status="reconcile_invalid_status",
            order_id=order_id,
            message="Order status does not allow reconciliation.",
        )

    # 3a. Short-circuit if already duplicate_reconciled
    if current_status == "duplicate_reconciled":
        return ReconcileReport(
            ok=True,
            status="duplicate_reconciled",
            order_id=order_id,
            broker_order_id=payload.get("broker_order_id"),
            message="Order is already reconciled. No broker query needed.",
        )

    # 4. Require non-expired approval unless submit_uncertain or reconciliation_required
    if current_status == "approved":
        expiry_ok, expiry_reason = _check_expiry(payload)
        if not expiry_ok:
            return ReconcileReport(
                ok=False,
                status="reconcile_expired",
                order_id=order_id,
                message=f"Approval {expiry_reason}.",
            )

    # 5. Require existing persisted client_order_id
    client_order_id = payload.get("client_order_id")
    if client_order_id is None:
        return ReconcileReport(
            ok=False,
            status="reconcile_not_available",
            order_id=order_id,
            message="No client_order_id is present. No broker submission can be reconciled.",
        )

    # 6. Validate client_order_id before broker query
    try:
        _validate_client_order_id(client_order_id)
    except BrokerOperationError:
        return ReconcileReport(
            ok=False,
            status="reconcile_invalid_client_order_id",
            order_id=order_id,
            message="Invalid client_order_id.",
        )

    # 7. Require live trading enabled before broker contact
    if not getattr(config, "enable_live_trading", False):
        return ReconcileReport(
            ok=False,
            status="reconcile_live_disabled",
            order_id=order_id,
            message="Live trading is not enabled.",
        )

    # 8. Resolve live sync provider
    resolver = BrokerResolver(config)
    resolution = resolver.resolve_sync_provider("live")

    # 9. Require AlpacaBrokerAdapter
    if resolution.sync_provider is None or not isinstance(resolution.sync_provider, AlpacaBrokerAdapter):
        return ReconcileReport(
            ok=False,
            status="reconcile_no_provider",
            order_id=order_id,
            message="Alpaca sync provider is not available.",
        )

    adapter: AlpacaBrokerAdapter = resolution.sync_provider

    # 10. Query broker (read-only GET)
    try:
        broker_order = adapter.get_order_by_client_order_id(client_order_id)
    except BrokerConfigurationError:
        return ReconcileReport(
            ok=False,
            status="reconcile_broker_config_error",
            order_id=order_id,
            message="Broker not configured.",
        )
    except BrokerOperationError as exc:
        error_msg = str(exc)
        if "order not found" in error_msg:
            # Not found — do not submit, do not mark submitted
            if current_status in ("submit_uncertain", "reconciliation_required"):
                # Keep or ensure reconciliation_required
                mark_reconciliation_required(path, "broker order not found during reconcile")
                return ReconcileReport(
                    ok=False,
                    status="reconcile_not_found",
                    order_id=order_id,
                    message="No broker order found. Manual review required before retry.",
                )
            return ReconcileReport(
                ok=False,
                status="reconcile_not_found",
                order_id=order_id,
                message="No broker order found for this client_order_id.",
            )
        # Transport / malformed / other broker error
        if current_status in ("submit_uncertain", "reconciliation_required", "approved"):
            mark_reconciliation_required(path, "broker query failed during reconcile")
        return ReconcileReport(
            ok=False,
            status="reconcile_failed",
            order_id=order_id,
            message="Broker query failed. Reconciliation required.",
        )
    except Exception:
        # Catch-all for unexpected errors
        if current_status in ("submit_uncertain", "reconciliation_required", "approved"):
            mark_reconciliation_required(path, "unexpected error during reconcile")
        return ReconcileReport(
            ok=False,
            status="reconcile_failed",
            order_id=order_id,
            message="Reconciliation failed. Reconciliation required.",
        )

    # 11. Broker order found
    if current_status == "duplicate_reconciled" and payload.get("broker_order_id") == broker_order.order_id:
        return ReconcileReport(
            ok=True,
            status="duplicate_reconciled",
            order_id=order_id,
            broker_order_id=broker_order.order_id,
            message="Broker order found and reconciled. No duplicate submit needed.",
        )

    mark_duplicate_reconciled(
        path,
        broker_order_id=broker_order.order_id,
        broker_status=broker_order.status,
    )
    return ReconcileReport(
        ok=True,
        status="duplicate_reconciled",
        order_id=order_id,
        broker_order_id=broker_order.order_id,
        message="Broker order found and reconciled. No duplicate submit needed.",
    )
