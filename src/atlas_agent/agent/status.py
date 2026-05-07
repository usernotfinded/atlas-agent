from __future__ import annotations

import datetime

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.risk.kill_switch import KillSwitch


def get_agent_status(config: AtlasConfig) -> str:
    detector = MarketSessionDetector()
    now = datetime.datetime.now(datetime.timezone.utc)
    state = detector.get_state(now)
    
    kill_switch = KillSwitch(config.memory_dir / "kill_switch.enabled")
    pending_count = len(list(config.pending_orders_dir.glob("*.json")))
    
    lines = [
        "Atlas Agent Status",
        f"Time: {now.isoformat()}",
        f"Market Calendar: {detector.config.timezone}",
        f"Market State: {state}",
        f"Trading Mode: {config.trading_mode}",
        f"Live Enabled: {'yes' if config.enable_live_trading else 'no'}",
        f"Kill Switch: {'enabled' if kill_switch.is_enabled() else 'disabled'}",
        f"Configured Broker: {config.live_broker if config.trading_mode == 'live' else 'paper'}",
        f"Pending Orders: {pending_count}"
    ]
    return "\n".join(lines)
