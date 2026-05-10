from __future__ import annotations

from typing import Optional, List, Literal, Any, Tuple

from atlas_agent.audit import AuditWriter
from atlas_agent.risk.limits import RiskLimits, DEFAULT_RISK_LIMITS
from atlas_agent.risk.models import (
    RiskDecision, 
    RiskViolation, 
    PortfolioSnapshot, 
    OrderRiskInput,
    OrderClassification,
    PendingOrder
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
        def _get(obj, key, default):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        enable_live = _get(config, "enable_live_trading", False)
        
        limits = RiskLimits(
            max_position_notional=_get(config, "max_position_size", 1000.0),
            max_single_trade_notional=_get(config, "max_order_notional", 500.0),
            allowed_symbols=_get(config, "symbol_allowlist", None),
            blocked_symbols=_get(config, "symbol_blocklist", set()) or set(),
            live_trading_enabled=enable_live,
            paper_only=not enable_live,
            minimum_confidence=_get(config, "minimum_confidence", 0.6),
            allow_shorting=_get(config, "allow_shorting", False),
        )
        return cls(limits=limits, kill_switch_enabled=_get(config, "kill_switch_enabled", False))

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
        
        # 1. Determine reference price
        limit_price = getattr(order, "limit_price", None)
        effective_price = limit_price if limit_price and limit_price > 0 else market_price
        
        if not effective_price or effective_price <= 0:
            class LegacyDecision:
                def __init__(self, allowed, reasons):
                    self.allowed = allowed
                    self.reasons = reasons
            return LegacyDecision(False, ("Cannot evaluate notional for market order without reference price", "reference_price_required"))

        risk_input = OrderRiskInput(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=effective_price,
            notional=order.quantity * effective_price,
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

    def _calculate_projection(
        self, 
        order: OrderRiskInput, 
        portfolio: PortfolioSnapshot
    ) -> dict[str, Any]:
        symbol = order.symbol.upper()
        current_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
        
        current_qty = current_pos.quantity if current_pos else 0.0
        order_qty_delta = order.quantity if order.side == "buy" else -order.quantity
        
        # Identify active pending orders
        active_statuses = {"pending", "open", "partially_filled"}
        pending_orders = [o for o in portfolio.open_orders if o.symbol == symbol and o.status in active_statuses]
        
        pending_qty_delta = sum((o.remaining_quantity if o.side == "buy" else -o.remaining_quantity) for o in pending_orders)
        
        baseline_projected_qty = current_qty + pending_qty_delta
        
        projected_qty = current_qty + order_qty_delta
        projected_qty_with_pending = baseline_projected_qty + order_qty_delta
        
        projected_exposure = abs(projected_qty * order.price)
        projected_exposure_with_pending = abs(projected_qty_with_pending * order.price)
        
        # Classification relative to current position
        classification: OrderClassification = "unknown"
        if current_qty == 0:
            classification = "opens_new_position"
        elif projected_qty == 0:
            classification = "closes_position"
        elif (current_qty > 0 and projected_qty < 0) or (current_qty < 0 and projected_qty > 0):
            classification = "flips_position"
        elif abs(projected_qty) > abs(current_qty):
            classification = "increases_risk"
        else:
            classification = "reduces_risk"
            
        # Classification relative to pending baseline
        is_increasing_risk_with_pending = False
        if baseline_projected_qty == 0:
            is_increasing_risk_with_pending = (projected_qty_with_pending != 0)
        elif abs(projected_qty_with_pending) > abs(baseline_projected_qty):
            is_increasing_risk_with_pending = True
        elif (baseline_projected_qty > 0 and projected_qty_with_pending < 0) or (baseline_projected_qty < 0 and projected_qty_with_pending > 0):
            is_increasing_risk_with_pending = True

        return {
            "classification": classification,
            "is_increasing_risk_with_pending": is_increasing_risk_with_pending,
            "current_quantity": current_qty,
            "pending_quantity_delta": pending_qty_delta,
            "proposed_quantity_delta": order_qty_delta,
            "projected_quantity": projected_qty,
            "projected_quantity_with_pending": projected_qty_with_pending,
            "projected_exposure": projected_exposure,
            "projected_exposure_with_pending": projected_exposure_with_pending,
            "included_pending_order_ids": [o.order_id for o in pending_orders],
            "ignored_pending_order_ids": [o.order_id for o in portfolio.open_orders if o.symbol == symbol and o.status not in active_statuses]
        }

    def evaluate_order(
        self,
        order: OrderRiskInput,
        portfolio: PortfolioSnapshot,
        mode: Literal["paper", "live"] = "paper",
    ) -> RiskDecision:
        projection = self._calculate_projection(order, portfolio)
        classification = projection["classification"]
        projected_qty_with_pending = projection["projected_quantity_with_pending"]
        projected_exposure_with_pending = projection["projected_exposure_with_pending"]
        is_increasing_risk_with_pending = projection["is_increasing_risk_with_pending"]

        if self.audit_writer:
            self.audit_writer.write_event(
                "risk_evaluation_started",
                run_id=self.run_id,
                iteration=self.iteration,
                tool_name="risk_manager",
                payload={
                    "order": order.model_dump(),
                    "portfolio": portfolio.model_dump(),
                    "mode": mode,
                    "projection": projection
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

        # 3. Shorting policy
        if not self.limits.allow_shorting:
            if projected_qty_with_pending < 0:
                # Block if it opens, increases, or flips to short
                # Even if it's "reduces_risk" relative to current, if it makes the projected short worse, it's blocked.
                if is_increasing_risk_with_pending:
                    violations.append(RiskViolation(
                        rule="allow_shorting",
                        message="shorting is disabled",
                        limit_value=False,
                        actual_value=True
                    ))

        # 4. Limits only apply if risk increases relative to current OR pending baseline
        # (Worst case approach: if either the current risk is increased, or the projected risk is increased, check limits)
        # Actually, let's be smarter: if the proposed order REDUCES absolute risk in BOTH current and pending scenarios, it's exempt.
        
        # Is it reducing risk in the current position?
        is_reducing_current = classification in ["reduces_risk", "closes_position"]
        # Is it reducing risk in the pending scenario?
        is_reducing_pending = not is_increasing_risk_with_pending
        
        should_check_limits = not (is_reducing_current and is_reducing_pending)
        
        if should_check_limits:
            # Single trade limits (always check for new orders)
            if order.notional > self.limits.max_single_trade_notional:
                violations.append(RiskViolation(
                    rule="max_single_trade_notional",
                    message=f"max order notional exceeded",
                    limit_value=self.limits.max_single_trade_notional,
                    actual_value=order.notional
                ))

            # Position limits (including pending)
            if projected_exposure_with_pending > self.limits.max_position_notional:
                violations.append(RiskViolation(
                    rule="max_position_notional",
                    message=f"max position size exceeded (including pending orders)",
                    limit_value=self.limits.max_position_notional,
                    actual_value=projected_exposure_with_pending
                ))

            # Symbol exposure % check
            if portfolio.equity > 0:
                exposure_pct = projected_exposure_with_pending / portfolio.equity
                if exposure_pct > self.limits.max_symbol_exposure_pct:
                    violations.append(RiskViolation(
                        rule="max_symbol_exposure_pct",
                        message=f"symbol exposure {exposure_pct:.1%} exceeds limit {self.limits.max_symbol_exposure_pct:.1%}",
                        limit_value=self.limits.max_symbol_exposure_pct,
                        actual_value=exposure_pct
                    ))

            # Portfolio exposure limits
            current_symbol_exposure = 0.0
            current_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
            if current_pos:
                current_symbol_exposure = current_pos.notional
            
            projected_total_exposure = portfolio.total_exposure - current_symbol_exposure + projected_exposure_with_pending
            
            max_exposure_abs = portfolio.equity * self.limits.max_portfolio_exposure_pct
            if projected_total_exposure > max_exposure_abs:
                violations.append(RiskViolation(
                    rule="max_portfolio_exposure_pct",
                    message=f"max portfolio exposure exceeded",
                    limit_value=max_exposure_abs,
                    actual_value=projected_total_exposure
                ))
            
            # Max open positions
            if classification == "opens_new_position":
                symbols_with_positions = {p.symbol for p in portfolio.positions}
                symbols_with_pending = {o.symbol for o in portfolio.open_orders if o.status in {"pending", "open", "partially_filled"}}
                unique_symbols = symbols_with_positions | symbols_with_pending
                
                if len(unique_symbols) >= self.limits.max_open_positions and symbol not in unique_symbols:
                    violations.append(RiskViolation(
                        rule="max_open_positions",
                        message=f"max open positions reached",
                        limit_value=self.limits.max_open_positions,
                        actual_value=len(unique_symbols)
                    ))

        # 5. Confidence check (always applies)
        if order.confidence is not None and order.confidence < self.limits.minimum_confidence:
             violations.append(RiskViolation(
                rule="minimum_confidence",
                message=f"confidence below minimum threshold",
                limit_value=self.limits.minimum_confidence,
                actual_value=order.confidence
            ))

        # 6. Live stop loss requirement (always applies in live)
        if mode == "live" and self.limits.require_stop_loss_live and order.stop_loss is None:
            violations.append(RiskViolation(
                rule="require_stop_loss_live",
                message="stop loss required for live mode",
                limit_value=True,
                actual_value=None
            ))

        # Determine decision
        diagnostics = projection.copy()
        
        if violations:
            decision = RiskDecision(
                allowed=False,
                status="blocked",
                reason="Risk violations detected",
                violations=violations,
                classification=classification,
                projected_quantity=projection["projected_quantity"],
                projected_exposure=projection["projected_exposure"],
                projected_quantity_with_pending=projected_qty_with_pending,
                projected_exposure_with_pending=projected_exposure_with_pending,
                diagnostics=diagnostics
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
            if mode == "live":
                decision = RiskDecision(
                    allowed=True,
                    status="requires_approval",
                    reason="Live order requires manual approval",
                    classification=classification,
                    projected_quantity=projection["projected_quantity"],
                    projected_exposure=projection["projected_exposure"],
                    projected_quantity_with_pending=projected_qty_with_pending,
                    projected_exposure_with_pending=projected_exposure_with_pending,
                    diagnostics=diagnostics
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
                    reason="All risk checks passed",
                    classification=classification,
                    projected_quantity=projection["projected_quantity"],
                    projected_exposure=projection["projected_exposure"],
                    projected_quantity_with_pending=projected_qty_with_pending,
                    projected_exposure_with_pending=projected_exposure_with_pending,
                    diagnostics=diagnostics
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
