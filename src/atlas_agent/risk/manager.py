from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.validation import RiskDecision


@dataclass
class RiskManager:
    limits: RiskLimits
    audit: AuditLogger | None = None
    kill_switch_enabled: bool = False

    @classmethod
    def from_config(
        cls,
        config: AtlasConfig,
        audit: AuditLogger | None = None,
    ) -> RiskManager:
        return cls(
            limits=RiskLimits(
                max_daily_loss=config.max_daily_loss,
                max_position_size=config.max_position_size,
                max_trades_per_day=config.max_trades_per_day,
                max_portfolio_exposure=config.max_portfolio_exposure,
                max_order_notional=config.max_order_notional,
                allow_leverage=config.allow_leverage,
                minimum_confidence=config.minimum_confidence,
                require_stop_loss_live=config.require_stop_loss_live,
                enforce_market_hours=config.enforce_market_hours,
                symbol_allowlist=config.symbol_allowlist,
                symbol_blocklist=config.symbol_blocklist,
            ),
            audit=audit,
            kill_switch_enabled=config.kill_switch_enabled,
        )

    def validate_order(
        self,
        order: Order,
        portfolio: PortfolioState,
        *,
        mode: str,
        market_price: float,
        market_is_open: bool = True,
    ) -> RiskDecision:
        reasons: list[str] = []
        symbol = order.symbol.upper()
        notional = order.quantity * market_price
        existing = portfolio.positions.get(symbol)
        current_quantity = existing.quantity if existing else 0.0

        if self.kill_switch_enabled:
            reasons.append("kill switch is enabled")
        if portfolio.realized_pnl_today <= -self.limits.max_daily_loss:
            reasons.append("max daily loss exceeded")
        if portfolio.trades_today >= self.limits.max_trades_per_day:
            reasons.append("max trades per day exceeded")
        if notional > self.limits.max_order_notional:
            reasons.append("max order notional exceeded")
        if order.side.lower() in {"buy", "increase"}:
            projected_quantity = current_quantity + order.quantity
            if projected_quantity * market_price > self.limits.max_position_size:
                reasons.append("max position size exceeded")
        if portfolio.exposure({symbol: market_price}) + notional > self.limits.max_portfolio_exposure:
            reasons.append("max portfolio exposure exceeded")
        if order.leverage != 1 or self.limits.allow_leverage:
            reasons.append("leverage is blocked by default")
        if self.limits.symbol_allowlist and symbol not in self.limits.symbol_allowlist:
            reasons.append("symbol is not allowlisted")
        if self.limits.symbol_blocklist and symbol in self.limits.symbol_blocklist:
            reasons.append("symbol is blocklisted")
        if order.confidence < self.limits.minimum_confidence:
            reasons.append("confidence below minimum threshold")
        if order.id in portfolio.seen_order_ids:
            reasons.append("duplicate order id")
        if mode == "live" and self.limits.require_stop_loss_live and order.stop_loss is None:
            reasons.append("stop loss required for live mode")
        if self.limits.enforce_market_hours and not market_is_open:
            reasons.append("market is closed")

        decision = RiskDecision(allowed=not reasons, reasons=tuple(reasons))
        if not decision.allowed and self.audit is not None:
            self.audit.write(
                "risk_rejection",
                {"order_id": order.id, "symbol": order.symbol, "reasons": decision.reasons},
            )
        return decision

