# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scheduler/runner.py
# PURPOSE: The scheduled entry point. Note the discipline import: a scheduled run
#          is unattended, so it demands the same validated discipline profile an
#          interactive agentic run does — and fails closed without one.
# DEPS:    ai.discipline (fail-closed profile requirement), routines.engine
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.discipline import (
    DisciplineNotConfiguredError,
    InvalidDisciplineProfileError,
    require_user_discipline,
)
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import OrderResult


VALID_ROUTINES = {"pre_market", "market_open", "midday_scan", "end_of_day", "weekly_review"}


@dataclass(frozen=True)
class SchedulerResult:
    routine: str
    mode: str
    order_result: OrderResult


def run_scheduler_once(
    *,
    routine: str,
    mode: str,
    config: AtlasConfig,
    run_once_func,
) -> SchedulerResult:
    if routine not in VALID_ROUTINES:
        raise ValueError(f"unknown routine: {routine}")
    # Discipline gate: scheduled routines are agentic.
    workspace = config.memory_dir.parent
    require_user_discipline(workspace)
    result = run_once_func(mode=mode, config=config)
    return SchedulerResult(routine=routine, mode=mode, order_result=result)

