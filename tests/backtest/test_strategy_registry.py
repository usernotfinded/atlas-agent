from __future__ import annotations

from atlas_agent.backtest.registry import default_strategy_registry


def test_default_registry_lists_builtin_buy_and_hold() -> None:
    registry = default_strategy_registry(include_entry_points=False)

    strategies = registry.list_metadata()

    assert [item.strategy_id for item in strategies] == [
        "buy_and_hold",
        "demo_stateful_paper",
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


def test_entry_points_are_declared_in_pyproject_toml():
    import tomllib
    from pathlib import Path

    pyproject = Path("pyproject.toml")
    assert pyproject.exists()
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    eps = data.get("project", {}).get("entry-points", {}).get("atlas_agent.backtest_strategies", {})
    assert "buy_and_hold" in eps
    assert "moving_average_cross" in eps
    assert "rsi_mean_reversion" in eps


def test_entry_points_load_correctly():
    from importlib import metadata as importlib_metadata

    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        candidates = list(entry_points.select(group="atlas_agent.backtest_strategies"))
    else:
        candidates = list(entry_points.get("atlas_agent.backtest_strategies", ()))

    for ep in candidates:
        loaded = ep.load()
        assert hasattr(loaded, "metadata")
        assert hasattr(loaded, "generate_orders")


def test_registry_with_entry_points_discovers_builtins():
    registry = default_strategy_registry(include_entry_points=True)

    strategies = registry.list_metadata()
    strategy_ids = [item.strategy_id for item in strategies]

    assert "buy_and_hold" in strategy_ids
    assert "moving_average_cross" in strategy_ids
    assert "rsi_mean_reversion" in strategy_ids
