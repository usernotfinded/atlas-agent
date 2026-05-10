from pathlib import Path
import os

def get_workspace_root() -> Path:
    """Get the workspace root directory (containing .atlas)."""
    # 1. Check if we are inside a workspace by looking upwards for .atlas
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        candidate = parent / ".atlas"
        if candidate.is_dir():
            return parent
    
    # 2. Fallback to CWD
    return Path.cwd()

def get_config_dir() -> Path:
    """Get the configuration directory (.atlas)."""
    root = get_workspace_root()
    dot_atlas = root / ".atlas"
    if dot_atlas.is_dir():
        return dot_atlas
    
    # Fallback to home directory
    return Path.home() / ".atlas"

def get_config_toml_path() -> Path:
    """Get path to config.toml."""
    return get_config_dir() / "config.toml"

def get_env_atlas_path() -> Path:
    """Get path to .env.atlas in workspace root."""
    return get_workspace_root() / ".env.atlas"

def get_legacy_config_json_path() -> Path:
    """Get path to legacy config.json."""
    return get_config_dir() / "config.json"
