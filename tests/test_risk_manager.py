from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot


def evaluate(symbol: str, quantity: float, price: float, config: AtlasConfig, realized_pnl_today: float = 0.0, trades_today: int = 0, leverage: float = 1.0):
    limits = RiskLimits(
        max_position_notional=config.max_position_size,
        max_single_trade_notional=config.max_order_notional,
        max_daily_loss_pct=config.max_daily_loss / 10000.0, # Approximate for legacy compat
        blocked_symbols=config.symbol_blocklist or set(),
    )
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol=symbol,
        side="buy",
        quantity=quantity,
        price=price,
        notional=quantity * price,
        leverage=leverage
    )
    
    portfolio = PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=0.0,
        realized_pnl_today=realized_pnl_today,
        trades_today=trades_today
    )
    
    return manager.evaluate_order(order, portfolio, mode="paper")


def test_max_position_size_blocks_order() -> None:
    decision = evaluate(
        "BTC-USD", 2, 100,
        AtlasConfig(max_position_size=100),
    )

    assert not decision.allowed
    assert any("max_position_notional" in v.rule for v in decision.violations)


def test_max_order_notional_blocks_order() -> None:
    decision = evaluate(
        "BTC-USD", 1, 200,
        AtlasConfig(max_order_notional=100),
    )

    assert not decision.allowed
    assert any("max_single_trade_notional" in v.rule for v in decision.violations)


def test_symbol_blocklist_works() -> None:
    decision = evaluate(
        "BTC-USD", 1, 100,
        AtlasConfig(symbol_blocklist={"BTC-USD"}),
    )

    assert not decision.allowed
    assert any("blocked_symbols" in v.rule for v in decision.violations)
