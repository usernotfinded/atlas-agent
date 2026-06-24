from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from atlas_agent.backtest.models import MarketBar


def _parse_date_boundary(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d")


def load_market_data(
    file_path: str,
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[MarketBar]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Market data file not found: {file_path}")

    start_dt = _parse_date_boundary(start_date)
    end_dt = _parse_date_boundary(end_date)

    bars = []
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate headers
        fieldnames = set(reader.fieldnames or [])
        time_col = "timestamp" if "timestamp" in fieldnames else "date"
        required_cols = {"open", "high", "low", "close", "volume"}
        if time_col not in fieldnames or not required_cols.issubset(fieldnames):
            missing = (required_cols | {time_col}) - fieldnames
            raise ValueError(f"Missing required columns in CSV: {missing}")

        for row in reader:
            # Skip rows for different symbols if a symbol filter was requested
            if symbol is not None and "symbol" in row and row["symbol"] and row["symbol"] != symbol:
                continue

            try:
                # Support common ISO formats or basic YYYY-MM-DD
                ts_str = row[time_col]
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    # Fallback for simple date
                    ts = datetime.strptime(ts_str, "%Y-%m-%d")

                if start_dt is not None and ts < start_dt:
                    continue
                if end_dt is not None and ts > end_dt:
                    continue

                bars.append(MarketBar(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    symbol=symbol
                ))
            except (ValueError, KeyError) as e:
                # In a real system we might log and continue, but for deterministic backtest
                # we want to know if data is corrupt.
                raise ValueError(f"Error parsing row {row}: {e}")

    if not bars:
        if symbol is not None:
            raise ValueError(f"No data found for symbol {symbol} in {file_path}")
        raise ValueError(f"No data found in {file_path}")

    # Ensure bars are sorted by timestamp
    bars.sort(key=lambda x: x.timestamp)
    return bars
