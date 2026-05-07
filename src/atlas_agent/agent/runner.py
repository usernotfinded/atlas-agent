from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.agent.open_market_cycle import run_open_market_cycle
from atlas_agent.agent.closed_market_cycle import run_closed_market_cycle
from atlas_agent.routines.engine import RoutineResult


import time
import sys


def run_agent(
    mode: str, 
    config: AtlasConfig, 
    continuous: bool = False,
    interval: int = 60,
    max_cycles: int | None = None
) -> RoutineResult | None:
    cycles = 0
    last_result = None
    
    try:
        while True:
            last_result = _run_cycle(mode, config)
            cycles += 1
            
            if not continuous:
                break
            
            if max_cycles is not None and cycles >= max_cycles:
                print(f"Reached max cycles ({max_cycles}). Exiting.")
                break
                
            print(f"Cycle {cycles} complete. Sleeping for {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nAgent stopped by user. Graceful shutdown complete.")
        
    return last_result


def _run_cycle(mode: str, config: AtlasConfig) -> RoutineResult:
    detector = MarketSessionDetector()
    state = detector.get_state()
    
    if mode == "auto":
        # Determine mode based on state
        if state == "open":
            run_mode = "live" if (config.trading_mode == "live" and config.enable_live_trading) else "paper"
            return run_open_market_cycle(config, mode=run_mode)
        else:
            return run_closed_market_cycle(config, mode="paper")
            
    elif mode == "paper":
        if state == "open":
            return run_open_market_cycle(config, mode="paper")
        else:
            return run_closed_market_cycle(config, mode="paper")
            
    elif mode == "live":
        if state == "open":
            return run_open_market_cycle(config, mode="live")
        else:
            # Live mode requested but market closed. DO NOT place real live orders.
            # We run closed market cycle which forces paper.
            return run_closed_market_cycle(config, mode="paper")
    
    raise ValueError(f"Unknown agent mode: {mode}")
