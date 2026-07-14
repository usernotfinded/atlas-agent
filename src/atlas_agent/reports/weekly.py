# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    reports/weekly.py
# PURPOSE: The weekly report entry point. A thin composition of generator →
#          renderer → writer; the period is the only thing that differs from daily.py.
# DEPS:    reports.generator, reports.renderers, reports.writer
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.renderers import render_markdown
from atlas_agent.reports.writer import write_report


def generate_weekly_report(workspace: str = ".", output_dir: str = "reports") -> str:
    """Generate a weekly report using real local data and write it to output_dir.

    Returns the path to the written report file.
    """
    data = generate_report("weekly", workspace=workspace, output_format="markdown")
    content = render_markdown(data)
    path = write_report("weekly-report", content, output_dir=output_dir)
    return str(path)
