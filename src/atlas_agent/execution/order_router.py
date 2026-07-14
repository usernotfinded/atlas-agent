# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/order_router.py
# PURPOSE: The gauntlet every order runs before it reaches a broker. Enforces the
#          project's central invariant — nothing is submitted that has not passed,
#          in this order: input validation → RiskManager → approval → broker.
# DEPS:    risk.manager (mandatory gate), execution.approval (human gate),
#          brokers.base (the only exit), events.log + execution.audit (the record)
# ==============================================================================

# --- IMPORTS ---
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


# ==============================================================================
# ORDER ROUTER
# ==============================================================================

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
        """Route an order through every gate. The only path to a broker.

        Returns:
            An OrderResult. Rejections are RETURNED, never raised — a blocked order
            is a normal outcome of a working safety system, not an exceptional one,
            and callers must be able to log it without a try/except.
        """
        # --- Gate 1: input sanity -------------------------------------------------
        # Rejected here, before risk ever sees it. A NaN quantity would slip past every
        # downstream limit check (NaN > max is False, so it violates nothing), so it has
        # to die at the door rather than be caught by a comparison that cannot catch it.
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
        # --- Gate 2: risk ---------------------------------------------------------
        # Mandatory and unconditional. There is no config flag, no mode and no caller
        # that can skip this call — that is the invariant the whole project rests on
        # ("RiskManager is mandatory before broker execution", safety/policy.py).
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

        # --- Gate 3: live-only locks ----------------------------------------------
        # Everything below applies to live mode ONLY. Paper orders skip straight to the
        # broker, which is the point: paper is where the agent is allowed to be wrong.
        if mode == "live":
            # The config gates are re-read HERE, at submit time, rather than trusted from
            # startup. A kill switch tripped or a flag flipped while this order was in
            # flight must still stop it.
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
            # An allowlist of exactly one value. Any other approval mode — including one
            # that would auto-approve — is REJECTED rather than honoured: on the live
            # path, "I don't recognise this policy" must mean no, not yes.
            if self.config.order_approval_mode != "manual_live":
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="rejected",
                    message="unsupported live approval mode",
                )
            # --- Gate 4: human approval -------------------------------------------
            # Unapproved live orders are PARKED, not dropped: written to disk as pending
            # so a human can review and approve them out of band. The order does not
            # proceed on this pass, and the caller is told so.
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

        # --- The broker call: the point of no return -------------------------------
        # Everything above this line is reversible. Once place_order() is entered, an
        # order may exist at the venue even if we never see the response — which is why
        # a broker exception below is reported as status="failed" (outcome UNKNOWN) and
        # never as "rejected" (outcome known: nothing happened). Reconciliation, not
        # this function, is what resolves a failed submit.
        try:
            result = broker.place_order(order)
        except Exception as exc:
            # Sanitised before it touches a log line: broker exceptions carry request
            # bodies and API keys.
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
