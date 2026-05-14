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
from atlas_agent.ai.discipline import (
    DisciplineNotConfiguredError,
    InvalidDisciplineProfileError,
    require_user_discipline,
)
from atlas_agent.ai.prompt_builder import build_agent_system_prompt
from atlas_agent.core.types import Session
from atlas_agent.providers.factory import get_provider_from_runtime_config
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.builtin import BUILTIN_TOOLS


def _check_discipline_gate(config: AtlasConfig) -> None:
    """Raise if user discipline is missing or invalid."""
    workspace = config.memory_dir.parent
    require_user_discipline(workspace)


def run_agent(
    mode: str, 
    config: AtlasConfig, 
    continuous: bool = False,
    interval: int = 60,
    max_cycles: int | None = None,
    use_loop: bool = True,
    symbol: str | None = None,
) -> RoutineResult | AgentResult | None:
    if use_loop:
        return _run_agent_loop_continuous(
            mode=mode,
            config=config,
            continuous=continuous,
            interval=interval,
            max_cycles=max_cycles,
            symbol=symbol,
        )
    
    cycles = 0
    last_result = None
    ...

def _run_agent_loop_continuous(
    mode: str,
    config: AtlasConfig,
    continuous: bool = False,
    interval: int = 60,
    max_cycles: int | None = None,
    symbol: str | None = None,
) -> AgentResult | None:
    cycles = 0
    last_result = None
    
    try:
        while True:
            last_result = _run_agent_loop_cycle(mode, config, symbol=symbol)
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


