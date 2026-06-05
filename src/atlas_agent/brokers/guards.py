from __future__ import annotations

from typing import TYPE_CHECKING

from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.status import (
    BrokerSupportEntry,
    get_broker_support_entry,
    is_broker_known,
)

if TYPE_CHECKING:
    from atlas_agent.config import AtlasConfig


def _guard_error(operation: str, broker_id: str, reason: str) -> BrokerConfigurationError:
    return BrokerConfigurationError(
        f"[{operation}] broker={broker_id}: {reason}"
    )


def guard_submit(
    *,
    broker_id: str,
    config: AtlasConfig,
    operation: str = "submit_order",
) -> BrokerSupportEntry:
    """Fail-closed guard for live broker order submission.

    Raises BrokerConfigurationError unless the broker is explicitly supported
    for live submit and all required opt-in gates are satisfied. This function
    does not call any broker API and does not read credential values.
    """
    if not is_broker_known(broker_id):
        raise _guard_error(
            operation,
            broker_id,
            "unsupported broker; execution is blocked",
        )

    entry = get_broker_support_entry(broker_id)
    assert entry is not None

    if entry.status == "placeholder":
        raise _guard_error(
            operation,
            broker_id,
            "broker is a placeholder; execution is not implemented",
        )

    if entry.status == "disabled":
        raise _guard_error(
            operation,
            broker_id,
            "broker is disabled until explicitly configured",
        )

    if entry.status == "unsupported":
        raise _guard_error(
            operation,
            broker_id,
            "broker is unsupported; execution is blocked",
        )

    if not entry.live_submit_supported:
        raise _guard_error(
            operation,
            broker_id,
            f"broker status is {entry.status}; live submit is not supported",
        )

    if not config.broker.enable_live_trading:
        raise _guard_error(
            operation,
            broker_id,
            "broker.enable_live_trading is false",
        )

    if not config.broker.enable_live_submit:
        raise _guard_error(
            operation,
            broker_id,
            "broker.enable_live_submit is false",
        )

    if config.trading_mode != "live":
        raise _guard_error(
            operation,
            broker_id,
            f"trading_mode is {config.trading_mode}; must be live",
        )

    return entry


def guard_sync(
    *,
    broker_id: str,
    config: AtlasConfig,
    operation: str = "sync_account",
) -> BrokerSupportEntry:
    """Fail-closed guard for live broker read-only sync.

    Raises BrokerConfigurationError unless the broker is explicitly supported
    for read-only sync. This function does not call any broker API.
    """
    if not is_broker_known(broker_id):
        raise _guard_error(
            operation,
            broker_id,
            "unsupported broker; sync is blocked",
        )

    entry = get_broker_support_entry(broker_id)
    assert entry is not None

    if entry.status == "placeholder":
        raise _guard_error(
            operation,
            broker_id,
            "broker is a placeholder; sync is not implemented",
        )

    if entry.status == "disabled":
        raise _guard_error(
            operation,
            broker_id,
            "broker is disabled until explicitly configured",
        )

    if not entry.read_only_supported:
        raise _guard_error(
            operation,
            broker_id,
            f"broker status is {entry.status}; read-only sync is not supported",
        )

    if not config.broker.enable_live_trading:
        raise _guard_error(
            operation,
            broker_id,
            "broker.enable_live_trading is false",
        )

    if config.trading_mode != "live":
        raise _guard_error(
            operation,
            broker_id,
            f"trading_mode is {config.trading_mode}; must be live",
        )

    return entry
