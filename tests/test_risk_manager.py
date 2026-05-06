from __future__ import annotations

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.order import Order
from omni_trade_ai.portfolio.state import PortfolioState
from omni_trade_ai.risk.manager import RiskManager


def evaluate(order: Order, config: OmniTradeConfig, portfolio: PortfolioState | None = None):
    manager = RiskManager.from_config(config)
    return manager.validate_order(
        order,
        portfolio or PortfolioState(cash=10_000),
        mode=config.trading_mode,
        market_price=100,
    )


def test_max_position_size_blocks_order() -> None:
    decision = evaluate(
        Order("BTC-USD", "buy", 2, limit_price=100, confidence=1),
        OmniTradeConfig(max_position_size=100),
    )

    assert not decision.allowed
    assert "max position size exceeded" in decision.reasons


def test_max_daily_loss_blocks_order() -> None:
    portfolio = PortfolioState(cash=10_000, realized_pnl_today=-101)
    decision = evaluate(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1),
        OmniTradeConfig(max_daily_loss=100),
        portfolio,
    )

    assert "max daily loss exceeded" in decision.reasons


def test_max_trades_per_day_blocks_order() -> None:
    portfolio = PortfolioState(cash=10_000, trades_today=5)
    decision = evaluate(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1),
        OmniTradeConfig(max_trades_per_day=5),
        portfolio,
    )

    assert "max trades per day exceeded" in decision.reasons


def test_leverage_blocked_by_default() -> None:
    decision = evaluate(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1, leverage=2),
        OmniTradeConfig(),
    )

    assert "leverage is blocked by default" in decision.reasons


def test_symbol_blocklist_works() -> None:
    decision = evaluate(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1),
        OmniTradeConfig(symbol_blocklist={"BTC-USD"}),
    )

    assert "symbol is blocklisted" in decision.reasons

