from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.agent.autonomous_paper_kernel import apply_fill, run_kernel_cycle
from atlas_agent.agent.autonomous_paper_metrics import calculate_stateful_paper_metrics
from atlas_agent.agent.autonomous_paper_models import (
    StatefulPaperConfig,
    StatefulPaperCursor,
    StatefulPaperResult,
    StatefulPaperState,
)
from atlas_agent.audit import AuditWriter
from atlas_agent.audit.redaction import redact_payload
from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.execution import ExecutionSimulator
from atlas_agent.backtest.models import BacktestConfig, BacktestOrder
from atlas_agent.backtest.registry import get_strategy
from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager


def _state_path(state_dir: str | Path, run_id: str) -> Path:
    return Path(state_dir) / f"{run_id}-state.json"


def _checkpoint_path(state_dir: str | Path, run_id: str) -> Path:
    return Path(state_dir) / f"{run_id}-checkpoint.json"


def _bar_hash(bar) -> str:
    canonical = json.dumps(bar.model_dump(mode="json"), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _initialize_state(config: StatefulPaperConfig) -> StatefulPaperState:
    now = datetime.now(UTC).isoformat()
    return StatefulPaperState(
        run_id=config.run_id,
        symbol=config.symbol,
        strategy_id=config.strategy_id,
        data_path=config.data_path,
        cash=config.initial_cash,
        positions={},
        cursor=StatefulPaperCursor(),
        fill_history=[],
        decision_refs=[],
        metrics_history=[],
        created_at=now,
        updated_at=now,
        status="active",
        errors=[],
    )


def load_state_or_initialize(
    *,
    state_dir: str | Path,
    run_id: str,
    config: StatefulPaperConfig,
    resume: bool = False,
) -> StatefulPaperState:
    state_path = _state_path(state_dir, run_id)
    if state_path.exists() and resume:
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return StatefulPaperState.model_validate(data)
        except Exception as exc:
            raise ValueError(f"malformed_state: {type(exc).__name__}") from None
    return _initialize_state(config)


def save_state(state: StatefulPaperState, state_dir: str | Path) -> Path:
    state_path = _state_path(state_dir, state.run_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(redact_payload(state.model_dump(mode="json")), indent=2),
        encoding="utf-8",
    )
    return state_path


def save_checkpoint(state: StatefulPaperState, state_dir: str | Path) -> Path:
    checkpoint_path = _checkpoint_path(state_dir, state.run_id)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = redact_payload(state.model_dump(mode="json"))
    checkpoint_path.write_text(
        json.dumps(checkpoint, indent=2),
        encoding="utf-8",
    )
    return checkpoint_path


def _redact_data_source(path: str | Path) -> str:
    return Path(path).name


def _safe_error(_exc: Exception) -> str:
    name = _exc.__class__.__name__
    msg = str(_exc)
    # Preserve our own error categories while redacting paths and details.
    for category in ("malformed_state", "state_mismatch"):
        if msg.startswith(category):
            return f"{category}: error details redacted"
    return f"{name}: error details redacted"


def _kill_switch_enabled(kill_switch: Any) -> bool:
    if kill_switch is None:
        return False
    if callable(getattr(kill_switch, "is_enabled", None)):
        return bool(kill_switch.is_enabled())
    status = None
    if callable(getattr(kill_switch, "status", None)):
        try:
            status = kill_switch.status()
        except Exception:
            status = None
    if status is not None and hasattr(status, "enabled"):
        return bool(status.enabled)
    if callable(getattr(kill_switch, "evaluate", None)):
        try:
            decision = kill_switch.evaluate()
            if hasattr(decision, "allowed"):
                return not bool(decision.allowed)
        except Exception:
            pass
    return False


def _build_result(
    *,
    config: StatefulPaperConfig,
    status: str,
    bars_processed_this_run: int,
    total_bars_processed: int,
    errors: list[str],
    metrics: StatefulPaperMetrics | None = None,
    checkpoint_path: str | None = None,
    audit_log_path: str | Path,
) -> StatefulPaperResult:
    output_dir = Path(config.output_dir)
    state_dir = Path(config.state_dir)
    return StatefulPaperResult(
        run_id=config.run_id,
        status=status,
        bars_processed_this_run=bars_processed_this_run,
        total_bars_processed=total_bars_processed,
        decisions_path=str(output_dir / f"{config.run_id}-decisions.jsonl"),
        fills_path=str(output_dir / f"{config.run_id}-fills.jsonl"),
        metrics_path=str(output_dir / f"{config.run_id}-metrics.json"),
        checkpoint_path=checkpoint_path
        or str(_checkpoint_path(state_dir, config.run_id)),
        manifest_path=str(output_dir / f"{config.run_id}-manifest.json"),
        audit_log_path=str(audit_log_path),
        metrics=metrics,
        errors=errors,
    )


def run_stateful_autonomous_paper(
    *,
    config: StatefulPaperConfig,
    atlas_config: AtlasConfig,
    resume: bool = False,
    max_cycles: int = 0,
    audit_writer: AuditWriter | None = None,
    event_logger: EventLogger | None = None,
    kill_switch: Any | None = None,
) -> StatefulPaperResult:
    """Run a stateful paper loop, resuming from the last processed bar.

    If no new bars are available, returns status="no_new_data" without
    modifying state. Duplicate bars (by index and hash) are skipped.
    """
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir = Path(config.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    audit_log_path = Path(atlas_config.audit_dir) / "events.jsonl"
    if audit_writer is None:
        audit_writer = AuditWriter(audit_log_path)
    if event_logger is None:
        event_logger = EventLogger(atlas_config.events_dir)

    audit_writer.start_run(config.run_id)
    event_logger.write(
        "autonomous_paper_started",
        run_id=config.run_id,
        command="atlas agent autonomous-paper --state-dir",
        mode="paper",
        payload=redact_payload(
            {
                "symbol": config.symbol,
                "strategy_id": config.strategy_id,
                "strategy_parameters": config.strategy_parameters,
                "data_path": config.data_path,
                "max_cycles": max_cycles,
                "fill_timing": config.fill_timing,
            }
        ),
    )

    decisions_path = output_dir / f"{config.run_id}-decisions.jsonl"
    fills_path = output_dir / f"{config.run_id}-fills.jsonl"
    metrics_path = output_dir / f"{config.run_id}-metrics.json"
    manifest_path = output_dir / f"{config.run_id}-manifest.json"

    try:
        state = load_state_or_initialize(
            state_dir=state_dir,
            run_id=config.run_id,
            config=config,
            resume=resume,
        )
    except ValueError as exc:
        error = _safe_error(exc)
        audit_writer.finish_run("failed", final_status_text=error)
        return _build_result(
            config=config,
            status="failed",
            bars_processed_this_run=0,
            total_bars_processed=0,
            errors=[error],
            audit_log_path=audit_log_path,
        )

    if resume and _state_path(state_dir, config.run_id).exists():
        mismatches: list[str] = []
        if state.run_id != config.run_id:
            mismatches.append("run_id")
        if state.symbol != config.symbol:
            mismatches.append("symbol")
        if state.strategy_id != config.strategy_id:
            mismatches.append("strategy_id")
        if state.data_path != config.data_path:
            mismatches.append("data_path")
        if mismatches:
            error = "state_mismatch"
            audit_writer.finish_run("failed", final_status_text=error)
            return _build_result(
                config=config,
                status="failed",
                bars_processed_this_run=0,
                total_bars_processed=state.cursor.last_processed_bar_index + 1,
                errors=[error],
                audit_log_path=audit_log_path,
            )

    try:
        bars = load_market_data(config.data_path, symbol=config.symbol)
    except Exception as exc:
        error = _safe_error(exc)
        audit_writer.finish_run("failed", final_status_text=error)
        return _build_result(
            config=config,
            status="failed",
            bars_processed_this_run=0,
            total_bars_processed=state.cursor.last_processed_bar_index + 1,
            errors=[error],
            audit_log_path=audit_log_path,
        )

    if not bars:
        audit_writer.finish_run("failed", final_status_text="no_bars_loaded")
        return _build_result(
            config=config,
            status="failed",
            bars_processed_this_run=0,
            total_bars_processed=state.cursor.last_processed_bar_index + 1,
            errors=["No bars loaded for symbol."],
            audit_log_path=audit_log_path,
        )

    start_index = state.cursor.last_processed_bar_index + 1
    if start_index >= len(bars):
        checkpoint_path = save_checkpoint(state, state_dir)
        audit_writer.finish_run("completed", final_status_text="no_new_data")
        return _build_result(
            config=config,
            status="no_new_data",
            bars_processed_this_run=0,
            total_bars_processed=state.cursor.last_processed_bar_index + 1,
            errors=[],
            checkpoint_path=str(checkpoint_path),
            audit_log_path=audit_log_path,
        )

    end_index = (
        len(bars) if max_cycles <= 0 else min(start_index + max_cycles, len(bars))
    )
    bars_to_process = bars[start_index:end_index]

    strategy = get_strategy(
        config.strategy_id, parameters=config.strategy_parameters
    )

    runtime_config = BacktestConfig(
        run_id=config.run_id,
        symbol=config.symbol,
        data_path=config.data_path,
        initial_equity=config.initial_cash,
        slippage_bps=config.slippage_bps,
        commission_bps=config.commission_bps,
        strategy_mode=config.strategy_id,
        strategy_parameters=config.strategy_parameters,
        risk_enabled=True,
    )
    executor = ExecutionSimulator(runtime_config)

    risk_limits = RiskLimits(
        max_position_notional=atlas_config.risk.max_position_notional,
        max_single_trade_notional=atlas_config.risk.max_order_notional,
        allowed_symbols=atlas_config.risk.symbol_allowlist,
        blocked_symbols=atlas_config.risk.symbol_blocklist or set(),
        live_trading_enabled=False,
        paper_only=True,
        minimum_confidence=atlas_config.risk.minimum_confidence,
        allow_shorting=atlas_config.risk.allow_leverage,
        require_stop_loss_live=atlas_config.risk.require_stop_loss_live,
    )
    risk_manager = RiskManager(
        limits=risk_limits,
        audit_writer=audit_writer,
        run_id=config.run_id,
        kill_switch_enabled=atlas_config.safety.kill_switch_enabled,
    )

    # Fill timing model:
    # - same_bar: orders generated on bar i are risk-evaluated and filled on bar i.
    # - next_bar: orders generated on bar i are risk-evaluated on bar i, stored as
    #   pending_orders, and filled on bar i+1 using bar i+1 as the fill bar. This
    #   prevents same-bar lookahead because the fill price is not known when the
    #   signal is generated.
    fill_timing = config.fill_timing
    pending_orders: list[BacktestOrder] = list(state.pending_orders)
    bars_processed_this_run = 0
    total_rejections = 0

    with open(decisions_path, "a", encoding="utf-8") as decisions_file, open(
        fills_path, "a", encoding="utf-8"
    ) as fills_file:
        for offset, bar in enumerate(bars_to_process):
            bar_index = start_index + offset

            if _kill_switch_enabled(kill_switch):
                state.errors.append("kill_switch_blocked")
                save_state(state, state_dir)
                save_checkpoint(state, state_dir)
                audit_writer.finish_run(
                    "failed", final_status_text="kill_switch_blocked"
                )
                return _build_result(
                    config=config,
                    status="blocked",
                    bars_processed_this_run=bars_processed_this_run,
                    total_bars_processed=state.cursor.last_processed_bar_index + 1,
                    errors=["kill_switch_blocked"],
                    audit_log_path=audit_log_path,
                )

            bar_hash = _bar_hash(bar)
            if bar_hash in state.cursor.processed_bar_hashes:
                continue

            # 1. Fill any orders queued from the previous bar (next-bar semantics).
            if fill_timing == "next_bar" and pending_orders:
                for order in pending_orders:
                    fill = executor.process_order(order, bar)
                    if fill:
                        state.cash, state.positions = apply_fill(
                            fill=fill,
                            cash=state.cash,
                            positions=state.positions,
                            allow_shorting=risk_manager.limits.allow_shorting,
                        )
                        state.fill_history.append(deepcopy(fill))
                        fills_file.write(
                            json.dumps(redact_payload(fill.model_dump(mode="json")))
                            + "\n"
                        )
                        audit_writer.write_event(
                            "autonomous_paper_fill",
                            run_id=config.run_id,
                            iteration=bar_index,
                            payload=redact_payload(fill.model_dump(mode="json")),
                        )
                pending_orders = []

            # 2. Run decision/risk cycle for the current bar.
            result = run_kernel_cycle(
                bar=bar,
                bar_index=bar_index,
                bars_so_far=bars[: bar_index + 1],
                cash=state.cash,
                positions=state.positions,
                pending_orders=pending_orders,
                strategy=strategy,
                executor=executor,
                risk_manager=risk_manager,
                symbol=config.symbol,
                run_id=config.run_id,
                config=runtime_config,
                audit_writer=audit_writer,
                max_orders_per_cycle=config.max_orders_per_cycle,
                execute_fills=(fill_timing == "same_bar"),
            )

            if fill_timing == "same_bar":
                state.cash = result.cash
                state.positions = deepcopy(result.positions)
                state.fill_history.extend(deepcopy(result.fills))
                state.pending_orders = []
            else:
                # Queue allowed orders to be filled on the next bar.
                pending_orders = list(result.allowed_orders)
                state.pending_orders = list(pending_orders)

            state.cursor.last_processed_bar_index = bar_index
            state.cursor.last_processed_bar_timestamp = bar.timestamp.isoformat()
            state.cursor.processed_bar_hashes.append(bar_hash)
            # Retain the most recent 10,000 bar hashes to bound memory growth
            # while still detecting duplicates across typical daily runs.
            if len(state.cursor.processed_bar_hashes) > 10_000:
                state.cursor.processed_bar_hashes = state.cursor.processed_bar_hashes[
                    -10_000:
                ]

            decision_ref = {
                "bar_index": bar_index,
                "decision_state": result.decision_state,
                "proposed_action": result.proposed_action,
                "fill_count": len(result.fills),
                "rejection_count": len(result.rejected_orders),
                "audit_event_ids": result.audit_event_ids,
            }
            state.decision_refs.append(decision_ref)
            total_rejections += len(result.rejected_orders)

            decisions_file.write(
                json.dumps(redact_payload(decision_ref)) + "\n"
            )

            for fill in result.fills:
                fills_file.write(
                    json.dumps(redact_payload(fill.model_dump(mode="json"))) + "\n"
                )

            bars_processed_this_run += 1

    state.updated_at = datetime.now(UTC).isoformat()
    state.status = "completed"

    last_close = bars[state.cursor.last_processed_bar_index].close
    metrics = calculate_stateful_paper_metrics(
        starting_cash=config.initial_cash,
        cash=state.cash,
        positions=state.positions,
        fill_history=state.fill_history,
        bars_processed=state.cursor.last_processed_bar_index + 1,
        current_price=last_close,
        data_source=config.data_path,
        number_of_rejections=total_rejections,
    )

    metrics_path.write_text(
        json.dumps(
            redact_payload(metrics.model_dump(mode="json")), indent=2
        ),
        encoding="utf-8",
    )

    manifest = {
        "run_id": config.run_id,
        "status": "completed",
        "symbol": config.symbol,
        "strategy_id": config.strategy_id,
        "data_source": _redact_data_source(config.data_path),
        "bars_processed_this_run": bars_processed_this_run,
        "total_bars_processed": state.cursor.last_processed_bar_index + 1,
        "decisions_path": decisions_path.name,
        "fills_path": fills_path.name,
        "metrics_path": metrics_path.name,
        "checkpoint_path": _checkpoint_path(state_dir, config.run_id).name,
        "manifest_path": manifest_path.name,
        "audit_log_path": Path(audit_log_path).name,
        "metrics": metrics.model_dump(mode="json"),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(
        json.dumps(redact_payload(manifest), indent=2),
        encoding="utf-8",
    )

    audit_writer.write_event(
        "autonomous_paper_manifest_sealed",
        run_id=config.run_id,
        payload=redact_payload(manifest),
    )
    audit_writer.finish_run(
        "completed", final_status_text="stateful_autonomous_paper_completed"
    )

    event_logger.write(
        "autonomous_paper_completed",
        run_id=config.run_id,
        command="atlas agent autonomous-paper --state-dir",
        mode="paper",
        payload=redact_payload(manifest),
    )

    checkpoint_path = save_checkpoint(state, state_dir)
    save_state(state, state_dir)

    return _build_result(
        config=config,
        status="completed",
        bars_processed_this_run=bars_processed_this_run,
        total_bars_processed=state.cursor.last_processed_bar_index + 1,
        errors=[],
        metrics=metrics,
        checkpoint_path=str(checkpoint_path),
        audit_log_path=audit_log_path,
    )
