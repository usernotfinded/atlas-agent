# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/registry.py
# PURPOSE: Maps a strategy id to its factory. Also discovers third-party strategies
#          via entry points, which is how a user plugs in their own without editing
#          this file.
# DEPS:    importlib.metadata (entry points), backtest.strategies
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from importlib import metadata as importlib_metadata
from typing import Callable

from atlas_agent.backtest.demo_strategy import DemoStatefulPaperStrategy
from atlas_agent.backtest.strategies import (
    BuyAndHoldStrategy,
    MovingAverageCrossStrategy,
    RSIMeanReversionStrategy,
)
from atlas_agent.backtest.strategy import (
    BacktestStrategy,
    StrategyMetadata,
    coerce_strategy_parameters,
)


StrategyFactory = Callable[[], BacktestStrategy]

_ENTRY_POINT_GROUP = "atlas_agent.backtest_strategies"


class StrategyRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, StrategyFactory] = {}

    def register(self, factory: StrategyFactory) -> None:
        strategy = factory()
        strategy_id = strategy.metadata.strategy_id
        if not strategy_id:
            raise ValueError("strategy_id is required")
        self._factories[strategy_id] = factory

    def get(
        self,
        strategy_id: str,
        parameters: dict[str, object] | None = None,
    ) -> BacktestStrategy:
        try:
            factory = self._factories[strategy_id]
        except KeyError as exc:
            raise KeyError(f"Unknown backtest strategy: {strategy_id}") from exc
        metadata = factory().metadata
        coerced = coerce_strategy_parameters(metadata, parameters)
        return factory(**coerced)

    def list_metadata(self) -> list[StrategyMetadata]:
        return sorted(
            (factory().metadata for factory in self._factories.values()),
            key=lambda item: item.strategy_id,
        )

    def describe(self, strategy_id: str) -> StrategyMetadata:
        return self.get(strategy_id).metadata


def default_strategy_registry(*, include_entry_points: bool = True) -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(BuyAndHoldStrategy)
    registry.register(MovingAverageCrossStrategy)
    registry.register(RSIMeanReversionStrategy)
    registry.register(DemoStatefulPaperStrategy)
    if include_entry_points:
        _discover_entry_point_strategies(registry)
    return registry


def _discover_entry_point_strategies(registry: StrategyRegistry) -> None:
    try:
        entry_points = importlib_metadata.entry_points()
        if hasattr(entry_points, "select"):
            candidates = entry_points.select(group=_ENTRY_POINT_GROUP)
        else:
            candidates = entry_points.get(_ENTRY_POINT_GROUP, ())
    except Exception:
        return

    for entry_point in candidates:
        try:
            loaded = entry_point.load()
            registry.register(loaded)
        except Exception:
            continue


def list_strategies() -> list[StrategyMetadata]:
    return default_strategy_registry().list_metadata()


def get_strategy(
    strategy_id: str,
    parameters: dict[str, object] | None = None,
) -> BacktestStrategy:
    return default_strategy_registry().get(strategy_id, parameters=parameters)


def describe_strategy(strategy_id: str) -> StrategyMetadata:
    return default_strategy_registry().describe(strategy_id)
