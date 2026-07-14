# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/__init__.py
# PURPOSE: Public surface of the broker domain. Note what is exported: the paper
#          broker by name, but the live adapters (Alpaca, Binance) only through the
#          resolver — so reaching a real venue always goes through the guards.
# DEPS:    brokers.base, brokers.guards, brokers.paper, brokers.resolver, brokers.status
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.brokers.base import Broker, BrokerConfigurationError
from atlas_agent.brokers.guards import guard_submit, guard_sync
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.brokers.resolver import BrokerResolver, BrokerStatus, BrokerResolution
from atlas_agent.brokers.status import (
    BrokerSupportEntry,
    BrokerSupportKind,
    get_broker_support_entry,
    is_broker_known,
    is_broker_supported_for_live_submit,
    list_broker_support_inventory,
)


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "Broker",
    "BrokerConfigurationError",
    "BrokerResolution",
    "BrokerResolver",
    "BrokerStatus",
    "BrokerSupportEntry",
    "BrokerSupportKind",
    "PaperBroker",
    "get_broker_support_entry",
    "guard_submit",
    "guard_sync",
    "is_broker_known",
    "is_broker_supported_for_live_submit",
    "list_broker_support_inventory",
]