def _run_agent_loop_cycle(mode: str, config: AtlasConfig, symbol: str | None = None) -> AgentResult:
    from atlas_agent.audit import AuditWriter
    from atlas_agent.risk.manager import RiskManager
    from atlas_agent.portfolio.state import PortfolioState
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch
    from atlas_agent.brokers.sync import BrokerSyncService
    from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter

    # Discipline gate: agentic loops require an explicit user discipline profile.
    try:
        _check_discipline_gate(config)
        system_prompt = build_agent_system_prompt(config.memory_dir.parent)
    except (DisciplineNotConfiguredError, InvalidDisciplineProfileError) as exc:
        return AgentResult(
            status="error",
            errors=[str(exc)],
            diagnostics={"discipline_gate": "blocked"},
        )

    effective_symbol = symbol or config.market.symbol or config.backtest.default_symbol
    if not effective_symbol:
        return AgentResult(
            status="error",
            errors=["No trading symbol configured. Set one with `atlas config set market.symbol <SYMBOL>` or pass `--symbol <SYMBOL>`."],
        )

    provider = get_provider_from_runtime_config(config)
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
    from atlas_agent.brokers.resolver import BrokerResolver

    effective_mode = mode
    if effective_mode == "auto":
        effective_mode = "live" if (config.trading_mode == "live" and config.enable_live_trading) else "paper"

    resolver = BrokerResolver(config)

    if effective_mode == "live":
        if not config.enable_live_trading:
            return AgentResult(
                status="error",
                errors=["Live trading is not enabled. Set enable_live_trading=true to use live analysis mode."],
                diagnostics={"broker_status": resolver.resolve_status("live").to_dict()},
            )
        status = resolver.resolve_status("live")
        if not status.can_sync:
            return AgentResult(
                status="error",
                errors=[status.message],
                diagnostics={"broker_status": status.to_dict()},
            )
        # Proceed to sync below

    resolution = resolver.resolve_sync_provider(effective_mode)

    if resolution.sync_provider is None:
        return AgentResult(
            status="error",
            errors=[resolution.status.message],
            diagnostics={"broker_status": resolution.status.to_dict()},
        )

    sync_service = BrokerSyncService(
        broker=resolution.sync_provider,
        audit_writer=audit_writer,
        run_id=run_id
    )

    sync_result = sync_service.sync()

    # Live mode: critical sync fields are required
    sync_warnings: list[dict[str, str]] = []
    if effective_mode == "live":
        broker_errors = sync_result.diagnostics.get("broker_errors", [])
        if not isinstance(broker_errors, list):
            return AgentResult(
                status="error",
                errors=["live broker sync failed: malformed diagnostics"],
                diagnostics={
                    "broker_status": resolution.status.to_dict(),
                    "sync_status": sync_result.status,
                    "failed_operations": ["malformed_broker_errors"],
                },
            )
        # Validate every item is a well-formed error dict with required string fields
        required_fields = {"code", "operation", "broker", "message"}
        for entry in broker_errors:
            if not isinstance(entry, dict):
                return AgentResult(
                    status="error",
                    errors=["live broker sync failed: malformed diagnostics"],
                    diagnostics={
                        "broker_status": resolution.status.to_dict(),
                        "sync_status": sync_result.status,
                        "failed_operations": ["malformed_broker_errors"],
                    },
                )
            missing_fields = required_fields - set(entry.keys())
            if missing_fields:
                return AgentResult(
                    status="error",
                    errors=["live broker sync failed: malformed diagnostics"],
                    diagnostics={
                        "broker_status": resolution.status.to_dict(),
                        "sync_status": sync_result.status,
                        "failed_operations": ["malformed_broker_errors"],
                    },
                )
            if not all(isinstance(entry.get(f), str) for f in required_fields):
                return AgentResult(
                    status="error",
                    errors=["live broker sync failed: malformed diagnostics"],
                    diagnostics={
                        "broker_status": resolution.status.to_dict(),
                        "sync_status": sync_result.status,
                        "failed_operations": ["malformed_broker_errors"],
                    },
                )
        failed_ops = {
            e.get("operation")
            for e in broker_errors
        }
        critical_ops = {"sync_account_state", "sync_positions", "sync_open_orders"}
        if sync_result.account is None:
            failed_ops.add("sync_account_state")
        if failed_ops & critical_ops:
            missing = sorted(failed_ops & critical_ops)
            return AgentResult(
                status="error",
                errors=[f"live broker sync failed: {', '.join(missing)}"],
                diagnostics={
                    "broker_status": resolution.status.to_dict(),
                    "sync_status": sync_result.status,
                    "failed_operations": missing,
                },
            )
        # Collect noncritical warnings (e.g., balances-only failure)
        noncritical_ops = sorted(failed_ops - critical_ops)
        for op in noncritical_ops:
            entry = next((e for e in broker_errors if e.get("operation") == op), {})
            sync_warnings.append({
                "operation": op,
                "code": entry.get("code", "unknown"),
                "broker": entry.get("broker", "unknown"),
            })

    portfolio_snapshot = sync_service.get_portfolio_snapshot(
        sync_result, broker_id=resolution.status.broker_id
    )
    
    from atlas_agent.risk.limits import RiskLimits
    risk_limits = RiskLimits(
        max_position_notional=config.max_position_size,
        max_single_trade_notional=config.max_order_notional,
        allowed_symbols=config.symbol_allowlist,
        blocked_symbols=config.symbol_blocklist or set(),
        live_trading_enabled=config.enable_live_trading,
        paper_only=not config.enable_live_trading,
        require_stop_loss_live=config.require_stop_loss_live,
    )
    
    risk_manager = RiskManager(limits=risk_limits, audit_writer=audit_writer, run_id=run_id)
    
    guardrails = DefaultGuardrailChain(registry)
    loop = AgentLoop(
        provider, 
        registry, 
        guardrails, 
        audit_writer=audit_writer, 
        risk_manager=risk_manager,
        kill_switch=kill_switch,
        log_raw_prompts=config.audit.log_raw_prompts,
        log_provider_text=config.audit.log_provider_text
    )
    
    session = Session(id=run_id, turn_count=0, has_summarized=False)
    
    # Simple objective for now
    objective = f"Current mode is {effective_mode}. Analyze the market for {effective_symbol} and propose any necessary actions."
    
    result = loop.run(
        user_objective=objective,
        session=session,
        system_prompt=system_prompt,
        mode=effective_mode,
        run_id=run_id,
        portfolio_snapshot=portfolio_snapshot
    )

    # Surface noncritical sync warnings in final diagnostics for live mode
    if effective_mode == "live" and sync_warnings:
        diagnostics = dict(result.diagnostics or {})
        diagnostics["sync_status"] = sync_result.status
        diagnostics["sync_warnings"] = sync_warnings
        diagnostics["noncritical_failed_operations"] = [w["operation"] for w in sync_warnings]
        diagnostics["broker_status"] = resolution.status.to_dict()
        import dataclasses
        result = dataclasses.replace(result, diagnostics=diagnostics)

    import dataclasses
    return dataclasses.replace(result, mode=effective_mode)


def _run_cycle(mode: str, config: AtlasConfig, symbol: str | None = None) -> RoutineResult:
    _check_discipline_gate(config)
    effective_symbol = symbol or config.market.symbol or config.backtest.default_symbol
    if not effective_symbol:
        return RoutineResult(
            name="agent_cycle",
            mode=mode,
            status="error",
            report_path=None,
            errors=["No trading symbol configured. Set one with `atlas config set market.symbol <SYMBOL>` or pass `--symbol <SYMBOL>`."],
        )
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
                    symbol=effective_symbol,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                    symbol=effective_symbol,
                )
        elif mode == "paper":
            if state == "open":
                result = _run_open_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                    symbol=effective_symbol,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                    symbol=effective_symbol,
                )
        elif mode == "live":
            if state == "open":
                result = _run_open_with_events(
                    config=config,
                    mode="live",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                    symbol=effective_symbol,
                )
            else:
                result = _run_closed_with_events(
                    config=config,
                    mode="paper",
                    event_logger=event_logger,
                    run_id=run_id,
                    command=command,
                    symbol=effective_symbol,
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
    symbol: str | None = None,
) -> RoutineResult:
    try:
        return run_open_market_cycle(
            config,
            mode=mode,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
            symbol=symbol,
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
    symbol: str | None = None,
) -> RoutineResult:
    try:
        return run_closed_market_cycle(
            config,
            mode=mode,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
            symbol=symbol,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return run_closed_market_cycle(config, mode=mode)
