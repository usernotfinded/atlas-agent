from __future__ import annotations

from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.renderers import render_markdown
from atlas_agent.reports.writer import write_report


def generate_daily_report(workspace: str = ".", output_dir: str = "reports") -> str:
    """Generate a daily report using real local data and write it to output_dir.

    Returns the path to the written report file.
    """
    data = generate_report("daily", workspace=workspace, output_format="markdown")
    content = render_markdown(data)
    path = write_report("daily-report", content, output_dir=output_dir)
    return str(path)
