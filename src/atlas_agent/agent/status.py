# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/status.py
# PURPOSE: Renders "what is the agent doing right now?" — mode, market state, kill
#          switch. Read-only: asking for status never changes anything.
# DEPS:    config, market.session, risk.kill_switch
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import datetime
from typing import Any

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.risk.kill_switch import KillSwitch


# ==============================================================================
# STATUS
# ==============================================================================

def get_agent_status(config: AtlasConfig) -> str:
    payload = get_agent_status_payload(config)
    lines = [
        "Atlas Agent Status",
        f"Time: {payload['time']}",
        f"Market Calendar: {payload['market_calendar']}",
        f"Market State: {payload['market_state']}",
        f"Trading Mode: {payload['trading_mode']}",
        f"Live Enabled: {'yes' if payload['live_enabled'] else 'no'}",
        f"Kill Switch: {payload['kill_switch']}",
        f"Configured Broker: {payload['configured_broker']}",
        f"Pending Orders: {payload['pending_orders']}",
    ]
    return "\n".join(lines)


def get_agent_status_payload(config: AtlasConfig) -> dict[str, Any]:
    detector = MarketSessionDetector()
    now = datetime.datetime.now(datetime.timezone.utc)
    state = detector.get_state(now)
    
    kill_switch = KillSwitch(config.memory_dir / "kill_switch.enabled")
    pending_count = len(list(config.pending_orders_dir.glob("*.json")))
    return {
        "time": now.replace(microsecond=0).isoformat(),
        "market_calendar": detector.config.timezone,
        "market_state": state,
        "trading_mode": config.trading_mode,
        "live_enabled": config.enable_live_trading,
        "kill_switch": "enabled" if kill_switch.is_enabled() else "disabled",
        "configured_broker": config.live_broker if config.trading_mode == "live" else "paper",
        "pending_orders": pending_count,
    }
