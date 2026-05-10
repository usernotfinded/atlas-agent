import json
import shutil
from pathlib import Path
from datetime import datetime

from atlas_agent.config.paths import get_legacy_config_json_path
from atlas_agent.config.store import set_raw_value
from atlas_agent.config.secrets import is_secret_key, canonical_env_var, set_secret

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
            mapped_key = _map_legacy_key(key)
            if is_secret_key(mapped_key):
                env_var = canonical_env_var(mapped_key)
                set_secret(env_var, str(value))
            else:
                set_raw_value(mapped_key, value)
            
        return True
    except (json.JSONDecodeError, OSError) as e:
        print(f"Migration failed: {e}")
        return False

def _map_legacy_key(key: str) -> str:
    """Map legacy flat keys to new nested structure if needed."""
    mapping = {
        "provider": "model.provider",
        "model": "model.model",
        "messaging": "safety.order_approval_mode",
        "broker_mode": "broker.provider",
        "trust_mode": "trading_mode",
        "enable_live_trading": "broker.enable_live_trading",
        "live_broker": "broker.provider",
        "order_approval_mode": "safety.order_approval_mode",
        "require_order_approval": "safety.require_order_approval",
        "max_daily_loss": "risk.max_daily_loss",
        "max_position_size": "risk.max_position_notional",
        "max_trades_per_day": "risk.max_trades_per_day",
        "max_portfolio_exposure": "risk.max_portfolio_exposure",
        "max_order_notional": "risk.max_order_notional",
        "allow_leverage": "risk.allow_leverage",
        "kill_switch_enabled": "safety.kill_switch_enabled",
        "minimum_confidence": "risk.minimum_confidence",
        "require_stop_loss_live": "risk.require_stop_loss_live",
        "enforce_market_hours": "risk.enforce_market_hours",
        "symbol_allowlist": "risk.symbol_allowlist",
        "symbol_blocklist": "risk.symbol_blocklist",
        "starting_cash": "backtest.initial_cash",
        "default_symbol": "backtest.default_symbol",
        "data_path": "backtest.data_path",
        "audit_dir": "audit.audit_dir",
    }
    return mapping.get(key, key)
