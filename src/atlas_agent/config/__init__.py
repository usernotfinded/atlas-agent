# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/__init__.py
# PURPOSE: Public surface of the config domain. Callers import from here and stay
#          unaware of the split between the TOML store and the secret store — the
#          routing between the two happens below.
# DEPS:    config.schema, config.builder, config.store, config.secrets, config.migrate
# ==============================================================================

# --- IMPORTS ---
from typing import Any
from atlas_agent.config.schema import (
    AtlasConfig,
    BacktestConfig,
    MarketConfig,
    parse_bool,
    parse_float,
    parse_int,
    parse_csv_set,
)
from atlas_agent.config.builder import get_effective_config
from atlas_agent.config.store import (
    get_raw_config, 
    get_raw_value, 
    set_raw_value, 
    unset_raw_value
)
from atlas_agent.config.secrets import (
    set_secret, 
    unset_secret,
    get_secret, 
    get_secret_status,
    is_secret_key,
    redact_value
)
from atlas_agent.config.migrate import migrate_legacy_config

# --- CONFIGURATIONS & CONSTANTS ---

# Aliases for backwards compatibility
get_config = get_effective_config
set_atlas_secret = set_secret


# ==============================================================================
# WRITE ROUTING (SECRET vs NON-SECRET)
# ==============================================================================
#
# These two wrappers are the reason callers can stay ignorant of the two stores:
# the key itself decides where the value goes. Note that set_raw_value() *also*
# rejects secrets on its own — the check here routes, the one there enforces. Two
# layers, because a credential written into a committable config.toml is not a
# mistake you get to undo.

def update_config_value(key: str, value: Any, *args, **kwargs):
    """Compatibility wrapper for updating config values."""
    if is_secret_key(key):
        return set_secret(key, value, *args, **kwargs)
    return set_raw_value(key, value, *args, **kwargs)

def delete_config_value(key: str, *args, **kwargs):
    """Compatibility wrapper for deleting config values."""
    if is_secret_key(key):
        return unset_secret(key, *args, **kwargs)
    return unset_raw_value(key, *args, **kwargs)


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "AtlasConfig",
    "BacktestConfig",
    "MarketConfig",
    "get_config",
    "get_effective_config",
    "update_config_value",
    "delete_config_value",
    "get_raw_config",
    "get_raw_value",
    "set_raw_value",
    "unset_raw_value",
    "set_atlas_secret",
    "set_secret",
    "unset_secret",
    "get_secret",
    "get_secret_status",
    "is_secret_key",
    "redact_value",
    "migrate_legacy_config",
    "parse_bool",
    "parse_float",
    "parse_int",
    "parse_csv_set",
]
