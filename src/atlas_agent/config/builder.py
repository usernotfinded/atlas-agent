# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/builder.py
# PURPOSE: Assembles the one config object the whole runtime reads, by layering
#          defaults, the TOML file and CLI overrides in a fixed precedence order.
# DEPS:    pydantic (validation), config.schema / config.store / config.secrets
# ==============================================================================

# --- IMPORTS ---
from typing import Any, Dict, Optional
from pydantic import ValidationError

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.config.store import get_raw_config
from atlas_agent.config.secrets import load_atlas_secrets
from atlas_agent.config.errors import format_schema_validation_error


# ==============================================================================
# EFFECTIVE CONFIG ASSEMBLY
# ==============================================================================

def get_effective_config(cli_overrides: Optional[Dict[str, Any]] = None) -> AtlasConfig:
    """
    Build the effective runtime configuration.

    Precedence:
    Non-secrets: CLI > .atlas/config.toml > defaults
    Secrets: CLI (if supported) > Process Env > .env.atlas > defaults
    """
    # Secrets travel through os.environ, never through the config dict, so that a
    # dumped or logged AtlasConfig can never carry a credential.
    load_atlas_secrets()

    config_dict = get_raw_config()

    # Overrides are applied to the *raw* dict, before validation, rather than to the
    # built model. This means a bad --set value fails schema validation exactly like
    # a bad value in the TOML file, instead of bypassing the checks entirely.
    if cli_overrides:
        for dotted_path, value in cli_overrides.items():
            _apply_dotted_override(config_dict, dotted_path, value)

    try:
        config = AtlasConfig.model_validate(config_dict)
    except ValidationError as exc:
        # Re-raised as AtlasConfigError: a raw pydantic traceback is not something an
        # operator should have to read to learn that a risk limit is out of range.
        raise format_schema_validation_error(exc) from exc

    return config


# --- Override plumbing ---

def _apply_dotted_override(target: dict, dotted_path: str, value: Any) -> None:
    # Intermediate segments are force-created as dicts, clobbering a scalar if one
    # sits in the way. `--set risk.limits.max=5` must work even when `risk.limits`
    # is absent, and a scalar there is a malformed config we are about to reject
    # in validation anyway.
    parts = dotted_path.split(".")
    current = target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
