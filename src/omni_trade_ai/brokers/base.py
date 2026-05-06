from __future__ import annotations

from typing import Protocol

from omni_trade_ai.execution.order import AccountSnapshot, Order, OrderResult
from omni_trade_ai.portfolio.positions import Position


class Broker(Protocol):
    def get_account(self) -> AccountSnapshot:
        ...

    def get_positions(self) -> list[Position]:
        ...

    def place_order(self, order: Order) -> OrderResult:
        ...

    def cancel_order(self, order_id: str) -> OrderResult:
        ...


class BrokerConfigurationError(RuntimeError):
    pass

