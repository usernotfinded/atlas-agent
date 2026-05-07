from __future__ import annotations

from atlas_agent.reports.writer import write_report


def generate_weekly_report() -> str:
    return str(write_report("weekly-review", "# Weekly Review\n\nReview paper evidence.\n"))

