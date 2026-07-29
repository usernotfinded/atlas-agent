# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/paths.py
# PURPOSE: Locates the config files on disk. Every other config module asks this
#          one where to read and write; nothing else hardcodes a config path.
# DEPS:    stdlib only (pathlib)
# ==============================================================================

# --- IMPORTS ---
from pathlib import Path
from typing import Any
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


def get_safety_dir() -> Path:
    """Directory holding `AdvancedKillSwitch` state and its heartbeat.

    One expression, used by both the writer (`atlas kill`) and the reader
    (`BrokerResolver._resolve_can_submit`). They were separate literals, and the
    reader did not exist at all: `atlas kill flatten-all` armed a switch nothing
    on the live-submit path ever looked at.

    The location is unchanged from what `atlas kill` has always written, on
    purpose. Moving it would orphan the state of anyone whose switch is armed
    right now, and an upgrade that silently disarms an emergency stop is worse
    than the split it would tidy up.
    """
    return get_config_dir() / "safety"


def get_safety_dir_for(config: Any) -> Path:
    """`get_safety_dir()` anchored to a loaded config's workspace root.

    Both callers must resolve to the same directory or the switch is armed in
    one place and read in another. Deriving it from `workspace_root` makes that
    structural instead of relying on the caller's cwd happening to match.
    """
    workspace_root = getattr(config, "workspace_root", None)
    if workspace_root is None:
        return get_safety_dir()
    return Path(workspace_root) / ".atlas" / "safety"
