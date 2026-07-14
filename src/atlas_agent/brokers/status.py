# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/status.py
# PURPOSE: The static support matrix — which brokers exist, and exactly what each
#          is allowed to do. This table is the ALLOWLIST that brokers/guards.py
#          enforces: a broker absent from it cannot trade, full stop.
# DEPS:    none (pure data — no network, no credentials, no runtime resolution)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --- CONFIGURATIONS & CONSTANTS ---

# Only "default_paper" and "supported_opt_in" can reach a live venue. The other four
# are all shades of no — the distinction exists so an operator gets told WHY a broker
# is unavailable ("not implemented" vs "not configured" vs "will never be supported")
# rather than a flat refusal.
BrokerSupportKind = Literal[
    "default_paper",
    "supported_opt_in",
    "partial",
    "disabled",
    "placeholder",
    "unsupported",
]


# ==============================================================================
# SUPPORT ENTRY
# ==============================================================================

@dataclass(frozen=True)
class BrokerSupportEntry:
    """Static support inventory entry for a broker adapter.

    This is documentation and guard metadata. It does not perform runtime
    resolution or call any broker APIs.
    """

    broker_id: str
    display_name: str
    status: BrokerSupportKind

    # Three capabilities, granted separately and in increasing danger:
    #   paper      → simulate only, no network;
    #   read_only  → observe a real account (guard_sync);
    #   live_submit→ place real orders (guard_submit).
    # A broker can be trusted to be read while still being barred from writing.
    paper_supported: bool
    read_only_supported: bool
    live_submit_supported: bool

    requires_explicit_opt_in: bool
    default_enabled: bool
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "status": self.status,
            "paper_supported": self.paper_supported,
            "read_only_supported": self.read_only_supported,
            "live_submit_supported": self.live_submit_supported,
            "requires_explicit_opt_in": self.requires_explicit_opt_in,
            "default_enabled": self.default_enabled,
            "notes": self.notes,
        }


# ==============================================================================
# SUPPORT INVENTORY
# ==============================================================================

# Static support inventory. Keep this in sync with actual adapter implementations.
# This table is intentionally conservative: if a broker is not explicitly ready,
# it is marked disabled/placeholder/unsupported.
#
# The conservatism is structural, not stylistic: a broker that is merely FORGOTTEN
# here is treated as unknown, and unknown means blocked. Omission fails safe.
_BROKER_SUPPORT_INVENTORY: tuple[BrokerSupportEntry, ...] = (
    BrokerSupportEntry(
        broker_id="paper",
        display_name="PaperBroker",
        status="default_paper",
        paper_supported=True,
        read_only_supported=True,
        live_submit_supported=False,
        requires_explicit_opt_in=False,
        default_enabled=True,
        notes=(
            "Default safe local/paper execution path. "
            "Deterministic simulation with no network calls and no real credentials."
        ),
    ),
    BrokerSupportEntry(
        broker_id="alpaca",
        display_name="Alpaca",
        status="supported_opt_in",
        paper_supported=False,
        read_only_supported=True,
        live_submit_supported=True,
        requires_explicit_opt_in=True,
        default_enabled=False,
        notes=(
            "Alpaca Markets adapter supports read-only sync and explicitly opted-in live submit. "
            "Requires ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables, "
            "live trading enabled, live submit enabled, kill switch normal, opt-in record valid, "
            "and ALPACA_ENDPOINT_MODE set to paper or live."
        ),
    ),
    BrokerSupportEntry(
        broker_id="binance",
        display_name="Binance",
        status="partial",
        paper_supported=False,
        read_only_supported=False,
        live_submit_supported=False,
        requires_explicit_opt_in=True,
        default_enabled=False,
        notes=(
            "Binance adapter is partial and guarded. The implementation exists for explicit "
            "opt-in workflows but live submit is deferred pending additional safety review. "
            "Requires BINANCE_API_KEY and BINANCE_API_SECRET, ccxt dependency, and "
            "explicit live trading + live submit + opt-in gates."
        ),
    ),
    BrokerSupportEntry(
        broker_id="ccxt",
        display_name="CCXT (generic)",
        status="disabled",
        paper_supported=False,
        read_only_supported=False,
        live_submit_supported=False,
        requires_explicit_opt_in=True,
        default_enabled=False,
        notes=(
            "Generic CCXT live adapter is disabled until explicitly configured. "
            "All broker methods raise BrokerConfigurationError. "
            "Per-exchange CCXT support may be added in the future under explicit opt-in."
        ),
    ),
    BrokerSupportEntry(
        broker_id="ibkr",
        display_name="Interactive Brokers (IBKR)",
        status="placeholder",
        paper_supported=False,
        read_only_supported=False,
        live_submit_supported=False,
        requires_explicit_opt_in=True,
        default_enabled=False,
        notes=(
            "IBKR is a placeholder only. No execution, sync, or submit implementation is provided. "
            "Any attempt to call an IBKR adapter method raises NotImplementedError."
        ),
    ),
)


_BROKER_SUPPORT_BY_ID: dict[str, BrokerSupportEntry] = {
    entry.broker_id: entry for entry in _BROKER_SUPPORT_INVENTORY
}


def list_broker_support_inventory() -> tuple[BrokerSupportEntry, ...]:
    """Return the full broker support inventory, ordered from safest to least supported."""
    return _BROKER_SUPPORT_INVENTORY


def get_broker_support_entry(broker_id: str) -> BrokerSupportEntry | None:
    """Look up a support entry by broker_id, or None if unknown."""
    return _BROKER_SUPPORT_BY_ID.get(broker_id)


def is_broker_supported_for_live_submit(broker_id: str) -> bool:
    """Return True only if the broker is explicitly marked live_submit_supported."""
    entry = get_broker_support_entry(broker_id)
    if entry is None:
        return False
    return entry.live_submit_supported and entry.status in {"supported_opt_in", "default_paper"}


def is_broker_known(broker_id: str) -> bool:
    """Return True if broker_id appears in the support inventory."""
    return broker_id in _BROKER_SUPPORT_BY_ID
