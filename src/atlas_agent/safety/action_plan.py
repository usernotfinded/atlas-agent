# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/action_plan.py
# PURPOSE: Turns a kill-switch verdict into a concrete, reviewable list of actions.
#          Plans only — nothing here touches a broker. Separating "decide what to do"
#          from "do it" is what lets a human read the plan before it executes.
# DEPS:    safety.models (plan/action shapes), risk.manager (the plan is itself
#          risk-checked — see _plan_flatten_all)
# ==============================================================================

# --- IMPORTS ---
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


# ==============================================================================
# SAFETY ACTION PLANNER
# ==============================================================================

class SafetyActionPlanner:
    def __init__(
        self,
        risk_manager: Optional[RiskManager] = None,
        # Defaults to False: even in paper mode, a safety plan is auto-approved only
        # when someone explicitly says so. Silent auto-execution is opt-in, never
        # inherited from "it's only paper".
        allow_auto_paper_actions: bool = False
    ):
        self.risk_manager = risk_manager
        self.allow_auto_paper_actions = allow_auto_paper_actions

    # --- Dispatch ---

    def create_plan(
        self,
        decision: KillSwitchDecision,
        portfolio: PortfolioSnapshot,
        open_order_ids: List[str],
        mode: Literal["paper", "live"] = "paper"
    ) -> SafetyActionPlan:
        plan_id = str(uuid4())
        ks_mode = decision.mode

        # One branch per kill-switch mode, most severe first. Note that `normal` is the
        # fallthrough at the bottom — an unrecognised mode therefore produces a no-op
        # plan, which is safe here precisely BECAUSE the switch itself already blocked
        # the order. This module never grants permission; it only plans the cleanup.
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

    # --- Per-mode plans ---

    def _plan_lockdown(self, plan_id: str, mode: KillSwitchMode) -> SafetyActionPlan:
        # Lockdown plans a NOTIFICATION and nothing else. It deliberately does not
        # cancel or flatten: lockdown is the "we no longer trust our own state" mode,
        # and a system that cannot trust its state must not be sending orders — not even
        # well-meant corrective ones. Getting a human involved is the entire plan.
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

        # Approval is required unless BOTH conditions hold: we are in paper, and auto
        # actions were explicitly enabled. Live always needs a human — no exceptions,
        # and no config that can grant one.
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
            # The closing side is the OPPOSITE of the position's sign: a long (qty > 0)
            # is closed by selling, a short (qty < 0) by buying. Getting this backwards
            # would double the exposure the flatten was meant to remove.
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

            # Flatten orders are run through the RiskManager like any other order. Not
            # to gate them — a flatten reduces risk by construction — but as a TRIPWIRE:
            # if risk says this order does not reduce risk, then our reading of the
            # position is wrong (bad sign, stale price, corrupt snapshot), and the last
            # thing to do is send it. The whole plan is abandoned rather than partially
            # executed, because a half-flattened book from a bad snapshot is worse than
            # an untouched one a human then looks at.
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
                    # Unreachable in a consistent system — which is exactly what makes it
                    # worth checking. Reaching here means an invariant is already broken.
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
