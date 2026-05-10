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

def test_market_order_without_reference_price_is_rejected():
    from atlas_agent.execution.order import Order
    from atlas_agent.portfolio.state import PortfolioState
    config = AtlasConfig()
    manager = RiskManager.from_config(config)
    
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market", limit_price=None)
    portfolio = PortfolioState(cash=10000.0)
    
    # Pass market_price=0.0
    decision = manager.validate_order(order, portfolio, mode="paper", market_price=0.0)
    assert not decision.allowed
    assert "reference_price_required" in decision.reasons
    assert "Cannot evaluate notional for market order without reference price" in decision.reasons

def test_market_order_with_reference_price_passes():
    from atlas_agent.execution.order import Order
    from atlas_agent.portfolio.state import PortfolioState
    config = AtlasConfig()
    manager = RiskManager.from_config(config)
    
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market", limit_price=None)
    portfolio = PortfolioState(cash=10000.0)
    
    # Pass market_price=10.0
    decision = manager.validate_order(order, portfolio, mode="paper", market_price=10.0)
    assert decision.allowed

def test_limit_order_uses_limit_price():
    from atlas_agent.execution.order import Order
    from atlas_agent.portfolio.state import PortfolioState
    config = AtlasConfig(max_order_notional=100)
    manager = RiskManager.from_config(config)
    
    # limit price is 20, qty=10 -> notional 200, but market_price is 5 (notional 50)
    # The order should be blocked because the effective price is limit_price (20) causing notional=200 > 100
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=20.0)
    portfolio = PortfolioState(cash=10000.0)
    
    decision = manager.validate_order(order, portfolio, mode="paper", market_price=5.0)
    assert not decision.allowed
    # The reason comes from legacy shim combining them
    assert any("max order notional exceeded" in r for r in decision.reasons)

