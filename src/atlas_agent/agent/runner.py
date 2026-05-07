from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.agent.open_market_cycle import run_open_market_cycle
from atlas_agent.agent.closed_market_cycle import run_closed_market_cycle
from atlas_agent.routines.engine import RoutineResult


def run_agent(mode: str, config: AtlasConfig) -> RoutineResult:
    detector = MarketSessionDetector()
    state = detector.get_state()
    
    if mode == "auto":
        # Determine mode based on state
        if state == "open":
            # auto defaults to whatever TRADING_MODE is configured to, but we can respect config.trading_mode
            # or force paper if live is not enabled. 
            # Actually, "auto" should run live if TRADING_MODE=live and ENABLE_LIVE_TRADING=true, else paper.
            run_mode = "live" if (config.trading_mode == "live" and config.enable_live_trading) else "paper"
            return run_open_market_cycle(config, mode=run_mode)
        elif state in ("closed", "premarket", "afterhours", "weekend", "holiday"):
            return run_closed_market_cycle(config, mode="paper")
        else:
            # Unknown state -> safe paper
            return run_closed_market_cycle(config, mode="paper")
            
    elif mode == "paper":
        if state == "open":
            return run_open_market_cycle(config, mode="paper")
        else:
            return run_closed_market_cycle(config, mode="paper")
            
    elif mode == "live":
        if state == "open":
            if not config.enable_live_trading:
                # Fails safely. We can still run the cycle in live mode to hit the gates and generate pending orders
                return run_open_market_cycle(config, mode="live")
            return run_open_market_cycle(config, mode="live")
        else:
            # Live mode requested but market closed. DO NOT place real live orders.
            # We run closed market cycle which forces paper.
            return run_closed_market_cycle(config, mode="paper")
    
    raise ValueError(f"Unknown agent mode: {mode}")
