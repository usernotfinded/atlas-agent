from __future__ import annotations

import time

from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.agent.closed_market_cycle import run_closed_market_cycle
from atlas_agent.agent.open_market_cycle import run_open_market_cycle
from atlas_agent.routines.engine import RoutineResult


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
    event_logger = EventLogger(config.events_dir)
    run_id = generate_run_id()
    command = "atlas agent run"
    event_logger.write(
        "agent_started",
        run_id=run_id,
        command=command,
        mode=mode,
        payload={"requested_mode": mode},
    )
    event_logger.write(
        "market_state_detected",
        run_id=run_id,
        command=command,
        mode=mode,
        payload={"state": state},
    )
    try:
        if mode == "auto":
            if state == "open":
                run_mode = "live" if (config.trading_mode == "live" and config.enable_live_trading) else "paper"
                result = _run_open_with_events(
                    config=config,
                    mode=run_mode,
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
        elif mode == "paper":
            if state == "open":
                result = _run_open_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
        elif mode == "live":
            if state == "open":
                result = _run_open_with_events(
                    config=config,
                    mode="live",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                )
        else:
            raise ValueError(f"Unknown agent mode: {mode}")
        event_logger.write(
            "agent_completed",
            run_id=run_id,
            command=command,
            mode=result.mode,
            payload={
                "status": result.status,
                "report_path": str(result.report_path),
                "order_status": result.order_status,
            },
        )
        return result
    except Exception as exc:
        event_logger.write(
            "agent_failed",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"error": str(exc)},
        )
        raise


def _run_open_with_events(
    *,
    config: AtlasConfig,
    mode: str,
    event_logger: EventLogger,
    run_id: str,
    command: str,
) -> RoutineResult:
    try:
        return run_open_market_cycle(
            config,
            mode=mode,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return run_open_market_cycle(config, mode=mode)


def _run_closed_with_events(
    *,
    config: AtlasConfig,
    mode: str,
    event_logger: EventLogger,
    run_id: str,
    command: str,
) -> RoutineResult:
    try:
        return run_closed_market_cycle(
            config,
            mode=mode,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return run_closed_market_cycle(config, mode=mode)
