from __future__ import annotations

import pytest

from atlas_agent.brokers.status import (
    get_broker_support_entry,
    is_broker_known,
    is_broker_supported_for_live_submit,
    list_broker_support_inventory,
)


@pytest.mark.parametrize(
    "broker_id, expected_status",
    [
        ("paper", "default_paper"),
        ("alpaca", "supported_opt_in"),
        ("binance", "partial"),
        ("ccxt", "disabled"),
        ("ibkr", "placeholder"),
    ],
)
def test_broker_support_inventory_includes_expected_brokers(
    broker_id: str, expected_status: str
) -> None:
    inventory = list_broker_support_inventory()
    ids = [entry.broker_id for entry in inventory]
    assert broker_id in ids

    entry = get_broker_support_entry(broker_id)
    assert entry is not None
    assert entry.broker_id == broker_id
    assert entry.status == expected_status


def test_paper_broker_marked_default_paper() -> None:
    entry = get_broker_support_entry("paper")
    assert entry is not None
    assert entry.status == "default_paper"
    assert entry.paper_supported is True
    assert entry.default_enabled is True
    assert entry.requires_explicit_opt_in is False


def test_alpaca_marked_supported_opt_in() -> None:
    entry = get_broker_support_entry("alpaca")
    assert entry is not None
    assert entry.status == "supported_opt_in"
    assert entry.live_submit_supported is True
    assert entry.requires_explicit_opt_in is True
    assert entry.default_enabled is False


def test_binance_marked_partial() -> None:
    entry = get_broker_support_entry("binance")
    assert entry is not None
    assert entry.status == "partial"
    assert entry.live_submit_supported is False
    assert entry.read_only_supported is False
    assert entry.requires_explicit_opt_in is True


def test_ccxt_marked_disabled() -> None:
    entry = get_broker_support_entry("ccxt")
    assert entry is not None
    assert entry.status == "disabled"
    assert entry.live_submit_supported is False
    assert entry.default_enabled is False


def test_ibkr_marked_placeholder() -> None:
    entry = get_broker_support_entry("ibkr")
    assert entry is not None
    assert entry.status == "placeholder"
    assert entry.live_submit_supported is False
    assert entry.read_only_supported is False


def test_unknown_broker_returns_none() -> None:
    assert get_broker_support_entry("not_a_real_broker") is None
    assert is_broker_known("not_a_real_broker") is False


def test_is_broker_supported_for_live_submit_only_for_explicit() -> None:
    assert is_broker_supported_for_live_submit("paper") is False
    assert is_broker_supported_for_live_submit("alpaca") is True
    assert is_broker_supported_for_live_submit("binance") is False
    assert is_broker_supported_for_live_submit("ccxt") is False
    assert is_broker_supported_for_live_submit("ibkr") is False
    assert is_broker_supported_for_live_submit("unknown") is False


def test_inventory_sorted_with_paper_first() -> None:
    inventory = list_broker_support_inventory()
    assert inventory[0].broker_id == "paper"
