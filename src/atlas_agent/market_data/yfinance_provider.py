from __future__ import annotations

from atlas_agent.market_data.base import Bar


class YFinanceProvider:
    def load_bars(self, symbol: str) -> list[Bar]:
        raise RuntimeError(
            "yfinance support is optional; install and configure it before use"
        )

