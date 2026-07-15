# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_code_inventory_imports.py
# PURPOSE: Verifies code inventory imports behavior and regression expectations.
# DEPS:    importlib, re, pathlib, pytest.
# ==============================================================================

# --- IMPORTS ---

import importlib
import re
from pathlib import Path

import pytest

# These modules were flagged as unused in the code inventory,
# but are intentionally kept to preserve public API compatibility
# or fail-closed stub behavior. We test that they remain importable.
# --- CONFIGURATION AND CONSTANTS ---

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

# Classification taxonomy must stay in sync with docs/development/code-inventory-followups.md
ALLOWED_CLASSIFICATIONS = frozenset([
    "public_api",
    "cli_or_dynamic",
    "test_used",
    "compat_shim",
    "fail_closed_stub",
    "historical",
])

CLASSIFICATIONS = {
    "atlas_agent.ai.analyst": "public_api",
    "atlas_agent.execution.trade_executor": "compat_shim",
    "atlas_agent.market_data.yfinance_provider": "public_api",
    "atlas_agent.notifications.slack_stub": "fail_closed_stub",
    "atlas_agent.notifications.telegram_stub": "fail_closed_stub",
    "atlas_agent.reports.adhoc": "public_api",
    "atlas_agent.risk.position_sizing": "public_api",
    "atlas_agent.safety.policy": "public_api",
    "atlas_agent.scheduler.cron": "public_api",
    "atlas_agent.strategies.base": "public_api",
    "atlas_agent.strategies.breakout": "public_api",
    "atlas_agent.strategies.rsi": "public_api",
    "atlas_agent.tools.contracts": "compat_shim",
    "atlas_agent.tools.runtime": "compat_shim",
    "atlas_agent.setup.inline_select": "public_api",
    "atlas_agent.risk.validation": "test_used",
    "atlas_agent.ai.signal_parser": "test_used",
    "atlas_agent.providers.openrouter": "cli_or_dynamic",
    "atlas_agent.brokers.ibkr_stub": "cli_or_dynamic",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def test_all_candidate_modules_have_classifications():
    """Every candidate module must map to an allowed classification."""
    missing = [m for m in CANDIDATE_MODULES if m not in CLASSIFICATIONS]
    extra = [m for m in CLASSIFICATIONS if m not in CANDIDATE_MODULES]
    assert not missing, f"Missing classifications for: {missing}"
    assert not extra, f"Classifications without candidate modules: {extra}"


def test_classifications_are_allowed():
    """Every classification value must be from the allowed taxonomy."""
    invalid = {c for c in CLASSIFICATIONS.values() if c not in ALLOWED_CLASSIFICATIONS}
    assert not invalid, f"Invalid classifications: {invalid}"


def test_inventory_doc_lists_all_candidate_modules():
    """The markdown inventory table must list the same modules as CANDIDATE_MODULES."""
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "development" / "code-inventory-followups.md"
    assert doc_path.exists(), f"Inventory doc not found: {doc_path}"
    text = doc_path.read_text(encoding="utf-8")
    # Extract module names from inventory table rows only.
    found_modules = set(re.findall(
        r"^\|\s*`src/atlas_agent/([a-z0-9_/]+\.py)`\s*\|",
        text,
        re.MULTILINE,
    ))
    # Convert to dotted module names
    found_dotted = {"atlas_agent." + m.replace("/", ".")[:-3] for m in found_modules}
    expected = set(CANDIDATE_MODULES)
    missing_in_doc = expected - found_dotted
    extra_in_doc = found_dotted - expected
    assert not missing_in_doc, f"Candidate modules missing from inventory doc: {sorted(missing_in_doc)}"
    assert not extra_in_doc, f"Inventory doc has extra modules not in CANDIDATE_MODULES: {sorted(extra_in_doc)}"
