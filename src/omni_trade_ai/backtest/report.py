from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omni_trade_ai.backtest.metrics import TradeRecord


def write_backtest_report(
    *,
    payload: dict[str, Any],
    trades: list[TradeRecord],
    output_dir: str | Path,
    stem: str,
) -> tuple[Path, Path, Path]:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(), **payload}
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    csv_path = report_dir / f"{stem}-trades.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["side", "quantity", "price", "notional", "realized_pnl"],
        )
        writer.writeheader()
        for trade in trades:
            writer.writerow(asdict(trade))
    return json_path, md_path, csv_path


def _markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        f"# Backtest Report: {payload['symbol']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in metrics.items():
        if isinstance(value, float):
            rendered = f"{value:.4f}"
        else:
            rendered = str(value)
        lines.append(f"| {key} | {rendered} |")
    return "\n".join(lines) + "\n"

