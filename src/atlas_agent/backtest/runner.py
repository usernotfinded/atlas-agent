from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from atlas_agent.backtest.metrics import BacktestMetrics, TradeRecord, calculate_metrics
from atlas_agent.backtest.report import write_backtest_report
from atlas_agent.config import AtlasConfig
from atlas_agent.market_data.base import Bar
from atlas_agent.market_data.csv_provider import CSVMarketDataProvider
from atlas_agent.market_data.sample_data import ensure_sample_data
from atlas_agent.strategies.moving_average import MovingAverageStrategy


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    starting_cash: float
    ending_equity: float
    metrics: BacktestMetrics
    trades: list[TradeRecord]
    report_paths: tuple[Path, Path, Path] | None = None


def run_backtest(
    *,
    symbol: str,
    strategy_name: str = "moving_average",
    config: AtlasConfig | None = None,
) -> BacktestResult:
    config = config or AtlasConfig.from_env()
    ensure_sample_data(config.data_path)
    bars = CSVMarketDataProvider(config.data_path).load_bars(symbol)
    if not bars:
        raise ValueError(f"no bars found for {symbol}")
    if strategy_name != "moving_average":
        raise ValueError("only moving_average strategy is implemented in this MVP")
    result = _simulate(bars, config)
    stem = f"backtest-{symbol}-{bars[0].date.isoformat()}-to-{bars[-1].date.isoformat()}"
    paths = write_backtest_report(
        payload={
            "mode": "backtest",
            "symbol": symbol,
            "starting_cash": result.starting_cash,
            "ending_equity": result.ending_equity,
            "metrics": asdict(result.metrics),
        },
        trades=result.trades,
        output_dir=config.reports_dir,
        stem=stem,
    )
    return BacktestResult(
        symbol=result.symbol,
        starting_cash=result.starting_cash,
        ending_equity=result.ending_equity,
        metrics=result.metrics,
        trades=result.trades,
        report_paths=paths,
    )


def _simulate(bars: list[Bar], config: AtlasConfig) -> BacktestResult:
    strategy = MovingAverageStrategy()
    cash = config.starting_cash
    quantity = 0.0
    average_price = 0.0
    trades: list[TradeRecord] = []
    equity_curve: list[float] = []
    exposure_points: list[bool] = []
    for index, bar in enumerate(bars):
        decision = strategy.decide(bars[: index + 1])
        if decision.action == "buy" and quantity == 0:
            notional = min(config.max_position_size, cash)
            quantity = notional / bar.close
            average_price = bar.close
            cash -= notional
            trades.append(TradeRecord("buy", quantity, bar.close, notional))
        elif decision.action == "sell" and quantity > 0:
            notional = quantity * bar.close
            realized = (bar.close - average_price) * quantity
            cash += notional
            trades.append(TradeRecord("sell", quantity, bar.close, notional, realized))
            quantity = 0.0
            average_price = 0.0
        equity_curve.append(cash + quantity * bar.close)
        exposure_points.append(quantity > 0)
    metrics = calculate_metrics(
        starting_cash=config.starting_cash,
        ending_equity=equity_curve[-1],
        equity_curve=equity_curve,
        trades=trades,
        exposure_points=exposure_points,
        start_price=bars[0].close,
        end_price=bars[-1].close,
    )
    return BacktestResult(
        symbol=bars[-1].symbol,
        starting_cash=config.starting_cash,
        ending_equity=equity_curve[-1],
        metrics=metrics,
        trades=trades,
    )

