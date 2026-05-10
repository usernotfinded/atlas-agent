import json
import shutil
from pathlib import Path
from datetime import datetime

from atlas_agent.config.paths import get_legacy_config_json_path, get_config_toml_path
from atlas_agent.config.store import update_config_value
from atlas_agent.config.secrets import is_secret_key

def migrate_legacy_config() -> bool:
    """Migrate legacy config.json to TOML and .env.atlas."""
    json_path = get_legacy_config_json_path()
    if not json_path.exists():
        return False
        
    # Backup
    backup_path = json_path.with_suffix(f".json.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(json_path, backup_path)
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            legacy_data = json.load(f)
            
        for key, value in legacy_data.items():
            # Basic mapping logic: 
            # If key matches a Pydantic field, use it.
            # If it's a secret, it will be routed to .env.atlas automatically by update_config_value.
            
            # Legacy keys might need mapping to nested structure
            mapped_key = _map_legacy_key(key)
            update_config_value(mapped_key, value)
            
        return True
    except (json.JSONDecodeError, OSError) as e:
        print(f"Migration failed: {e}")
        return False

def _map_legacy_key(key: str) -> str:
    """Map legacy flat keys to new nested structure if needed."""
    mapping = {
        "provider": "model.provider",
        "model": "model.model",
        "messaging": "safety.order_approval_mode", # approximate
        "broker_mode": "broker.provider",
        "trust_mode": "trading_mode",
    }
    return mapping.get(key, key)
