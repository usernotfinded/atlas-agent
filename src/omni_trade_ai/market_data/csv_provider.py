from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from omni_trade_ai.market_data.base import Bar


class CSVMarketDataProvider:
    required_columns = {"date", "symbol", "open", "high", "low", "close", "volume"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_bars(self, symbol: str) -> list[Bar]:
        if not self.path.exists():
            raise FileNotFoundError(f"market data not found: {self.path}")
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("market data CSV is empty")
            missing = self.required_columns - set(reader.fieldnames)
            if missing:
                raise ValueError(f"missing market data columns: {sorted(missing)}")
            bars = [
                Bar(
                    date=date.fromisoformat(row["date"]),
                    symbol=row["symbol"].upper(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                for row in reader
                if row["symbol"].upper() == symbol.upper()
            ]
        return sorted(bars, key=lambda item: item.date)

