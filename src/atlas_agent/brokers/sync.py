from __future__ import annotations

import logging
from typing import Optional, List, Literal

from atlas_agent.audit import AuditWriter
from atlas_agent.brokers.base import BrokerProvider
from atlas_agent.brokers.errors import make_broker_error
from atlas_agent.brokers.models import BrokerSyncResult, BrokerPosition, BrokerOrder
from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition, PendingOrder


class BrokerSyncService:
    def __init__(
        self,
        broker: BrokerProvider,
        audit_writer: Optional[AuditWriter] = None,
        run_id: str = "unknown",
        iteration: Optional[int] = None,
    ):
        self.broker = broker
        self.audit_writer = audit_writer
        self.run_id = run_id
        self.iteration = iteration

    def sync(self) -> BrokerSyncResult:
        if self.audit_writer:
            self.audit_writer.write_event(
                "broker_sync_started",
                run_id=self.run_id,
                iteration=self.iteration,
                payload={"broker_type": type(self.broker).__name__}
            )

        errors = []
        broker_errors: list[dict[str, str]] = []
        account = None
        positions = []
        open_orders = []
        balances = []

        try:
            account = self.broker.get_account_state()
        except Exception as exc:
            broker_error = make_broker_error(
                operation="sync_account_state",
                broker=self.broker,
                exc=exc,
            )
            errors.append(broker_error.to_error_string())
            broker_errors.append(broker_error.to_dict())

        try:
            positions = self.broker.get_positions()
        except Exception as exc:
            broker_error = make_broker_error(
                operation="sync_positions",
                broker=self.broker,
                exc=exc,
            )
            errors.append(broker_error.to_error_string())
            broker_errors.append(broker_error.to_dict())

        try:
            open_orders = self.broker.get_open_orders()
        except Exception as exc:
            broker_error = make_broker_error(
                operation="sync_open_orders",
                broker=self.broker,
                exc=exc,
            )
            errors.append(broker_error.to_error_string())
            broker_errors.append(broker_error.to_dict())

        try:
            balances = self.broker.get_balances()
        except Exception as exc:
            broker_error = make_broker_error(
                operation="sync_balances",
                broker=self.broker,
                exc=exc,
            )
            errors.append(broker_error.to_error_string())
            broker_errors.append(broker_error.to_dict())

        status: Literal["success", "partial", "failed"] = "success"
        if errors:
            has_some_data = (
                account is not None or 
                len(positions) > 0 or 
                len(open_orders) > 0 or 
                len(balances) > 0 or
                (len(errors) < 4) # If some succeeded without data
            )
            if has_some_data:
                status = "partial"
            else:
                status = "failed"

        result = BrokerSyncResult(
            status=status,
            account=account,
            positions=positions,
            open_orders=open_orders,
            balances=balances,
            errors=errors,
            diagnostics={"broker_errors": broker_errors},
        )

        if self.audit_writer:
            event_type = "broker_sync_completed" if status == "success" else f"broker_sync_{status}"
            self.audit_writer.write_event(
                event_type, # type: ignore
                run_id=self.run_id,
                iteration=self.iteration,
                payload={
                    "status": status,
                    "position_count": len(positions),
                    "open_order_count": len(open_orders),
                    "error_count": len(errors)
                }
            )

        return result

    def get_portfolio_snapshot(
        self,
        sync_result: BrokerSyncResult,
        broker_id: str | None = None,
    ) -> PortfolioSnapshot:
        """
        Convert sync result into Risk-ready PortfolioSnapshot.
        """
        acc = sync_result.account

        # Risk-ready positions
        risk_positions = [
            RiskPosition(
                symbol=p.symbol,
                quantity=p.quantity,
                average_price=p.average_price,
                market_price=p.market_price or p.average_price,
                notional=abs(p.quantity * (p.market_price or p.average_price)),
                side=p.side
            )
            for p in sync_result.positions
        ]

        # Risk-ready pending orders
        pending_orders = [
            PendingOrder(
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                quantity=o.quantity,
                limit_price=o.limit_price,
                status=o.status,
                filled_quantity=o.filled_quantity
            )
            for o in sync_result.open_orders
        ]

        equity = acc.equity if acc else 0.0
        exposure = sum(p.notional for p in risk_positions)

        return PortfolioSnapshot(
            cash=acc.cash if acc else 0.0,
            equity=equity,
            total_exposure=exposure,
            positions=risk_positions,
            open_orders=pending_orders,
            synced_at=sync_result.synced_at,
            sync_status=sync_result.status,
            sync_source="broker_sync",
            broker_id=broker_id,
        )
