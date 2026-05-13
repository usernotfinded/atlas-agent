from __future__ import annotations

import math
from dataclasses import dataclass

from atlas_agent.brokers.base import Broker
from atlas_agent.brokers.errors import make_broker_error
from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger
from atlas_agent.execution.approval import ApprovalManager
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import Order, OrderResult
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.manager import RiskManager


@dataclass
class OrderRouter:
    config: AtlasConfig
    risk_manager: RiskManager
    approval_manager: ApprovalManager
    audit: AuditLogger

    def route(
        self,
        order: Order,
        *,
        mode: str,
        broker: Broker,
        portfolio: PortfolioState,
        market_price: float,
        market_is_open: bool = True,
        event_logger: EventLogger | None = None,
        run_id: str | None = None,
        command: str = "atlas run-once",
    ) -> OrderResult:
        if isinstance(order.quantity, bool) or not isinstance(order.quantity, (int, float)) or not math.isfinite(order.quantity) or order.quantity <= 0:
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="order quantity must be a positive finite number",
                reasons=("invalid_quantity",),
            )
        if order.limit_price is not None and (isinstance(order.limit_price, bool) or not isinstance(order.limit_price, (int, float)) or not math.isfinite(order.limit_price) or order.limit_price <= 0):
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="limit price must be a positive finite number",
                reasons=("invalid_limit_price",),
            )
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "order_created",
                run_id=run_id,
                command=command,
                mode=mode,
                payload={
                    "order_id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                },
            )
        decision = self.risk_manager.validate_order(
            order,
            portfolio,
            mode=mode,
            market_price=market_price,
            market_is_open=market_is_open,
        )
        if not decision.allowed:
            if event_logger is not None and run_id is not None:
                event_logger.write(
                    "risk_rejected",
                    run_id=run_id,
                    command=command,
                    mode=mode,
                    payload={"order_id": order.id, "reasons": list(decision.reasons)},
                )
                event_logger.write(
                    "order_rejected",
                    run_id=run_id,
                    command=command,
                    mode=mode,
                    payload={"order_id": order.id, "reasons": list(decision.reasons)},
                )
            self.audit.write(
                "order_rejected",
                {"order_id": order.id, "reasons": decision.reasons},
            )
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="risk manager rejected order",
                reasons=decision.reasons,
            )
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "risk_approved",
                run_id=run_id,
                command=command,
                mode=mode,
                payload={"order_id": order.id},
            )

        if mode == "live":
            live_reasons = self.config.live_disabled_reasons()
            if live_reasons:
                if event_logger is not None and run_id is not None:
                    event_logger.write(
                        "order_rejected",
                        run_id=run_id,
                        command=command,
                        mode=mode,
                        payload={"order_id": order.id, "reasons": list(live_reasons)},
                    )
                self.audit.write(
                    "live_order_rejected",
                    {"order_id": order.id, "reasons": live_reasons},
                )
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="rejected",
                    message="live trading gates failed",
                    reasons=live_reasons,
                )
            if self.config.order_approval_mode != "manual_live":
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="rejected",
                    message="unsupported live approval mode",
                )
            if not self.approval_manager.is_approved(order.id):
                pending_path = self.approval_manager.create_pending_order(order)
                if event_logger is not None and run_id is not None:
                    event_logger.write(
                        "order_pending_approval",
                        run_id=run_id,
                        command=command,
                        mode=mode,
                        payload={"order_id": order.id, "path": str(pending_path)},
                    )
                self.audit.write(
                    "pending_live_order_created",
                    {"order_id": order.id, "path": str(pending_path)},
                )
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="pending_approval",
                    message=f"live order pending approval: {pending_path}",
                )

        try:
            result = broker.place_order(order)
        except Exception as exc:
            broker_error = make_broker_error(
                operation="place_order",
                broker=broker,
                exc=exc,
            )
            if event_logger is not None and run_id is not None:
                event_logger.write(
                    "order_rejected",
                    run_id=run_id,
                    command=command,
                    mode=mode,
                    payload={
                        "order_id": order.id,
                        "status": "failed",
                        "broker_error": broker_error.to_dict(),
                    },
                )
            self.audit.write(
                "broker_order_result",
                {
                    "order_id": order.id,
                    "status": "failed",
                    "filled": False,
                    "broker_error": broker_error.to_dict(),
                },
            )
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="failed",
                message=broker_error.message,
                reasons=(broker_error.code, f"operation={broker_error.operation}", f"broker={broker_error.broker}"),
            )
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "order_executed" if result.filled else "order_rejected",
                run_id=run_id,
                command=command,
                mode=mode,
                payload={
                    "order_id": order.id,
                    "status": result.status,
                    "message": result.message,
                },
            )
        self.audit.write(
            "broker_order_result",
            {"order_id": order.id, "status": result.status, "filled": result.filled},
        )
        return result
