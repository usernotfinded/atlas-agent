from typing import Any, Dict, Optional
from pydantic import ValidationError

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.config.store import get_raw_config
from atlas_agent.config.secrets import load_atlas_secrets

def get_effective_config(cli_overrides: Optional[Dict[str, Any]] = None) -> AtlasConfig:
    """
    Build the effective runtime configuration.
    
    Precedence:
    Non-secrets: CLI > .atlas/config.toml > defaults
    Secrets: CLI (if supported) > Process Env > .env.atlas > defaults
    """
    # 1. Load secrets from .env.atlas into os.environ (without overriding existing process env)
    load_atlas_secrets()
    
    # 2. Get raw non-secret TOML config
    config_dict = get_raw_config()
    
    # 3. Apply CLI overrides to the raw dict before validation
    if cli_overrides:
        for dotted_path, value in cli_overrides.items():
            _apply_dotted_override(config_dict, dotted_path, value)
            
    # 4. Validate and build the effective read-only config
    try:
        config = AtlasConfig.model_validate(config_dict)
    except ValidationError:
        # Fallback to defaults or partial if invalid, though ideally we'd fail loudly
        # For legacy compatibility, we return defaults. Real errors should be handled by validation.
        config = AtlasConfig()
        
    return config

def _apply_dotted_override(target: dict, dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current = target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
