# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/risk.py
# PURPOSE: CLI handler for `atlas risk` — shows the active risk limits and the kill
#          switch state, reconciled with the on-disk runtime flag (so a tripped
#          switch shows as tripped even if the config file says otherwise).
# DEPS:    cli_safety (the reconciliation), risk.limits
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_safety import _effective_config_with_runtime_kill_switch
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager


def handle_risk(context: CLIContext) -> int:
    args = context.args
    config = context.config

    if args.risk_command == "status":
        limits = RiskLimits(
            max_position_notional=config.max_position_size,
            max_single_trade_notional=config.max_order_notional,
            allowed_symbols=config.symbol_allowlist,
            blocked_symbols=config.symbol_blocklist or set(),
            live_trading_enabled=config.enable_live_trading,
        )
        manager = RiskManager(
            limits=limits, kill_switch_enabled=config.kill_switch_enabled
        )
        print("Risk Management Status:")
        print(f"  Live Trading: {'ENABLED' if limits.live_trading_enabled else 'DISABLED'}")
        print(f"  Kill Switch: {'ACTIVE' if manager.kill_switch_enabled else 'Inactive'}")
        print(f"  Max Position Notional: ${limits.max_position_notional}")
        print(f"  Max Order Notional: ${limits.max_single_trade_notional}")
        print(f"  Allowed Symbols: {limits.allowed_symbols if limits.allowed_symbols else 'All'}")
        print(f"  Blocked Symbols: {list(limits.blocked_symbols) if limits.blocked_symbols else 'None'}")
        return 0

    if args.risk_command == "check":
        effective = _effective_config_with_runtime_kill_switch(config)
        print(f"kill_switch={effective.kill_switch_enabled}")
        print(f"max_position_size={config.max_position_size}")
        print(f"max_trades_per_day={config.max_trades_per_day}")
        return 0

    return 0
