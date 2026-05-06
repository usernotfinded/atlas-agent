from __future__ import annotations

from pathlib import Path


GITHUB_ACTIONS_WORKFLOW_PATH = Path(".github") / "workflows" / "omni-trade-routines.yml"
SCHEDULED_ROUTINES = {
    "pre_market": "30 13 * * 1-5",
    "market_open": "35 14 * * 1-5",
    "midday_scan": "30 17 * * 1-5",
    "market_close": "15 21 * * 1-5",
    "weekly_review": "30 22 * * 5",
}


def github_actions_hint() -> str:
    return "Use scheduled workflows for paper mode; keep live mode behind approval."


def write_github_actions_workflow(
    *,
    template: str = "routine-trader",
    workspace_dir: str | Path = ".",
) -> Path:
    if template != "routine-trader":
        raise ValueError(f"unknown template: {template}")
    root = Path(workspace_dir)
    path = root / GITHUB_ACTIONS_WORKFLOW_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_github_actions_workflow(), encoding="utf-8")
    return path


def render_github_actions_workflow() -> str:
    schedule_lines = "\n".join(
        f'    - cron: "{cron}" # {routine}; edit this UTC cron as needed.'
        for routine, cron in SCHEDULED_ROUTINES.items()
    )
    job_blocks = "\n\n".join(_render_job(routine, cron) for routine, cron in SCHEDULED_ROUTINES.items())
    return f"""name: OmniTradeAI Paper Routines

on:
  # Default cron times are UTC and intentionally editable.
  schedule:
{schedule_lines}
  workflow_dispatch:

env:
  TRADING_MODE: paper
  ENABLE_LIVE_TRADING: "false"
  LIVE_BROKER: alpaca
  ORDER_APPROVAL_MODE: manual_live
  KILL_SWITCH_ENABLED: "false"
  ALLOW_GIT_COMMIT: "true"
  ALLOW_GIT_PUSH: "false"
  GIT_COMMIT_AUTHOR_NAME: OmniTradeAI Agent
  GIT_COMMIT_AUTHOR_EMAIL: omni-trade-ai@example.local
  # Configure GitHub Secrets in repository settings, then uncomment only after paper validation:
  # ALPACA_API_KEY: ${{{{ secrets.ALPACA_API_KEY }}}}
  # ALPACA_SECRET_KEY: ${{{{ secrets.ALPACA_SECRET_KEY }}}}
  # PERPLEXITY_API_KEY: ${{{{ secrets.PERPLEXITY_API_KEY }}}}
  # CLICKUP_API_TOKEN: ${{{{ secrets.CLICKUP_API_TOKEN }}}}

jobs:
{job_blocks}
"""


def _render_job(routine: str, cron: str) -> str:
    return f"""  {routine}:
    if: github.event_name == 'workflow_dispatch' || github.event.schedule == '{cron}'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install -e . --no-build-isolation
      - run: omni-trade routine run {routine} --mode paper"""
