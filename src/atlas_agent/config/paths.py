# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/paths.py
# PURPOSE: Locates the config files on disk. Every other config module asks this
#          one where to read and write; nothing else hardcodes a config path.
# DEPS:    stdlib only (pathlib)
# ==============================================================================

# --- IMPORTS ---
from pathlib import Path
import os


# ==============================================================================
# WORKSPACE DISCOVERY
# ==============================================================================

def get_workspace_root() -> Path:
    """Get the workspace root directory (containing .atlas)."""
    # Walk upwards from the cwd, git-style, so `atlas` works from any subdirectory
    # of a workspace rather than only from its root.
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        candidate = parent / ".atlas"
        try:
            if candidate.is_dir():
                return parent
        except PermissionError:
            # Sandbox/local environments may restrict directory traversal
            continue

    # 2. Fallback to CWD
    return Path.cwd()


# ==============================================================================
# CONFIG FILE PATHS
# ==============================================================================

def get_config_dir() -> Path:
    """Get the configuration directory (.atlas)."""
    root = get_workspace_root()
    dot_atlas = root / ".atlas"
    if dot_atlas.is_dir():
        return dot_atlas

    # No workspace-local .atlas: fall back to the user-global one, which is what
    # makes configless commands (`atlas config`, `atlas init`) work outside a
    # workspace.
    return Path.home() / ".atlas"

def get_config_toml_path() -> Path:
    """Get path to config.toml."""
    return get_config_dir() / "config.toml"

def get_env_atlas_path() -> Path:
    """Get path to .env.atlas in workspace root."""
    # Deliberately the workspace *root*, not .atlas/: secrets live beside the
    # workspace and outside the directory that gets committed and shipped around.
    return get_workspace_root() / ".env.atlas"

def get_legacy_config_json_path() -> Path:
    """Get path to legacy config.json."""
    return get_config_dir() / "config.json"
