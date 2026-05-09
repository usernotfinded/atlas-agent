from __future__ import annotations

import time
from pathlib import Path

from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.agent.closed_market_cycle import run_closed_market_cycle
from atlas_agent.agent.open_market_cycle import run_open_market_cycle
from atlas_agent.routines.engine import RoutineResult


from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.agent.result import AgentResult
from atlas_agent.core.types import Session
from atlas_agent.providers.factory import get_provider_from_env
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.builtin import BUILTIN_TOOLS


def run_agent(
    mode: str, 
    config: AtlasConfig, 
    continuous: bool = False,
    interval: int = 60,
    max_cycles: int | None = None,
    use_loop: bool = True,
) -> RoutineResult | AgentResult | None:
    if use_loop:
        return _run_agent_loop_continuous(
            mode=mode,
            config=config,
            continuous=continuous,
            interval=interval,
            max_cycles=max_cycles
        )
    
    cycles = 0
    last_result = None
    ...

def _run_agent_loop_continuous(
    mode: str,
    config: AtlasConfig,
    continuous: bool = False,
    interval: int = 60,
    max_cycles: int | None = None
) -> AgentResult | None:
    cycles = 0
    last_result = None
    
    try:
        while True:
            last_result = _run_agent_loop_cycle(mode, config)
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


def _run_agent_loop_cycle(mode: str, config: AtlasConfig) -> AgentResult:
    from atlas_agent.audit import AuditWriter
    from atlas_agent.risk.manager import RiskManager
    from atlas_agent.portfolio.state import PortfolioState
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch
    from atlas_agent.brokers.sync import BrokerSyncService
    from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
    
    provider = get_provider_from_env()
    registry = ToolRegistry()
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
    
    audit_path = config.audit_dir / "events.jsonl"
    audit_writer = AuditWriter(audit_path)
    
    run_id = f"run_{int(time.time())}"

    # Advanced Kill Switch
    safety_dir = Path(".atlas/safety")
    kill_switch = AdvancedKillSwitch(
        state_path=safety_dir / "kill_switch.json",
        heartbeat_path=safety_dir / "heartbeat.json",
        audit_writer=audit_writer,
        run_id=run_id
    )
    # Record a fresh heartbeat at start of cycle
    kill_switch.heartbeat_manager.record(source="agent_runner")
    
    # Broker Sync
    # For now, default to PaperBroker in all modes if no real adapter is configured
    # In V4, we'll add Alpaca/Binance adapter factories here.
    paper_broker = PaperBroker(state=PortfolioState(cash=config.starting_cash))
    broker_provider = PaperBrokerAdapter(broker=paper_broker)
    
    sync_service = BrokerSyncService(
        broker=broker_provider,
        audit_writer=audit_writer,
        run_id=run_id
    )
    
    sync_result = sync_service.sync()
    if sync_result.status == "failed" and mode == "live":
        return AgentResult(
            status="error",
            errors=["Broker sync failed in live mode; failing closed."],
            diagnostics={"sync_errors": sync_result.errors}
        )
        
    portfolio_snapshot = sync_service.get_portfolio_snapshot(sync_result)
    
    from atlas_agent.risk.limits import RiskLimits
    risk_limits = RiskLimits(
        max_position_notional=config.max_position_size,
        max_single_trade_notional=config.max_order_notional,
        allowed_symbols=config.symbol_allowlist,
        blocked_symbols=config.symbol_blocklist or set(),
        live_trading_enabled=config.enable_live_trading
    )
    
    risk_manager = RiskManager(limits=risk_limits, audit_writer=audit_writer, run_id=run_id)
    
    guardrails = DefaultGuardrailChain(registry)
    loop = AgentLoop(
        provider, 
        registry, 
        guardrails, 
        audit_writer=audit_writer, 
        risk_manager=risk_manager,
        kill_switch=kill_switch
    )
    
    session = Session(id=run_id, turn_count=0, has_summarized=False)
    
    from atlas_agent.ai.prompt_builder import SYSTEM_PROMPT
    
    # Simple objective for now
    objective = f"Current mode is {mode}. Analyze the market for {config.default_symbol} and propose any necessary actions."
    
    result = loop.run(
        user_objective=objective,
        session=session,
        system_prompt=SYSTEM_PROMPT,
        mode=mode,
        run_id=run_id,
        portfolio_snapshot=portfolio_snapshot
    )
    
    import dataclasses
    return dataclasses.replace(result, mode=mode)


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
