import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
import tomlkit
from pydantic import ValidationError

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path
from atlas_agent.config.secrets import load_atlas_secrets, is_secret_key, set_atlas_secret

def load_raw_config() -> dict:
    """Load raw TOML config as a dict."""
    path = get_config_toml_path()
    if not path.exists():
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        return tomlkit.load(f)

def save_raw_config(config_dict: dict) -> None:
    """Save raw TOML config to disk."""
    path = get_config_toml_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        tomlkit.dump(config_dict, f)

def get_config() -> AtlasConfig:
    """Load and merge configuration with defaults and environment."""
    load_atlas_secrets()
    raw_toml = load_raw_config()
    
    try:
        config = AtlasConfig.model_validate(raw_toml)
    except ValidationError:
        # If TOML is broken, we return defaults but maybe log a warning?
        config = AtlasConfig()
        
    return config

def update_config_value(dotted_path: str, value: Any) -> None:
    """Update a configuration value using dotted path notation."""
    if is_secret_key(dotted_path):
        # Route to .env.atlas
        # Convert path to uppercase env var name if it's a flat key, 
        # or use the path as is if it's already an env var style.
        env_key = dotted_path.replace(".", "_").upper()
        set_atlas_secret(env_key, str(value))
        return

    # Route to config.toml
    config_dict = load_raw_config()
    parts = dotted_path.split(".")
    
    current = config_dict
    for i, part in enumerate(parts[:-1]):
        if part not in current:
            current[part] = tomlkit.table()
        current = current[part]
        
    current[parts[-1]] = value
    save_raw_config(config_dict)

def delete_config_value(dotted_path: str) -> None:
    """Delete a configuration value."""
    config_dict = load_raw_config()
    parts = dotted_path.split(".")
    
    current = config_dict
    for part in parts[:-1]:
        if part not in current:
            return
        current = current[part]
        
    if parts[-1] in current:
        del current[parts[-1]]
        save_raw_config(config_dict)
