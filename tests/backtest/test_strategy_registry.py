from __future__ import annotations

from atlas_agent.backtest.registry import default_strategy_registry


def test_default_registry_lists_builtin_buy_and_hold() -> None:
    registry = default_strategy_registry(include_entry_points=False)

    strategies = registry.list_metadata()

    assert [item.strategy_id for item in strategies] == [
        "buy_and_hold",
        "moving_average_cross",
        "rsi_mean_reversion",
    ]
    assert strategies[0].name == "Buy and Hold"
    assert "builtin" in strategies[0].tags


def test_registry_loads_fresh_strategy_instances() -> None:
    registry = default_strategy_registry(include_entry_points=False)

    first = registry.get("buy_and_hold")
    second = registry.get("buy_and_hold")

    assert first is not second
    assert first.metadata.strategy_id == "buy_and_hold"
    assert second.metadata.strategy_id == "buy_and_hold"


def test_registry_applies_strategy_parameters() -> None:
    registry = default_strategy_registry(include_entry_points=False)

    strategy = registry.get(
        "moving_average_cross",
        parameters={"short_window": "2", "long_window": "4", "exit_on_cross": "false"},
    )

    assert strategy.short_window == 2
    assert strategy.long_window == 4
    assert strategy.exit_on_cross is False
