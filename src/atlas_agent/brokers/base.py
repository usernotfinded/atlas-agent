from __future__ import annotations

from typing import Protocol

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


class BrokerConfigurationError(RuntimeError):
    pass
