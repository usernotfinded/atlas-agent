from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from atlas_agent.audit import AuditWriter
from atlas_agent.audit.redaction import redact_payload
from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.execution import ExecutionSimulator
from atlas_agent.backtest.models import (
    BacktestConfig as BacktestRuntimeConfig,
    BacktestFill,
    BacktestOrder,
    BacktestPosition,
    MarketBar,
)
from atlas_agent.backtest.registry import get_strategy
from atlas_agent.backtest.strategy import StrategyContext
from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PendingOrder, PortfolioSnapshot, RiskPosition


class AutonomousDecision(BaseModel):
    """A single deterministic autonomous paper decision."""

    run_id: str
    iteration: int
    timestamp: str
    symbol: str
    mode: Literal["paper"] = "paper"
    data_source: str
    strategy_id: str
    observations: dict[str, Any] = Field(default_factory=dict)
    proposed_action: Literal["buy", "sell", "hold"]
    proposed_order: dict[str, Any] | None = None
    risk_result: dict[str, Any] = Field(default_factory=dict)
    decision_state: Literal["no_trade", "risk_blocked", "paper_executed"]
    blocked_reason: str | None = None
    audit_event_ids: list[str] = Field(default_factory=list)
    manifest_path: str | None = None


class AutonomousPaperResult(BaseModel):
    """Summary result of an autonomous paper decision loop run."""

    run_id: str
    status: Literal["completed", "failed", "blocked"]
    mode: Literal["paper"] = "paper"
    symbol: str
    strategy_id: str
    bars_processed: int
    decisions: int
    trades_executed: int
    trades_blocked: int
    no_trade_count: int
    decisions_path: str
    manifest_path: str
    audit_log_path: str
    errors: list[str] = Field(default_factory=list)


def _build_portfolio_snapshot(
    *,
    cash: float,
    positions: dict[str, BacktestPosition],
    pending_orders: list[BacktestOrder],
    current_price: float,
) -> PortfolioSnapshot:
    risk_positions: list[RiskPosition] = []
    total_exposure = 0.0
    for pos in positions.values():
        notional = abs(pos.quantity * current_price)
        side: Literal["long", "short", "flat"] = (
            "long" if pos.quantity > 0 else "short" if pos.quantity < 0 else "flat"
        )
        risk_positions.append(
            RiskPosition(
                symbol=pos.symbol,
                quantity=pos.quantity,
                average_price=pos.average_entry_price,
                market_price=current_price,
                notional=notional,
                side=side,
            )
        )
        total_exposure += notional

    open_orders: list[PendingOrder] = []
    for o in pending_orders:
        open_orders.append(
            PendingOrder(
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                quantity=o.quantity,
                limit_price=o.price if o.type == "limit" else None,
                estimated_price=o.price if o.type == "market" else None,
                status="pending",
                filled_quantity=0.0,
            )
        )

    equity = cash + sum(pos.quantity * current_price for pos in positions.values())
    return PortfolioSnapshot(
        cash=cash,
        equity=equity,
        total_exposure=total_exposure,
        positions=risk_positions,
        open_orders=open_orders,
    )


def _apply_fill(
    *,
    fill: BacktestFill,
    cash: float,
    positions: dict[str, BacktestPosition],
) -> tuple[float, dict[str, BacktestPosition]]:
    """Return updated cash and positions after applying a paper fill."""
    cash = float(cash)
    positions = deepcopy(positions)
    if fill.side == "buy":
        cash -= (fill.notional + fill.commission)
        pos = positions.get(fill.symbol, BacktestPosition(symbol=fill.symbol))
        new_qty = pos.quantity + fill.quantity
        new_avg = ((pos.quantity * pos.average_entry_price) + (fill.quantity * fill.price)) / new_qty
        positions[fill.symbol] = BacktestPosition(
            symbol=fill.symbol,
            quantity=new_qty,
            average_entry_price=new_avg,
            notional=new_qty * fill.price,
        )
    else:
        cash += (fill.notional - fill.commission)
        pos = positions.get(fill.symbol)
        if pos:
            new_qty = pos.quantity - fill.quantity
            if new_qty <= 0:
                positions.pop(fill.symbol, None)
            else:
                positions[fill.symbol] = BacktestPosition(
                    symbol=fill.symbol,
                    quantity=new_qty,
                    average_entry_price=pos.average_entry_price,
                    notional=new_qty * fill.price,
                )
    return cash, positions


