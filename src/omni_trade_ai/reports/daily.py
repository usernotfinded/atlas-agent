from __future__ import annotations

from omni_trade_ai.reports.writer import write_report


def generate_daily_report() -> str:
    return str(write_report("daily-report", "# Daily Report\n\nNo live trading by default.\n"))

