# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/base.py
# PURPOSE: The contracts every broker adapter satisfies. Structural (Protocol),
#          not inherited: an adapter is anything with the right methods, so a paper
#          broker, a real venue and a test double are interchangeable to the rest
#          of the system — which is what makes the order path testable at all.
# DEPS:    execution.order (order/result types), brokers.models (sync types)
# ==============================================================================

# --- IMPORTS ---
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


# ==============================================================================
# TRADING CONTRACT (the write path)
# ==============================================================================

# Deliberately minimal — five methods. Every capability here can MOVE MONEY, so the
# surface is kept as small as the system can function with. Anything a broker can
# additionally do stays off this Protocol and out of the order path.
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


# ==============================================================================
# SYNC CONTRACT (the read path)
# ==============================================================================

# Split from Broker on purpose: this interface is READ-ONLY. Reconciliation and
# status reporting only need to observe the venue, and giving them an object that
# cannot place an order means they structurally cannot cause one.
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


# ==============================================================================
# ERRORS
# ==============================================================================

# Two distinct types, because the two failures demand opposite responses:
#   - Configuration → we never reached the venue. Nothing happened. Safe to retry
#     once the config is fixed.
#   - Operation     → we DID reach the venue, or may have. The outcome is unknown,
#     and a blind retry risks a duplicate order. This is reconciliation's problem.
class BrokerConfigurationError(RuntimeError):
    pass


class BrokerOperationError(RuntimeError):
    """Raised when a broker operation fails due to provider-side or transport-side error."""
