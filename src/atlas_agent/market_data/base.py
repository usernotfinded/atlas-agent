from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataProvider(Protocol):
    def load_bars(self, symbol: str) -> list[Bar]:
        ...

