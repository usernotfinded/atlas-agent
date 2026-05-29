import os
import tempfile
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Use stdlib tomllib for reading where possible (Python 3.11+)
if sys.version_info >= (3, 11):
    import tomllib
else:
    # Fallback to tomli if on older python, though project says >=3.11
    import tomlkit as tomllib

from atlas_agent.config.paths import get_config_toml_path
from atlas_agent.config.secrets import is_secret_key
from atlas_agent.config.errors import format_toml_syntax_error

def load_raw_config() -> dict:
    """Load raw TOML config as a dict using fast stdlib parser."""
    path = get_config_toml_path()
    if not path.exists():
        return {}
    
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except PermissionError:
        # Sandbox/local environments may restrict access to user-global config
        return {}
    except Exception as exc:
        if exc.__class__.__name__ == "TOMLDecodeError":
            raise format_toml_syntax_error(path, exc) from exc
        raise

def get_raw_config() -> dict:
    """Get the entire raw persisted config dict."""
    return load_raw_config()

def get_raw_value(dotted_path: str, default: Any = None) -> Any:
    """Get a raw value from the persisted config by dotted path."""
    config_dict = load_raw_config()
    parts = dotted_path.split(".")
    
    current = config_dict
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
        
    return current

def _atomic_write_toml(config_dict: dict) -> None:
    """Atomically write tomlkit document to disk."""
    import tomlkit # Lazy import
    path = get_config_toml_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to a temporary file in the same directory, then replace
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix="config.toml.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            tomlkit.dump(config_dict, f)
        os.replace(temp_path, path)
    except Exception:
        os.unlink(temp_path)
        raise

def set_raw_value(dotted_path: str, value: Any) -> None:
    """Set a value in the raw TOML config. Rejects secrets."""
    is_model_update = False
    if dotted_path in ("model.default", "model.model"):
        dotted_path = "model.model"
        is_model_update = True
        
    if is_secret_key(dotted_path):
        raise ValueError(f"Cannot store secret key '{dotted_path}' in raw TOML. Use secrets store.")

    import tomlkit # Lazy import
    
    path = get_config_toml_path()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            doc = tomlkit.load(f)
    else:
        doc = tomlkit.document()

    if is_model_update and "model" in doc and hasattr(doc["model"], "get") and "default" in doc["model"]:
        del doc["model"]["default"]

    parts = dotted_path.split(".")
    
    current = doc
    for i, part in enumerate(parts[:-1]):
        if part not in current:
            current[part] = tomlkit.table()
        elif not hasattr(current[part], "get"):
            # Overwrite non-dict with table if intermediate path
            current[part] = tomlkit.table()
        current = current[part]
        
    current[parts[-1]] = value
    _atomic_write_toml(doc)

def unset_raw_value(dotted_path: str) -> None:
    """Remove a value from the raw TOML config."""
    import tomlkit # Lazy import
    
    path = get_config_toml_path()
    if not path.exists():
        return
        
    with open(path, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
        
    modified = False

    if dotted_path == "model.model":
        if "model" in doc and hasattr(doc["model"], "get"):
            if "default" in doc["model"]:
                del doc["model"]["default"]
                modified = True
            if "model" in doc["model"]:
                del doc["model"]["model"]
                modified = True
    elif dotted_path == "model.default":
        if "model" in doc and hasattr(doc["model"], "get"):
            if "default" in doc["model"]:
                del doc["model"]["default"]
                modified = True
    else:
        parts = dotted_path.split(".")
        current = doc
        found = True
        for part in parts[:-1]:
            if not hasattr(current, "get") or part not in current:
                found = False
                break
            current = current[part]
            
        if found and hasattr(current, "get") and parts[-1] in current:
            del current[parts[-1]]
            modified = True
        
    if modified:
        _atomic_write_toml(doc)
