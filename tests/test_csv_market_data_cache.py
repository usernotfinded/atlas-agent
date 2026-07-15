# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_csv_market_data_cache.py
# PURPOSE: Verifies csv market data cache behavior and regression expectations.
# DEPS:    os, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import os
from pathlib import Path

from atlas_agent.market_data.csv_provider import CSVMarketDataProvider


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _write_csv(path: Path, rows: str) -> None:
    path.write_text(
        "date,symbol,open,high,low,close,volume\n" + rows,
        encoding="utf-8",
    )


def test_csv_provider_caches_bars_by_symbol(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlcv.csv"
    _write_csv(
        csv_path,
        "2026-05-15,AAPL,1,2,1,2,100\n"
        "2026-05-15,MSFT,3,4,3,4,200\n",
    )
    provider = CSVMarketDataProvider(csv_path)

    aapl = provider.load_bars("aapl")
    cache = provider._cache
    msft = provider.load_bars("MSFT")

    assert cache is provider._cache
    assert [bar.symbol for bar in aapl] == ["AAPL"]
    assert [bar.symbol for bar in msft] == ["MSFT"]


def test_csv_provider_invalidates_cache_on_mtime_change(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlcv.csv"
    _write_csv(csv_path, "2026-05-15,AAPL,1,2,1,2,100\n")
    provider = CSVMarketDataProvider(csv_path)

    assert provider.load_bars("AAPL")[0].close == 2.0

    _write_csv(csv_path, "2026-05-15,AAPL,1,3,1,3,100\n")
    stat = csv_path.stat()
    os.utime(csv_path, ns=(stat.st_atime_ns + 1_000_000_000, stat.st_mtime_ns + 1_000_000_000))

    assert provider.load_bars("AAPL")[0].close == 3.0
