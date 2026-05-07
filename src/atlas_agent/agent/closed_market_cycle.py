from __future__ import annotations

import datetime
from pathlib import Path

from atlas_agent.config import AtlasConfig
from atlas_agent.routines.engine import RoutineResult, run_routine


def run_closed_market_cycle(config: AtlasConfig, mode: str, models: str | None = None) -> RoutineResult:
    # Force paper mode for closed market
    safe_mode = "paper"
    
    from atlas_agent.cli import run_once
    
    # We use pre_market as the base for closed market (research, simulation)
    result = run_routine(
        "pre_market",
        mode=safe_mode,
        config=config,
        order_runner=lambda **kwargs: run_once(**kwargs, models=models),
        models=models,
    )
    
    import dataclasses
    
    # Move report to agent folder
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    agent_report_path = config.reports_dir / "agent" / f"{timestamp}-agent-closed.md"
    agent_report_path.parent.mkdir(parents=True, exist_ok=True)
    if result.report_path and Path(result.report_path).exists():
        Path(result.report_path).rename(agent_report_path)
        result = dataclasses.replace(result, report_path=str(agent_report_path))
        
    return result
