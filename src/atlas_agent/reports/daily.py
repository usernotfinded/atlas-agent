from __future__ import annotations

from atlas_agent.reports.writer import write_report


def generate_daily_report() -> str:
    return str(write_report("daily-report", "# Daily Report\n\nNo live trading by default.\n"))

