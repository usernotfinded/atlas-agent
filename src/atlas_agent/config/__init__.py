from typing import Any
from atlas_agent.config.schema import (
    AtlasConfig, 
    parse_bool, 
    parse_float, 
    parse_int, 
    parse_csv_set
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

# Aliases for backwards compatibility
get_config = get_effective_config
set_atlas_secret = set_secret

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

__all__ = [
    "AtlasConfig",
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
