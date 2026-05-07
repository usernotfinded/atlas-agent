from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.config import AtlasConfig
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.execution.order import AccountSnapshot, Order, OrderResult
from atlas_agent.portfolio.positions import Position


@dataclass(frozen=True)
class CCXTBroker:
    config: AtlasConfig

    def _disabled(self) -> BrokerConfigurationError:
        return BrokerConfigurationError(
            "generic CCXT live adapter is disabled until explicitly configured"
        )

    def get_account(self) -> AccountSnapshot:
        raise self._disabled()

    def get_positions(self) -> list[Position]:
        raise self._disabled()

    def place_order(self, order: Order) -> OrderResult:
        raise self._disabled()

    def cancel_order(self, order_id: str) -> OrderResult:
        raise self._disabled()

