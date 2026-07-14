# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/ccxt_adapter.py
# PURPOSE: A CCXT adapter that is deliberately switched off. It satisfies the Broker
#          protocol so the type system is happy, and raises on every method so the
#          runtime is not: a generic exchange bridge is too broad a capability to
#          enable without a per-venue review.
# DEPS:    brokers.base (BrokerConfigurationError), config
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.config import AtlasConfig
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.execution.order import AccountSnapshot, FlattenResult, Order, OrderResult
from atlas_agent.portfolio.positions import Position


# ==============================================================================
# DISABLED CCXT ADAPTER
# ==============================================================================

@dataclass(frozen=True)
class CCXTBroker:
    config: AtlasConfig

    # Every method raises the SAME error. The shape is fully implemented, the behaviour
    # is not — so this adapter can be resolved and type-checked, but can never place an
    # order by accident.
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

    def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
        raise self._disabled()
