from __future__ import annotations

from typing import Any, List, Optional, Literal
from uuid import uuid4

from atlas_agent.risk.models import PortfolioSnapshot, OrderRiskInput, RiskPosition
from atlas_agent.risk.manager import RiskManager
from atlas_agent.safety.models import (
    SafetyAction, 
    SafetyActionPlan, 
    KillSwitchDecision, 
    KillSwitchMode
)


class SafetyActionPlanner:
    def __init__(
        self, 
        risk_manager: Optional[RiskManager] = None,
        allow_auto_paper_actions: bool = False
    ):
        self.risk_manager = risk_manager
        self.allow_auto_paper_actions = allow_auto_paper_actions

    def create_plan(
        self,
        decision: KillSwitchDecision,
        portfolio: PortfolioSnapshot,
        open_order_ids: List[str],
        mode: Literal["paper", "live"] = "paper"
    ) -> SafetyActionPlan:
        plan_id = str(uuid4())
        ks_mode = decision.mode
        
        if ks_mode == "locked_down":
            return self._plan_lockdown(plan_id, ks_mode)
            
        if ks_mode == "cancel_all":
            return self._plan_cancel_all(plan_id, ks_mode, open_order_ids, mode)
            
        if ks_mode == "flatten_all":
            return self._plan_flatten_all(plan_id, ks_mode, portfolio, mode)
            
        if ks_mode == "soft_pause":
            return self._plan_soft_pause(plan_id, ks_mode)
            
        # Normal mode
        return SafetyActionPlan(
            plan_id=plan_id,
            mode=ks_mode,
            status="planned",
            reason="Normal operation, no safety actions required.",
            actions=[SafetyAction(type="no_op", description="No action required")],
            requires_approval=False
        )

    def _plan_lockdown(self, plan_id: str, mode: KillSwitchMode) -> SafetyActionPlan:
        return SafetyActionPlan(
            plan_id=plan_id,
            mode=mode,
            status="blocked",
            reason="System is in locked_down mode. All execution-sensitive actions are blocked.",
            actions=[SafetyAction(type="notify_user", description="System locked down", params={"priority": "high"})],
            requires_approval=True
        )

    def _plan_cancel_all(
        self, 
        plan_id: str, 
        mode: KillSwitchMode, 
        open_order_ids: List[str],
        run_mode: str
    ) -> SafetyActionPlan:
        if not open_order_ids:
            return SafetyActionPlan(
                plan_id=plan_id,
                mode=mode,
                status="planned",
                reason="Cancel all requested, but no open orders were found.",
                actions=[SafetyAction(type="no_op", description="No open orders to cancel")],
                requires_approval=False
            )
            
        actions = []
        for order_id in open_order_ids:
            actions.append(SafetyAction(
                type="cancel_order",
                description=f"Cancel order {order_id}",
                params={"order_id": order_id}
            ))
            
        requires_approval = not (run_mode == "paper" and self.allow_auto_paper_actions)
        
        return SafetyActionPlan(
            plan_id=plan_id,
            mode=mode,
            status="requires_approval" if requires_approval else "planned",
            reason=f"Found {len(open_order_ids)} open orders to cancel.",
            actions=actions,
            requires_approval=requires_approval
        )

    def _plan_flatten_all(
        self, 
        plan_id: str, 
        mode: KillSwitchMode, 
        portfolio: PortfolioSnapshot,
        run_mode: str
    ) -> SafetyActionPlan:
        if not portfolio.positions:
            return SafetyActionPlan(
                plan_id=plan_id,
                mode=mode,
                status="planned",
                reason="Flatten all requested, but no open positions were found.",
                actions=[SafetyAction(type="no_op", description="No positions to flatten")],
                requires_approval=False
            )
            
        actions = []
        requires_approval = not (run_mode == "paper" and self.allow_auto_paper_actions)
        
        for pos in portfolio.positions:
            # Generate flatten action
            side = "sell" if pos.quantity > 0 else "buy"
            actions.append(SafetyAction(
                type="flatten_position",
                description=f"Flatten {pos.symbol} ({pos.quantity} units)",
                params={
                    "symbol": pos.symbol,
                    "quantity": abs(pos.quantity),
                    "side": side
                }
            ))
            
            # Verify risk reduction if RiskManager is available
            if self.risk_manager:
                risk_input = OrderRiskInput(
                    symbol=pos.symbol,
                    side=side,
                    quantity=abs(pos.quantity),
                    price=pos.market_price,
                    notional=abs(pos.quantity * pos.market_price)
                )
                decision = self.risk_manager.evaluate_order(risk_input, portfolio, mode=run_mode) # type: ignore
                if not decision.allowed or decision.classification not in ["reduces_risk", "closes_position"]:
                    # This should basically never happen if the logic is correct
                    return SafetyActionPlan(
                        plan_id=plan_id,
                        mode=mode,
                        status="failed",
                        reason=f"Safety check failed for flattening {pos.symbol}: {decision.reason}",
                        actions=[],
                        requires_approval=True,
                        diagnostics={"failed_decision": decision.model_dump()}
                    )
        
        return SafetyActionPlan(
            plan_id=plan_id,
            mode=mode,
            status="requires_approval" if requires_approval else "planned",
            reason=f"Found {len(portfolio.positions)} positions to flatten.",
            actions=actions,
            requires_approval=requires_approval
        )

    def _plan_soft_pause(self, plan_id: str, mode: KillSwitchMode) -> SafetyActionPlan:
        return SafetyActionPlan(
            plan_id=plan_id,
            mode=mode,
            status="planned",
            reason="System in soft_pause. No automated corrective actions required by default.",
            actions=[SafetyAction(type="no_op", description="Wait for resume or explicit intervention")],
            requires_approval=False
        )
