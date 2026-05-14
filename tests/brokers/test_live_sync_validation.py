from __future__ import annotations

import pytest

from atlas_agent.brokers.live_sync_validation import validate_live_sync
from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
from atlas_agent.brokers.resolver import BrokerStatus


def _status() -> BrokerStatus:
    return BrokerStatus(
        mode="live",
        broker_id="alpaca",
        configured=True,
        credentials_configured=True,
        can_sync=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )


def _sync_result(
    *,
    account: BrokerAccountState | None = None,
    diagnostics: dict | None = None,
) -> BrokerSyncResult:
    return BrokerSyncResult(
        status="success",
        account=account,
        diagnostics=diagnostics or {"broker_errors": []},
    )


def test_validate_live_sync_success_no_errors() -> None:
    account = BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0)
    sync_result = _sync_result(account=account)
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is None


def test_validate_live_sync_malformed_broker_errors_list() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": "not-a-list"},
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert error["status"] == "error"
    assert "malformed" in error["errors"][0].lower()
    assert error["diagnostics"]["failed_operations"] == ["malformed_broker_errors"]


def test_validate_live_sync_malformed_entry_missing_field() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": [{"code": "x", "operation": "sync_balances", "broker": "alpaca"}]},
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert error["diagnostics"]["failed_operations"] == ["malformed_broker_errors"]


def test_validate_live_sync_malformed_entry_non_string_value() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": [{"code": "x", "operation": "sync_balances", "broker": "alpaca", "message": 123}]},
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert error["diagnostics"]["failed_operations"] == ["malformed_broker_errors"]


def test_validate_live_sync_critical_failure_account() -> None:
    sync_result = _sync_result(
        account=None,
        diagnostics={"broker_errors": []},
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert "sync_account_state" in error["errors"][0]
    assert "sync_account_state" in error["diagnostics"]["failed_operations"]


def test_validate_live_sync_critical_failure_positions() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={
            "broker_errors": [
                {
                    "code": "broker_operation_failed",
                    "operation": "sync_positions",
                    "broker": "alpaca",
                    "message": "positions sync failed",
                }
            ]
        },
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert "sync_positions" in error["errors"][0]
    assert "sync_positions" in error["diagnostics"]["failed_operations"]


def test_validate_live_sync_critical_failure_open_orders() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={
            "broker_errors": [
                {
                    "code": "broker_operation_failed",
                    "operation": "sync_open_orders",
                    "broker": "alpaca",
                    "message": "open orders sync failed",
                }
            ]
        },
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    assert "sync_open_orders" in error["errors"][0]
    assert "sync_open_orders" in error["diagnostics"]["failed_operations"]


def test_validate_live_sync_noncritical_balances_warning() -> None:
    sync_result = _sync_result(
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={
            "broker_errors": [
                {
                    "code": "broker_operation_failed",
                    "operation": "sync_balances",
                    "broker": "alpaca",
                    "message": "balances sync failed",
                }
            ]
        },
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert error is None
    assert len(warnings) == 1
    assert warnings[0]["operation"] == "sync_balances"
    assert warnings[0]["code"] == "broker_operation_failed"
    assert warnings[0]["broker"] == "alpaca"


def test_validate_live_sync_multiple_critical_failures() -> None:
    sync_result = _sync_result(
        account=None,
        diagnostics={
            "broker_errors": [
                {
                    "code": "broker_operation_failed",
                    "operation": "sync_positions",
                    "broker": "alpaca",
                    "message": "positions sync failed",
                },
                {
                    "code": "broker_operation_failed",
                    "operation": "sync_open_orders",
                    "broker": "alpaca",
                    "message": "open orders sync failed",
                },
            ]
        },
    )
    warnings, error = validate_live_sync(sync_result, _status())
    assert warnings == []
    assert error is not None
    failed = error["diagnostics"]["failed_operations"]
    assert "sync_account_state" in failed
    assert "sync_positions" in failed
    assert "sync_open_orders" in failed
