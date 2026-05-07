from __future__ import annotations

import datetime

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector


def get_agent_plan(config: AtlasConfig) -> str:
    detector = MarketSessionDetector()
    state = detector.get_state()
    mode = config.trading_mode
    
    lines = [
        "Atlas Agent Plan",
        f"Detected Market State: {state}",
        f"Requested Mode: {mode}",
        ""
    ]
    
    if state == "open":
        if mode == "live" and not config.enable_live_trading:
            lines.append("Plan: Live mode requested but ENABLE_LIVE_TRADING is false. Fails safely. Pending/rejected flow.")
        elif mode == "live":
            lines.append("Plan: Market open. Trade cycle (Live execution with risk manager and approval gates).")
        else:
            lines.append("Plan: Market open. Trade cycle (Paper execution).")
    elif state in ("closed", "premarket", "afterhours", "weekend", "holiday"):
        lines.append("Plan: Market closed. Research/planning/paper simulation cycle. No live broker orders will be placed.")
    else:
        lines.append("Plan: Unknown market state. Defaulting to paper/research only.")
        
    return "\n".join(lines)