def _observations_for_bar(bar: MarketBar, orders: list[BacktestOrder]) -> dict[str, Any]:
    return {
        "bar": {
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "symbol": bar.symbol,
        },
        "signal_count": len(orders),
        "signals": [
            {
                "side": o.side,
                "quantity": o.quantity,
                "price": o.price,
                "type": o.type,
                "order_id": o.order_id,
            }
            for o in orders
        ],
    }


def run_autonomous_paper_loop(
    *,
    config: AtlasConfig,
    symbol: str | None = None,
    strategy_id: str | None = None,
    strategy_parameters: dict[str, Any] | None = None,
    data_path: str | Path | None = None,
    max_cycles: int = 1,
    output_dir: str | Path | None = None,
    audit_writer: AuditWriter | None = None,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
) -> AutonomousPaperResult:
    """Run a deterministic, paper-only autonomous decision loop.

    This function never calls a real broker, never loads real credentials, and
    never reaches a live order-submission path. It operates on local sample/CSV
    data and routes every proposed order through :class:`RiskManager` in paper
    mode before simulating a fill locally.
    """
    effective_symbol = symbol or config.market.symbol or config.backtest.default_symbol
    if not effective_symbol:
        return AutonomousPaperResult(
            run_id=run_id or generate_run_id(),
            status="failed",
            symbol="",
            strategy_id=strategy_id or "moving_average_cross",
            bars_processed=0,
            decisions=0,
            trades_executed=0,
            trades_blocked=0,
            no_trade_count=0,
            decisions_path="",
            manifest_path="",
            audit_log_path="",
            errors=["No trading symbol configured. Set market.symbol or pass --symbol."],
        )

    effective_symbol = effective_symbol.upper()
    effective_strategy = strategy_id or "moving_average_cross"
    effective_strategy_parameters = strategy_parameters or {}
    effective_data_path = Path(data_path or config.backtest.data_path)
    effective_output_dir = Path(output_dir or (config.reports_dir / "autonomous_paper"))
    effective_output_dir.mkdir(parents=True, exist_ok=True)

    effective_run_id = run_id or generate_run_id()
    audit_log_path = Path(config.audit_dir) / "events.jsonl"
    if audit_writer is None:
        audit_writer = AuditWriter(audit_log_path)
    if event_logger is None:
        event_logger = EventLogger(config.events_dir)

    audit_writer.start_run(effective_run_id)
    event_logger.write(
        "autonomous_paper_started",
        run_id=effective_run_id,
        command="atlas agent autonomous-paper",
        mode="paper",
        payload={
            "symbol": effective_symbol,
            "strategy_id": effective_strategy,
            "strategy_parameters": effective_strategy_parameters,
            "data_path": str(effective_data_path),
            "max_cycles": max_cycles,
        },
    )

    try:
        bars = load_market_data(str(effective_data_path), symbol=effective_symbol)
    except Exception as exc:
        audit_writer.finish_run("failed", final_status_text=f"data_load_failed: {exc}")
        return AutonomousPaperResult(
            run_id=effective_run_id,
            status="failed",
            symbol=effective_symbol,
            strategy_id=effective_strategy,
            bars_processed=0,
            decisions=0,
            trades_executed=0,
            trades_blocked=0,
            no_trade_count=0,
            decisions_path="",
            manifest_path="",
            audit_log_path=str(audit_log_path),
            errors=[f"Failed to load market data: {exc}"],
        )

    if not bars:
        audit_writer.finish_run("failed", final_status_text="no_bars_loaded")
        return AutonomousPaperResult(
            run_id=effective_run_id,
            status="failed",
            symbol=effective_symbol,
            strategy_id=effective_strategy,
            bars_processed=0,
            decisions=0,
            trades_executed=0,
            trades_blocked=0,
            no_trade_count=0,
            decisions_path="",
            manifest_path="",
            audit_log_path=str(audit_log_path),
            errors=["No bars loaded for symbol."],
        )

    strategy = get_strategy(effective_strategy, parameters=effective_strategy_parameters)

    runtime_config = BacktestRuntimeConfig(
        run_id=effective_run_id,
        symbol=effective_symbol,
        data_path=str(effective_data_path),
        initial_equity=config.backtest.initial_cash,
        strategy_mode=effective_strategy,
        risk_enabled=True,
    )
    executor = ExecutionSimulator(runtime_config)

    risk_limits = RiskLimits(
        max_position_notional=config.risk.max_position_notional,
        max_single_trade_notional=config.risk.max_order_notional,
        allowed_symbols=config.risk.symbol_allowlist,
        blocked_symbols=config.risk.symbol_blocklist or set(),
        live_trading_enabled=False,
        paper_only=True,
        minimum_confidence=config.risk.minimum_confidence,
        allow_shorting=config.risk.allow_leverage,
        require_stop_loss_live=config.risk.require_stop_loss_live,
    )
    risk_manager = RiskManager(
        limits=risk_limits,
        audit_writer=audit_writer,
        run_id=effective_run_id,
        kill_switch_enabled=config.safety.kill_switch_enabled,
    )

    decisions_path = effective_output_dir / f"{effective_run_id}-decisions.jsonl"
    manifest_path = effective_output_dir / f"{effective_run_id}-manifest.json"

    cash = float(config.backtest.initial_cash)
    positions: dict[str, BacktestPosition] = {}
    pending_orders: list[BacktestOrder] = []

    decisions_count = 0
    trades_executed = 0
    trades_blocked = 0
    no_trade_count = 0
    errors: list[str] = []

    bar_count = min(max_cycles, len(bars)) if max_cycles > 0 else len(bars)
    bars_to_process = bars[:bar_count]

    with open(decisions_path, "w", encoding="utf-8") as decisions_file:
        for iteration, bar in enumerate(bars_to_process):
            context = StrategyContext(
                run_id=effective_run_id,
                symbol=effective_symbol,
                bar_index=iteration,
                cash=cash,
                positions=dict(positions),
                pending_orders=list(pending_orders),
                config=runtime_config,
            )

            orders = strategy.generate_orders(bars=bars[: iteration + 1], context=context)
            observations = _observations_for_bar(bar, orders)

            decision_event_ids: list[str] = []

            if not orders:
                decision = AutonomousDecision(
                    run_id=effective_run_id,
                    iteration=iteration,
                    timestamp=datetime.now(UTC).isoformat(),
                    symbol=effective_symbol,
                    data_source=str(effective_data_path),
                    strategy_id=effective_strategy,
                    observations=observations,
                    proposed_action="hold",
                    proposed_order=None,
                    risk_result={"status": "not_applicable", "allowed": True},
                    decision_state="no_trade",
                    blocked_reason=None,
                    manifest_path=str(manifest_path),
                )
                no_trade_count += 1
            else:
                order = orders[0]
                proposed_action = order.side
                proposed_order_payload = {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                    "type": order.type,
                    "price": order.price,
                }

                snapshot = _build_portfolio_snapshot(
                    cash=cash,
                    positions=positions,
                    pending_orders=pending_orders,
                    current_price=bar.close,
                )
                risk_input = OrderRiskInput(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=bar.close,
                    notional=order.quantity * bar.close,
                )
                risk_decision = risk_manager.evaluate_order(
                    risk_input,
                    snapshot,
                    mode="paper",
                )
                risk_result = {
                    "status": risk_decision.status,
                    "allowed": risk_decision.allowed,
                    "reason": risk_decision.reason,
                    "violations": [v.model_dump() for v in risk_decision.violations],
                    "classification": risk_decision.classification,
                }

                if risk_decision.allowed and risk_decision.status == "allowed":
                    fill = executor.process_order(order, bar)
                    if fill:
                        cash, positions = _apply_fill(fill=fill, cash=cash, positions=positions)
                        decision_state = "paper_executed"
                        trades_executed += 1
                        fill_event = audit_writer.write_event(
                            "autonomous_paper_fill",
                            run_id=effective_run_id,
                            iteration=iteration,
                            payload=redact_payload(fill.model_dump(mode="json")),
                        )
                        decision_event_ids.append(fill_event.event_id)
                    else:
                        decision_state = "no_trade"
                        no_trade_count += 1
                    blocked_reason = None
                else:
                    decision_state = "risk_blocked"
                    trades_blocked += 1
                    blocked_reason = risk_decision.reason or "; ".join(
                        v.message for v in risk_decision.violations
                    )

                decision = AutonomousDecision(
                    run_id=effective_run_id,
                    iteration=iteration,
                    timestamp=datetime.now(UTC).isoformat(),
                    symbol=effective_symbol,
                    data_source=str(effective_data_path),
                    strategy_id=effective_strategy,
                    observations=observations,
                    proposed_action=proposed_action,
                    proposed_order=proposed_order_payload,
                    risk_result=risk_result,
                    decision_state=decision_state,
                    blocked_reason=blocked_reason,
                    manifest_path=str(manifest_path),
                )

            decision_event = audit_writer.write_event(
                "autonomous_paper_decision",
                run_id=effective_run_id,
                iteration=iteration,
                payload=redact_payload(decision.model_dump(mode="json")),
            )
            decision_event_ids.insert(0, decision_event.event_id)
            decision.audit_event_ids = decision_event_ids

            decisions_file.write(json.dumps(decision.model_dump(mode="json")) + "\n")
            decisions_count += 1

    summary = {
        "run_id": effective_run_id,
        "mode": "paper",
        "symbol": effective_symbol,
        "strategy_id": effective_strategy,
        "data_source": str(effective_data_path),
        "bars_processed": len(bars_to_process),
        "decisions": decisions_count,
        "trades_executed": trades_executed,
        "trades_blocked": trades_blocked,
        "no_trade_count": no_trade_count,
        "errors": errors,
        "decisions_path": str(decisions_path),
        "manifest_path": str(manifest_path),
        "audit_log_path": str(audit_log_path),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    audit_writer.write_event(
        "autonomous_paper_manifest_sealed",
        run_id=effective_run_id,
        payload=redact_payload(summary),
    )
    audit_writer.finish_run("completed", final_status_text="autonomous_paper_completed")

    event_logger.write(
        "autonomous_paper_completed",
        run_id=effective_run_id,
        command="atlas agent autonomous-paper",
        mode="paper",
        payload=redact_payload(summary),
    )

    return AutonomousPaperResult(
        run_id=effective_run_id,
        status="completed",
        symbol=effective_symbol,
        strategy_id=effective_strategy,
        bars_processed=len(bars_to_process),
        decisions=decisions_count,
        trades_executed=trades_executed,
        trades_blocked=trades_blocked,
        no_trade_count=no_trade_count,
        decisions_path=str(decisions_path),
        manifest_path=str(manifest_path),
        audit_log_path=str(audit_log_path),
        errors=errors,
    )


def build_autonomous_paper_evidence(
    run_id: str,
    decisions_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
) -> Path:
    """Build a local evidence bundle for a prior autonomous paper loop run.

    The bundle contains only already-redacted, paper-only local artifacts.
    """
    from hashlib import sha256

    decisions_path = Path(decisions_path)
    manifest_path = Path(manifest_path)
    if not decisions_path.name or not manifest_path.name:
        raise ValueError("decisions_path and manifest_path must be non-empty")
    output_dir = Path(output_dir)
    bundle_dir = output_dir / run_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    def _copy_and_hash(src: Path, dst: Path) -> str:
        text = src.read_text(encoding="utf-8")
        dst.write_text(text, encoding="utf-8")
        return sha256(text.encode("utf-8")).hexdigest()

    checksums: dict[str, str] = {}
    if decisions_path.is_file():
        checksums["decisions.jsonl"] = _copy_and_hash(
            decisions_path, bundle_dir / "decisions.jsonl"
        )
    if manifest_path.is_file():
        checksums["manifest.json"] = _copy_and_hash(
            manifest_path, bundle_dir / "manifest.json"
        )

    summary = {
        "run_id": run_id,
        "bundle_dir": str(bundle_dir),
        "files": list(checksums.keys()),
        "checksums": checksums,
        "mode": "paper",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (bundle_dir / "evidence.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return bundle_dir
