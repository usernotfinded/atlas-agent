# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    reports/__init__.py
# PURPOSE: Public surface of the reports domain: daily, weekly and ad-hoc reports
#          built entirely from local data.
# DEPS:    reports.daily, reports.weekly, reports.generator, reports.renderers
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.reports.daily import generate_daily_report
from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.models import ReportData
from atlas_agent.reports.renderers import render_json, render_json_string, render_markdown
from atlas_agent.reports.weekly import generate_weekly_report

__all__ = [
    "generate_daily_report",
    "generate_report",
    "generate_weekly_report",
    "render_json",
    "render_json_string",
    "render_markdown",
    "ReportData",
]
