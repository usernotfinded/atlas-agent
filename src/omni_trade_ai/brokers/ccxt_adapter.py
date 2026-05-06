from __future__ import annotations

from dataclasses import dataclass

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.brokers.base import BrokerConfigurationError
from omni_trade_ai.execution.order import AccountSnapshot, Order, OrderResult
from omni_trade_ai.portfolio.positions import Position


@dataclass(frozen=True)
class CCXTBroker:
    config: OmniTradeConfig

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

