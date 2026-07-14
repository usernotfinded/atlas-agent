# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/migrate.py
# PURPOSE: One-shot migration of the legacy flat config.json into the current
#          split world: non-secrets to config.toml, secrets to .env.atlas.
# DEPS:    config.store (TOML sink), config.secrets (secret sink + classifier)
# ==============================================================================

# --- IMPORTS ---
import json
import shutil
from pathlib import Path
from datetime import datetime

from atlas_agent.config.paths import get_legacy_config_json_path
from atlas_agent.config.store import set_raw_value
from atlas_agent.config.secrets import is_secret_key, canonical_env_var, set_secret


# ==============================================================================
# MIGRATION ENTRY POINT
# ==============================================================================

def migrate_legacy_config() -> bool:
    """Migrate legacy config.json to TOML and .env.atlas."""
    json_path = get_legacy_config_json_path()
    if not json_path.exists():
        return False

    # Timestamped backup before touching anything: the legacy file is the user's only
    # copy of settings that may include API keys, and this migration fans them out
    # across two destinations with no way back.
    backup_path = json_path.with_suffix(f".json.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(json_path, backup_path)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            legacy_data = json.load(f)

        # The classifier decides the destination per key: anything secret-shaped is
        # routed to .env.atlas (0600), everything else to config.toml. Getting this
        # split wrong in either direction is what the whole module exists to prevent.
        for key, value in legacy_data.items():
            mapped_key = _map_legacy_key(key)
            if is_secret_key(mapped_key):
                env_var = canonical_env_var(mapped_key)
                set_secret(env_var, str(value))
            else:
                set_raw_value(mapped_key, value)

        return True
    except (json.JSONDecodeError, OSError) as e:
        # `e` is safe to print here: it is a parse/IO error over a path, not a value.
        print(f"Migration failed: {e}")
        return False


# --- Legacy key mapping ---

def _map_legacy_key(key: str) -> str:
    """Map legacy flat keys to new nested structure if needed."""
    # Flat legacy name → dotted path in the new schema. Unmapped keys pass through
    # unchanged and land at the top level, where schema validation will reject them
    # if they are not real settings.
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
