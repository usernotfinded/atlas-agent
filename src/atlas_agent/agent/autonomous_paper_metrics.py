from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.agent.autonomous_paper_models import StatefulPaperMetrics
from atlas_agent.backtest.metrics import (
    MetricsCalculator,
    MetricsInput,
    TradeRecord,
    calculate_metrics,
)
from atlas_agent.backtest.models import BacktestFill, BacktestMetrics, BacktestPosition


def build_trade_records_from_fills(fill_history: list[BacktestFill]) -> list[TradeRecord]:
    """Convert fills to ``TradeRecord`` instances, computing realized PnL for sells.

    Realized PnL is computed using a FIFO cost-basis view of the long position.
    Commission on each sell fill is included in that fill's realized PnL so that
    trade-level returns are net of transaction costs.
    """
    open_buys: deque[list[float]] = deque()  # [quantity, price]
    records: list[TradeRecord] = []

    for fill in fill_history:
        if fill.side == "buy":
            open_buys.append([fill.quantity, fill.price])
            records.append(
                TradeRecord(
                    side="buy",
                    quantity=fill.quantity,
                    price=fill.price,
                    notional=fill.notional,
                    realized_pnl=0.0,
                )
            )
            continue

        # Sell: match against earliest open buy lots (FIFO).
        remaining = fill.quantity
        realized = -fill.commission
        while remaining > 0 and open_buys:
            lot = open_buys[0]
            lot_qty, lot_price = lot
            consumed = min(remaining, lot_qty)
            realized += (fill.price - lot_price) * consumed
            lot[0] -= consumed
            remaining -= consumed
            if lot[0] <= 0:
                open_buys.popleft()

        records.append(
            TradeRecord(
                side="sell",
                quantity=fill.quantity,
                price=fill.price,
                notional=fill.notional,
                realized_pnl=realized,
            )
        )

    return records


def _redact_data_source(path: str | Path) -> str:
    return Path(path).name


def _approximate_equity_curve(
    *,
    starting_cash: float,
    fill_history: list[BacktestFill],
) -> tuple[list[float], list[bool]]:
    """Build a fill-based equity curve and exposure vector.

    This is intentionally conservative: equity is only sampled at fill points,
    so metrics derived from it (drawdown, Sharpe) are approximations.
    """
    equity = starting_cash
    qty = 0.0
    avg_price = 0.0
    equity_curve: list[float] = [equity]
    exposure_points: list[bool] = [False]

    for fill in fill_history:
        if fill.side == "buy":
            equity -= fill.notional + fill.commission
            new_qty = qty + fill.quantity
            avg_price = (
                (qty * avg_price + fill.quantity * fill.price) / new_qty
                if new_qty > 0
                else fill.price
            )
            qty = new_qty
        else:
            equity += fill.notional - fill.commission
            qty -= fill.quantity

        position_value = qty * fill.price
        equity_value = equity + position_value
        equity_curve.append(equity_value)
        exposure_points.append(qty > 0)

    return equity_curve, exposure_points


def _number_of_trades(fill_history: list[BacktestFill]) -> int:
    """Count closed trades when sells exist, otherwise report fill count."""
    sell_fills = [f for f in fill_history if f.side == "sell"]
    return len(sell_fills) if sell_fills else len(fill_history)


def calculate_stateful_paper_metrics(
    *,
    starting_cash: float,
    cash: float,
    positions: dict[str, BacktestPosition],
    fill_history: list[BacktestFill],
    bars_processed: int,
    current_price: float,
    data_source: str,
    number_of_rejections: int = 0,
) -> StatefulPaperMetrics:
    """Compute honest trading metrics for the stateful paper runner.

    Reuses the existing backtest metrics calculator where possible and leaves
    metrics that cannot be reliably computed (e.g., realized PnL when no sells
    exist) as ``None``. Approximations are documented in ``notes``.
    """
    ending_equity = cash + sum(
        pos.quantity * current_price for pos in positions.values()
    )
    total_return_pct = (
        (ending_equity - starting_cash) / starting_cash * 100.0
        if starting_cash > 0
        else 0.0
    )

    equity_curve, exposure_points = _approximate_equity_curve(
        starting_cash=starting_cash, fill_history=fill_history
    )
    trade_records = build_trade_records_from_fills(fill_history)

    # Benchmark comparison cannot be computed from fills alone; pass a neutral
    # value so the reusable calculator does not invent one from price levels.
    try:
        backtest_metrics = calculate_metrics(
            starting_cash=starting_cash,
            ending_equity=ending_equity,
            equity_curve=equity_curve,
            trades=trade_records,
            exposure_points=exposure_points,
            start_price=1.0,
            end_price=1.0,
            benchmark_return_pct=0.0,
        )
    except Exception:
        # Fallback if the shared calculator fails (e.g., negative starting cash).
        backtest_metrics = BacktestMetrics(
            total_return_pct=total_return_pct,
            annualized_return_pct=None,
            max_drawdown_pct=0.0,
            trade_count=len(trade_records),
            win_rate=0.0,
            sharpe_ratio=0.0,
            best_trade_pct=None,
            worst_trade_pct=None,
            average_trade_pct=None,
            exposure_time_pct=None,
            buy_and_hold_return_pct=None,
            final_equity=ending_equity,
            initial_equity=starting_cash,
        )

    buy_fills = [f for f in fill_history if f.side == "buy"]
    sell_fills = [f for f in fill_history if f.side == "sell"]

    realized_pnl: float | None = None
    if sell_fills and buy_fills:
        realized_pnl = sum(
            trade.realized_pnl for trade in trade_records if trade.side == "sell"
        )

    unrealized_pnl: float | None = None
    for pos in positions.values():
        if pos.quantity > 0:
            unrealized_pnl = (current_price - pos.average_entry_price) * pos.quantity
            break

    turnover: float | None = None
    if fill_history:
        avg_equity = (
            (starting_cash + ending_equity) / 2.0
            if ending_equity > 0
            else starting_cash
        )
        turnover = (
            sum(f.notional for f in fill_history) / avg_equity
            if avg_equity > 0
            else None
        )

    gross_exposure = sum(f.notional for f in fill_history)
    net_exposure = sum(
        f.notional if f.side == "buy" else -f.notional for f in fill_history
    )

    notes = [
        "max_drawdown_pct is approximated from fill points, not a full bar-by-bar equity curve",
        "sharpe_ratio is approximated from a fill-based equity curve and may be unreliable for sparse fills",
        "win_rate is based on closed sell fills with computable realized PnL",
    ]
    if turnover is not None:
        notes.append("turnover is total notional divided by average equity")
    if not sell_fills or not buy_fills:
        notes.append("realized_pnl is omitted when buy or sell fills are unavailable")

    return StatefulPaperMetrics(
        starting_cash=starting_cash,
        ending_cash=cash,
        ending_equity=ending_equity,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_return_pct=backtest_metrics.total_return_pct,
        max_drawdown_pct=backtest_metrics.max_drawdown_pct,
        number_of_trades=_number_of_trades(fill_history),
        number_of_fills=len(fill_history),
        number_of_rejections=number_of_rejections,
        turnover=turnover,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        total_commission=sum(f.commission for f in fill_history),
        total_slippage=sum(f.slippage for f in fill_history),
        bars_processed=bars_processed,
        data_source_redacted=_redact_data_source(data_source),
        generated_at=datetime.now(UTC).isoformat(),
        notes=notes,
    )


__all__ = [
    "build_trade_records_from_fills",
    "calculate_stateful_paper_metrics",
    "MetricsCalculator",
    "MetricsInput",
    "TradeRecord",
]
