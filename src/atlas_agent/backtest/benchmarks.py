# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/benchmarks.py
# PURPOSE: The do-nothing alternatives a strategy is measured against. A strategy
#          that "made 8%" has said nothing until you know what buy-and-hold made.
# DEPS:    pydantic (models)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Protocol, Sequence

from pydantic import BaseModel

from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.models import BacktestConfig, MarketBar


class BenchmarkResult(BaseModel):
    benchmark_id: str
    name: str
    symbol: str
    return_pct: float
    data_path: str | None = None


class Benchmark(Protocol):
    benchmark_id: str
    name: str

    def calculate(self, bars: Sequence[MarketBar]) -> BenchmarkResult:
        ...


class BuyAndHoldBenchmark:
    benchmark_id = "buy_and_hold"
    name = "Buy and Hold"

    def calculate(self, bars: Sequence[MarketBar]) -> BenchmarkResult:
        if not bars:
            return BenchmarkResult(
                benchmark_id=self.benchmark_id,
                name=self.name,
                symbol="",
                return_pct=0.0,
            )

        symbol = bars[-1].symbol or ""
        start_price = bars[0].close
        end_price = bars[-1].close
        return_pct = ((end_price - start_price) / start_price) * 100.0 if start_price > 0 else 0.0
        return BenchmarkResult(
            benchmark_id=self.benchmark_id,
            name=self.name,
            symbol=symbol,
            return_pct=return_pct,
        )


class SPYBenchmark:
    benchmark_id = "spy"
    name = "SPY"

    def __init__(self, data_path: str, symbol: str = "SPY") -> None:
        if not data_path:
            raise ValueError("SPY benchmark requires a local benchmark data path")
        self.data_path = data_path
        self.symbol = symbol

    def calculate(self, bars: Sequence[MarketBar]) -> BenchmarkResult:
        benchmark_bars = load_market_data(self.data_path, self.symbol)
        start_price = benchmark_bars[0].close
        end_price = benchmark_bars[-1].close
        return_pct = ((end_price - start_price) / start_price) * 100.0 if start_price > 0 else 0.0
        return BenchmarkResult(
            benchmark_id=self.benchmark_id,
            name=self.name,
            symbol=self.symbol,
            return_pct=return_pct,
            data_path=self.data_path,
        )


def get_benchmark(config: BacktestConfig) -> Benchmark:
    if config.benchmark_mode == "buy_and_hold":
        return BuyAndHoldBenchmark()
    if config.benchmark_mode == "spy":
        return SPYBenchmark(
            data_path=config.benchmark_data_path or "",
            symbol=config.benchmark_symbol,
        )
    raise ValueError(f"Unknown backtest benchmark: {config.benchmark_mode}")
