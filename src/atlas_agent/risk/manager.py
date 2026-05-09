from __future__ import annotations

from typing import Optional, List, Literal, Any

from atlas_agent.audit import AuditWriter
from atlas_agent.risk.limits import RiskLimits, DEFAULT_RISK_LIMITS
from atlas_agent.risk.models import (
    RiskDecision, 
    RiskViolation, 
    PortfolioSnapshot, 
    OrderRiskInput
)


class RiskManager:
    def __init__(
        self,
        limits: RiskLimits = DEFAULT_RISK_LIMITS,
        audit_writer: Optional[AuditWriter] = None,
        run_id: str = "unknown",
        iteration: Optional[int] = None,
        kill_switch_enabled: bool = False,
    ):
        self.limits = limits
        self.audit_writer = audit_writer
        self.run_id = run_id
        self.iteration = iteration
        self.kill_switch_enabled = kill_switch_enabled

    @classmethod
    def from_config(
        cls,
        config: Any,
        audit: Optional[Any] = None,
    ) -> RiskManager:
        """Legacy compatibility shim."""
        from atlas_agent.risk.limits import RiskLimits
        enable_live = getattr(config, "enable_live_trading", False)
        limits = RiskLimits(
            max_position_notional=getattr(config, "max_position_size", 1000.0),
            max_single_trade_notional=getattr(config, "max_order_notional", 500.0),
            allowed_symbols=getattr(config, "symbol_allowlist", None),
            blocked_symbols=getattr(config, "symbol_blocklist", set()) or set(),
            live_trading_enabled=enable_live,
            paper_only=not enable_live,
            minimum_confidence=getattr(config, "minimum_confidence", 0.6),
        )
        return cls(limits=limits, kill_switch_enabled=getattr(config, "kill_switch_enabled", False))

    def validate_order(
        self,
        order: Any,
        portfolio: Any,
        *,
        mode: str,
        market_price: float,
        market_is_open: bool = True,
    ) -> Any:
        """Legacy compatibility shim."""
        from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot
        
        risk_input = OrderRiskInput(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=market_price,
            notional=order.quantity * market_price,
            leverage=getattr(order, "leverage", 1.0),
            confidence=getattr(order, "confidence", None),
            stop_loss=getattr(order, "stop_loss", None)
        )
        
        # Build portfolio snapshot from legacy portfolio state
        def _get_val(obj, attr, default):
            val = getattr(obj, attr, default)
            if callable(val):
                try:
                    return val(None) # type: ignore
                except TypeError:
                    return val()
            return val

        snapshot = PortfolioSnapshot(
            cash=_get_val(portfolio, "cash", 10000.0),
            equity=_get_val(portfolio, "equity", 10000.0),
            total_exposure=_get_val(portfolio, "exposure", 0.0),
            realized_pnl_today=_get_val(portfolio, "realized_pnl_today", 0.0),
            trades_today=_get_val(portfolio, "trades_today", 0)
        )
        
        decision = self.evaluate_order(risk_input, snapshot, mode=mode) # type: ignore
        
        # Adapt RiskDecision to legacy expectations
        class LegacyDecision:
            def __init__(self, allowed, reasons):
                self.allowed = allowed
                self.reasons = reasons
        
        reasons = [v.message for v in decision.violations]
        if not decision.allowed and not reasons:
            reasons = [decision.reason or "Risk rejection"]
            
        return LegacyDecision(decision.allowed, tuple(reasons))

    def evaluate_order(
        self,
        order: OrderRiskInput,
        portfolio: PortfolioSnapshot,
        mode: Literal["paper", "live"] = "paper",
    ) -> RiskDecision:
        if self.audit_writer:
            self.audit_writer.write_event(
                "risk_evaluation_started",
                run_id=self.run_id,
                iteration=self.iteration,
                tool_name="risk_manager",
                payload={
                    "order": order.model_dump(),
                    "portfolio": portfolio.model_dump(),
                    "mode": mode
                }
            )

        violations: List[RiskViolation] = []
        symbol = order.symbol.upper()

        # 0. Kill switch
        if self.kill_switch_enabled:
            violations.append(RiskViolation(
                rule="kill_switch",
                message="kill switch is enabled",
                limit_value=False,
                actual_value=True
            ))

        # 1. Mode check
        if mode == "live":
            if self.limits.paper_only:
                violations.append(RiskViolation(
                    rule="paper_only",
                    message="Live trading is blocked (paper_only=True)",
                    limit_value=True,
                    actual_value=True
                ))
            if not self.limits.live_trading_enabled:
                violations.append(RiskViolation(
                    rule="live_trading_enabled",
                    message="ENABLE_LIVE_TRADING must be true",
                    limit_value=True,
                    actual_value=False
                ))

        # 2. Symbol check
        if self.limits.allowed_symbols is not None and symbol not in self.limits.allowed_symbols:
            violations.append(RiskViolation(
                rule="allowed_symbols",
                message=f"symbol is not allowlisted",
                limit_value=list(self.limits.allowed_symbols) if self.limits.allowed_symbols else [],
                actual_value=symbol
            ))
        
        if symbol in self.limits.blocked_symbols:
            violations.append(RiskViolation(
                rule="blocked_symbols",
                message=f"symbol is blocklisted",
                limit_value=list(self.limits.blocked_symbols),
                actual_value=symbol
            ))

        # 3. Single trade limits
        if order.notional > self.limits.max_single_trade_notional:
            violations.append(RiskViolation(
                rule="max_single_trade_notional",
                message=f"max order notional exceeded",
                limit_value=self.limits.max_single_trade_notional,
                actual_value=order.notional
            ))

        # 4. Position limits
        current_position = next((p for p in portfolio.positions if p.symbol == symbol), None)
        projected_notional = order.notional
        if current_position:
            projected_notional += current_position.notional

        if projected_notional > self.limits.max_position_notional:
            violations.append(RiskViolation(
                rule="max_position_notional",
                message=f"max position size exceeded",
                limit_value=self.limits.max_position_notional,
                actual_value=projected_notional
            ))

        # 5. Portfolio exposure limits
        projected_total_exposure = portfolio.total_exposure + order.notional
        max_exposure_abs = portfolio.equity * self.limits.max_portfolio_exposure_pct
        if projected_total_exposure > max_exposure_abs:
            violations.append(RiskViolation(
                rule="max_portfolio_exposure_pct",
                message=f"max portfolio exposure exceeded",
                limit_value=max_exposure_abs,
                actual_value=projected_total_exposure
            ))

        # 6. Confidence check
        if order.confidence is not None and order.confidence < self.limits.minimum_confidence:
             violations.append(RiskViolation(
                rule="minimum_confidence",
                message=f"confidence below minimum threshold",
                limit_value=self.limits.minimum_confidence,
                actual_value=order.confidence
            ))

        # 7. Live stop loss requirement
        if mode == "live" and self.limits.require_stop_loss_live and order.stop_loss is None:
            violations.append(RiskViolation(
                rule="require_stop_loss_live",
                message="stop loss required for live mode",
                limit_value=True,
                actual_value=None
            ))

        # Determine decision
        if violations:
            decision = RiskDecision(
                allowed=False,
                status="blocked",
                reason="Risk violations detected",
                violations=violations
            )
            if self.audit_writer:
                self.audit_writer.write_event(
                    "risk_evaluation_blocked",
                    run_id=self.run_id,
                    iteration=self.iteration,
                    tool_name="risk_manager",
                    status="blocked",
                    payload=decision.model_dump()
                )
        else:
            # Check if it requires approval (all live trades require approval by default for now)
            if mode == "live":
                decision = RiskDecision(
                    allowed=True, # Allowed to proceed to approval
                    status="requires_approval",
                    reason="Live order requires manual approval"
                )
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "risk_evaluation_requires_approval",
                        run_id=self.run_id,
                        iteration=self.iteration,
                        tool_name="risk_manager",
                        status="requires_approval",
                        payload=decision.model_dump()
                    )
            else:
                decision = RiskDecision(
                    allowed=True,
                    status="allowed",
                    reason="All risk checks passed"
                )
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "risk_evaluation_allowed",
                        run_id=self.run_id,
                        iteration=self.iteration,
                        tool_name="risk_manager",
                        status="allowed",
                        payload=decision.model_dump()
                    )

        return decision
