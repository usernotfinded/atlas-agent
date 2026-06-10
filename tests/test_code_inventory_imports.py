import importlib
import pytest

# These modules were flagged as unused in the code inventory,
# but are intentionally kept to preserve public API compatibility
# or fail-closed stub behavior. We test that they remain importable.
CANDIDATE_MODULES = [
    "atlas_agent.ai.analyst",
    "atlas_agent.execution.trade_executor",
    "atlas_agent.market_data.yfinance_provider",
    "atlas_agent.notifications.slack_stub",
    "atlas_agent.notifications.telegram_stub",
    "atlas_agent.reports.adhoc",
    "atlas_agent.risk.position_sizing",
    "atlas_agent.safety.policy",
    "atlas_agent.scheduler.cron",
    "atlas_agent.strategies.base",
    "atlas_agent.strategies.breakout",
    "atlas_agent.strategies.rsi",
    "atlas_agent.tools.contracts",
    "atlas_agent.tools.runtime",
    "atlas_agent.setup.inline_select",
    "atlas_agent.risk.validation",
    "atlas_agent.ai.signal_parser",
    "atlas_agent.providers.openrouter",
    "atlas_agent.brokers.ibkr_stub",
]

@pytest.mark.parametrize("module_name", CANDIDATE_MODULES)
def test_inventory_module_is_importable(module_name):
    """
    Ensure deferred code inventory candidate modules can be imported.
    If a module is removed in the future, remove it from this list
    only after proving it breaks no public APIs.
    """
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        pytest.fail(f"Failed to import {module_name}: {exc}")
