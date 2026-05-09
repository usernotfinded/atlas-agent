from __future__ import annotations

from typing import Protocol, List

from atlas_agent.brokers.models import (
    BrokerAccountState,
    BrokerPosition,
    BrokerOrder,
    BrokerBalance,
)
from atlas_agent.execution.order import (
    AccountSnapshot,
    FlattenResult,
    Order,
    OrderResult,
)
from atlas_agent.portfolio.positions import Position


class Broker(Protocol):
    def get_account(self) -> AccountSnapshot:
        ...

    def get_positions(self) -> list[Position]:
        ...

    def place_order(self, order: Order) -> OrderResult:
        ...

    def cancel_order(self, order_id: str) -> OrderResult:
        ...

    def flatten_all(
        self,
        strategy: str = "market",
        bps: int = 25,
    ) -> FlattenResult:
        ...


class BrokerProvider(Protocol):
    """
    Interface for broker data synchronization.
    """
    def get_account_state(self) -> BrokerAccountState:
        ...

    def get_positions(self) -> List[BrokerPosition]:
        ...

    def get_open_orders(self) -> List[BrokerOrder]:
        ...

    def get_balances(self) -> List[BrokerBalance]:
        ...


class BrokerConfigurationError(RuntimeError):
    pass
