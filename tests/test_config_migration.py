# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_config_migration.py
# PURPOSE: Verifies config migration behavior and regression expectations.
# DEPS:    json, pytest, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
import pytest
from pathlib import Path
from atlas_agent.config.migrate import migrate_legacy_config
from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path, get_legacy_config_json_path
from atlas_agent.config import get_config

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

def test_migration_from_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Create legacy config
    dot_atlas = tmp_path / ".atlas"
    dot_atlas.mkdir()
    legacy_json = dot_atlas / "config.json"
    legacy_json.write_text(json.dumps({
        "provider": "anthropic",
        "model": "claude-3",
        "OPENROUTER_API_KEY": "sk-test",
        "trust_mode": "live"
    }))
    
    # Run migration
    assert migrate_legacy_config() == True
    
    # Check TOML
    config = get_config()
    assert config.model.provider == "anthropic"
    assert config.model.model == "claude-3"
    assert config.trading_mode == "live"
    
    # Check secrets
    env_atlas = get_env_atlas_path()
    assert env_atlas.exists()
    content = env_atlas.read_text()
    assert "OPENROUTER_API_KEY=" in content
    assert "sk-test" in content
    
    # Original should still exist (it's a backup)
    assert legacy_json.exists()


def test_migration_never_writes_a_notification_channel_into_the_approval_mode(
    tmp_path, monkeypatch
):
    """`messaging` is a notification channel, not an order-approval policy.

    It used to map to `safety.order_approval_mode`, so a workspace carrying
    `messaging = "telegram"` migrated to `order_approval_mode = "telegram"` — a
    value no code path accepts. `OrderRouter` allowlists exactly `manual_live` on
    the live path and rejects anything else, so the corruption failed closed
    rather than open; what it cost was a working approval mode, replaced by a
    confusing "unsupported live approval mode" rejection with nothing pointing at
    the migration.
    """
    import json

    from atlas_agent.config import get_config
    from atlas_agent.config.migrate import migrate_legacy_config

    monkeypatch.chdir(tmp_path)
    dot_atlas = tmp_path / ".atlas"
    dot_atlas.mkdir()
    (dot_atlas / "config.json").write_text(
        json.dumps({"messaging": "telegram", "provider": "anthropic"})
    )

    assert migrate_legacy_config() is True

    config = get_config()
    assert config.safety.order_approval_mode in {
        "auto_paper",
        "manual_live",
        "disabled_live",
    }, (
        f"migration set order_approval_mode to "
        f"{config.safety.order_approval_mode!r}, which is not an approval mode. A "
        "legacy key was written into a typed safety field."
    )
    # The migration that does belong still happens.
    assert config.model.provider == "anthropic"


def test_no_two_legacy_keys_target_the_same_setting(tmp_path):
    """Two sources for one field means whichever arrives last silently wins."""
    from atlas_agent.config.migrate import _map_legacy_key

    legacy_keys = [
        "provider", "model", "broker_mode", "trust_mode", "enable_live_trading",
        "live_broker", "order_approval_mode", "require_order_approval",
        "max_daily_loss", "max_position_size", "max_trades_per_day",
        "max_portfolio_exposure", "max_order_notional", "allow_leverage",
        "kill_switch_enabled", "minimum_confidence", "require_stop_loss_live",
        "enforce_market_hours", "symbol_allowlist", "symbol_blocklist",
        "starting_cash", "default_symbol", "data_path", "audit_dir", "messaging",
    ]
    targets: dict[str, list[str]] = {}
    for key in legacy_keys:
        targets.setdefault(_map_legacy_key(key), []).append(key)

    collisions = {
        target: sources for target, sources in targets.items() if len(sources) > 1
    }
    # `live_broker` and `broker_mode` are the same setting under two old names, so
    # they legitimately share a destination; nothing else may.
    collisions.pop("broker.provider", None)

    assert collisions == {}, (
        f"these legacy keys write to the same setting: {collisions}. Whichever the "
        "legacy file lists last wins, silently."
    )
