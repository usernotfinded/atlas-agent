# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_broker_errors.py
# PURPOSE: Verifies broker errors behavior and regression expectations.
# DEPS:    urllib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from urllib.error import URLError

from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.errors import (
    BROKER_ERROR_CODE_CONFIG,
    BROKER_ERROR_CODE_DEPENDENCY,
    BROKER_ERROR_CODE_OPERATION,
    BROKER_ERROR_CODE_TRANSPORT,
    make_broker_error,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_make_broker_error_sanitizes_configuration_exceptions() -> None:
    exc = BrokerConfigurationError(
        "BINANCE_API_SECRET=super-secret-token should never appear"
    )

    error = make_broker_error(
        operation="place_order",
        broker="binance",
        exc=exc,
    )

    serialized = str(error.to_dict()) + " " + error.to_error_string()
    assert error.code == BROKER_ERROR_CODE_CONFIG
    assert error.operation == "place_order"
    assert error.broker == "binance"
    assert error.message == "broker configuration is invalid or incomplete"
    assert "super-secret-token" not in serialized
    assert "BINANCE_API_SECRET=" not in serialized


def test_make_broker_error_sanitizes_dependency_transport_and_operation_exceptions() -> None:
    dependency_error = make_broker_error(
        operation="place_order",
        broker="binance",
        exc=ModuleNotFoundError("ccxt missing with token sk-test-raw-secret"),
    )
    transport_error = make_broker_error(
        operation="sync_positions",
        broker="binance",
        exc=URLError("https://exchange.example/v1?api_key=raw-secret"),
    )
    operation_error = make_broker_error(
        operation="sync_open_orders",
        broker="binance",
        exc=RuntimeError("account_id=acct-1 token=raw-secret"),
    )

    assert dependency_error.code == BROKER_ERROR_CODE_DEPENDENCY
    assert dependency_error.message == "required broker dependency is unavailable"

    assert transport_error.code == BROKER_ERROR_CODE_TRANSPORT
    assert transport_error.message == "broker transport request failed"

    assert operation_error.code == BROKER_ERROR_CODE_OPERATION
    assert operation_error.message == "broker operation failed"

    combined = " ".join(
        [
            dependency_error.to_error_string(),
            transport_error.to_error_string(),
            operation_error.to_error_string(),
            str(dependency_error.to_dict()),
            str(transport_error.to_dict()),
            str(operation_error.to_dict()),
        ]
    )
    assert "raw-secret" not in combined
    assert "api_key=" not in combined
    assert "account_id=" not in combined
