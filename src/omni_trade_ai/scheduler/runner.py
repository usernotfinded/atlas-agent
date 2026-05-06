from __future__ import annotations

from dataclasses import dataclass

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.order import OrderResult


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
    config: OmniTradeConfig,
    run_once_func,
) -> SchedulerResult:
    if routine not in VALID_ROUTINES:
        raise ValueError(f"unknown routine: {routine}")
    result = run_once_func(mode=mode, config=config)
    return SchedulerResult(routine=routine, mode=mode, order_result=result)

