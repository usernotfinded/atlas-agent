from __future__ import annotations

from dataclasses import dataclass

from omni_trade_ai.brokers.base import Broker
from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.approval import ApprovalManager
from omni_trade_ai.execution.audit import AuditLogger
from omni_trade_ai.execution.order import Order, OrderResult
from omni_trade_ai.portfolio.state import PortfolioState
from omni_trade_ai.risk.manager import RiskManager


@dataclass
class OrderRouter:
    config: OmniTradeConfig
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
    ) -> OrderResult:
        decision = self.risk_manager.validate_order(
            order,
            portfolio,
            mode=mode,
            market_price=market_price,
            market_is_open=market_is_open,
        )
        if not decision.allowed:
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

        if mode == "live":
            live_reasons = self.config.live_disabled_reasons()
            if live_reasons:
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

        result = broker.place_order(order)
        self.audit.write(
            "broker_order_result",
            {"order_id": order.id, "status": result.status, "filled": result.filled},
        )
        return result

