from __future__ import annotations

from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition


def get_portfolio_snapshot(state: PortfolioState, marks: dict[str, float] | None = None) -> PortfolioSnapshot:
    """
    Convert internal PortfolioState to a Risk-compatible PortfolioSnapshot.
    """
    marks = marks or {}
    positions = []
    total_unrealized_pnl = 0.0
    
    for symbol, pos in state.positions.items():
        market_price = marks.get(symbol, pos.average_price)
        market_value = pos.market_value(market_price)
        notional = abs(market_value)
        unrealized = pos.unrealized_pnl(market_price)
        total_unrealized_pnl += unrealized
        
        positions.append(RiskPosition(
            symbol=symbol,
            quantity=pos.quantity,
            average_price=pos.average_price,
            market_price=market_price,
            notional=notional,
            side="long" if pos.quantity > 0 else "short" if pos.quantity < 0 else "flat"
        ))
        
    equity = state.equity(marks)
    exposure = state.exposure(marks)
    
    return PortfolioSnapshot(
        cash=state.cash,
        equity=equity,
        total_exposure=exposure,
        positions=positions,
        realized_pnl_today=state.realized_pnl_today,
        unrealized_pnl=total_unrealized_pnl,
        trades_today=state.trades_today
    )
