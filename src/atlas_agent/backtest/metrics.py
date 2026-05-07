from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean, pstdev


@dataclass(frozen=True)
class TradeRecord:
    side: str
    quantity: float
    price: float
    notional: float
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    number_of_trades: int
    average_trade_return: float
    best_trade: float
    worst_trade: float
    exposure_time: float
    buy_and_hold_return: float
    excess_return_vs_benchmark: float


def calculate_metrics(
    *,
    starting_cash: float,
    ending_equity: float,
    equity_curve: list[float],
    trades: list[TradeRecord],
    exposure_points: list[bool],
    start_price: float,
    end_price: float,
    periods_per_year: int = 252,
) -> BacktestMetrics:
    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")
    total_return = (ending_equity - starting_cash) / starting_cash
    periods = max(len(equity_curve), 1)
    annualized = (1 + total_return) ** (periods_per_year / periods) - 1
    closed_returns = _closed_trade_returns(trades)
    benchmark = (end_price - start_price) / start_price
    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized,
        max_drawdown=_max_drawdown(equity_curve),
        sharpe_ratio=_sharpe(equity_curve, periods_per_year),
        win_rate=_win_rate(closed_returns),
        number_of_trades=len(trades),
        average_trade_return=fmean(closed_returns) if closed_returns else 0.0,
        best_trade=max(closed_returns) if closed_returns else 0.0,
        worst_trade=min(closed_returns) if closed_returns else 0.0,
        exposure_time=(
            sum(1 for point in exposure_points if point) / len(exposure_points)
            if exposure_points
            else 0.0
        ),
        buy_and_hold_return=benchmark,
        excess_return_vs_benchmark=total_return - benchmark,
    )


def _closed_trade_returns(trades: list[TradeRecord]) -> list[float]:
    returns: list[float] = []
    for trade in trades:
        if trade.side != "sell":
            continue
        entry_notional = trade.notional - trade.realized_pnl
        if entry_notional > 0:
            returns.append(trade.realized_pnl / entry_notional)
    return returns


def _win_rate(returns: list[float]) -> float:
    if not returns:
        return 0.0
    return sum(1 for item in returns if item > 0) / len(returns)


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def _sharpe(equity_curve: list[float], periods_per_year: int) -> float:
    if len(equity_curve) < 3:
        return 0.0
    returns = [
        (equity_curve[index] - equity_curve[index - 1]) / equity_curve[index - 1]
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    volatility = pstdev(returns)
    if volatility == 0:
        return 0.0
    return fmean(returns) / volatility * sqrt(periods_per_year)

