# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market_data/csv_provider.py
# PURPOSE: Loads OHLCV bars from a CSV file. The default data source: offline,
#          deterministic and reproducible, which is what a backtest needs to be
#          worth anything.
# DEPS:    market_data.base (Bar)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import NamedTuple

from atlas_agent.market_data.base import Bar


# ==============================================================================
# CACHE STATE
# ==============================================================================

class _CSVCacheState(NamedTuple):
    # Keyed on mtime, so an edited file is transparently reloaded. Caching on path
    # alone would serve stale bars for the rest of the process's life.
    mtime_ns: int
    bars_by_symbol: dict[str, list[Bar]]


# ==============================================================================
# CSV PROVIDER
# ==============================================================================

class CSVMarketDataProvider:
    required_columns = {"date", "symbol", "open", "high", "low", "close", "volume"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._cache: _CSVCacheState | None = None

    def load_bars(self, symbol: str) -> list[Bar]:
        if not self.path.exists():
            raise FileNotFoundError(f"market data not found: {self.path}")
        cache = self._load_cache()
        # A COPY of the list, not the cached one. Callers (strategies, the backtest
        # engine) would otherwise be able to mutate the shared cache and corrupt every
        # later run in the same process.
        return list(cache.bars_by_symbol.get(symbol.upper(), []))

    def _load_cache(self) -> _CSVCacheState:
        stat = self.path.stat()
        if self._cache is not None and self._cache.mtime_ns == stat.st_mtime_ns:
            return self._cache
        bars_by_symbol: dict[str, list[Bar]] = {}
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("market data CSV is empty")
            # Fail on a malformed header rather than reading rows with missing fields.
            # A backtest run on silently-incomplete data produces a plausible-looking
            # result that is simply wrong — the worst possible failure mode here.
            missing = self.required_columns - set(reader.fieldnames)
            if missing:
                raise ValueError(f"missing market data columns: {sorted(missing)}")
            for row in reader:
                bar = Bar(
                    date=date.fromisoformat(row["date"]),
                    symbol=row["symbol"].upper(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                bars_by_symbol.setdefault(bar.symbol, []).append(bar)
        # Sorted by date regardless of the file's own order. The backtest engine walks
        # bars forward in time and would otherwise "look ahead" at a future bar that
        # happened to be listed early — the classic way to accidentally build a strategy
        # that cannot lose.
        for bars in bars_by_symbol.values():
            bars.sort(key=lambda item: item.date)
        self._cache = _CSVCacheState(mtime_ns=stat.st_mtime_ns, bars_by_symbol=bars_by_symbol)
        return self._cache
