from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import NamedTuple

from atlas_agent.market_data.base import Bar


class _CSVCacheState(NamedTuple):
    mtime_ns: int
    bars_by_symbol: dict[str, list[Bar]]


class CSVMarketDataProvider:
    required_columns = {"date", "symbol", "open", "high", "low", "close", "volume"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._cache: _CSVCacheState | None = None

    def load_bars(self, symbol: str) -> list[Bar]:
        if not self.path.exists():
            raise FileNotFoundError(f"market data not found: {self.path}")
        cache = self._load_cache()
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
        for bars in bars_by_symbol.values():
            bars.sort(key=lambda item: item.date)
        self._cache = _CSVCacheState(mtime_ns=stat.st_mtime_ns, bars_by_symbol=bars_by_symbol)
        return self._cache
