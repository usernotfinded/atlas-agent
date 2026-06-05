from __future__ import annotations

import math
from typing import Sequence

from atlas_agent.backtest.models import BacktestConfig, BacktestOrder, MarketBar
from atlas_agent.backtest.registry import get_strategy
from atlas_agent.backtest.strategy import (
    BacktestStrategy,
    StrategyContext,
    StrategyParameterValidationError,
    StrategyValidationIssue,
    StrategyValidationResult,
)


def validate_strategy(
    strategy_id: str,
    *,
    bars: Sequence[MarketBar] | None = None,
    config: BacktestConfig | None = None,
) -> StrategyValidationResult:
    try:
        strategy = get_strategy(
            strategy_id,
            parameters=config.strategy_parameters if config else None,
        )
    except KeyError as exc:
        return StrategyValidationResult(
            strategy_id=strategy_id,
            status="invalid",
            issues=[
                StrategyValidationIssue(
                    severity="error",
                    code="strategy_not_found",
                    message=str(exc),
                )
            ],
        )
    except (StrategyParameterValidationError, ValueError) as exc:
        return StrategyValidationResult(
            strategy_id=strategy_id,
            status="invalid",
            issues=[
                StrategyValidationIssue(
                    severity="error",
                    code="strategy_parameters_invalid",
                    message=str(exc),
                )
            ],
        )

    return validate_strategy_instance(strategy, bars=bars or (), config=config)


def validate_strategy_instance(
    strategy: BacktestStrategy,
    *,
    bars: Sequence[MarketBar] | None = None,
    config: BacktestConfig | None = None,
) -> StrategyValidationResult:
    issues: list[StrategyValidationIssue] = []
    metadata = getattr(strategy, "metadata", None)
    strategy_id = getattr(metadata, "strategy_id", "")

    if not metadata or not strategy_id:
        issues.append(_error("metadata_missing", "Strategy metadata with strategy_id is required."))

    sample_bars = list(bars or ())
    issues.extend(_validate_bars(sample_bars))

    if sample_bars and config is not None and strategy_id:
        context = StrategyContext(
            run_id=config.run_id,
            symbol=config.symbol,
            bar_index=0,
            cash=config.initial_equity,
            positions={},
            pending_orders=[],
            config=config,
        )
        try:
            orders = strategy.generate_orders(bars=[sample_bars[0]], context=context)
        except Exception as exc:
            issues.append(
                _error(
                    "strategy_harness_failed",
                    f"Strategy failed the local validation harness: {exc}",
                )
            )
        else:
            issues.extend(_validate_orders(orders, symbol=config.symbol))

    return StrategyValidationResult(
        strategy_id=strategy_id or "<unknown>",
        status="invalid" if any(issue.severity == "error" for issue in issues) else "valid",
        issues=issues,
        metadata=metadata,
    )


def _validate_bars(bars: Sequence[MarketBar]) -> list[StrategyValidationIssue]:
    issues: list[StrategyValidationIssue] = []
    previous = None
    for index, bar in enumerate(bars):
        if previous is not None and bar.timestamp < previous:
            issues.append(_error("bars_unsorted", "Market bars must be sorted by timestamp."))
            break
        previous = bar.timestamp
        for field in ("open", "high", "low", "close", "volume"):
            value = getattr(bar, field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                issues.append(_error("bar_value_invalid", f"Bar {index} {field} must be finite."))
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            issues.append(_error("bar_price_invalid", f"Bar {index} prices must be positive."))
    return issues


def _validate_orders(orders: Sequence[BacktestOrder], *, symbol: str) -> list[StrategyValidationIssue]:
    issues: list[StrategyValidationIssue] = []
    for index, order in enumerate(orders):
        if order.status != "proposed":
            issues.append(_error("order_status_invalid", f"Order {index} must start as proposed."))
        if order.symbol != symbol:
            issues.append(_error("order_symbol_invalid", f"Order {index} symbol must match the backtest symbol."))
        if order.quantity <= 0 or not math.isfinite(order.quantity):
            issues.append(_error("order_quantity_invalid", f"Order {index} quantity must be positive and finite."))
        if order.price is not None and (order.price <= 0 or not math.isfinite(order.price)):
            issues.append(_error("order_price_invalid", f"Order {index} price must be positive and finite."))
    return issues


def _error(code: str, message: str) -> StrategyValidationIssue:
    return StrategyValidationIssue(severity="error", code=code, message=message)
