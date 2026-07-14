# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/autonomous_paper_kernel.py
# PURPOSE: The deterministic core of the autonomous paper loop: given a state and a
#          decision, produce the next state. Pure and side-effect-free by design —
#          the same inputs must always yield the same book, or the whole exercise
#          proves nothing.
# DEPS:    agent.autonomous_paper_models, audit (the record)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from atlas_agent.audit import AuditWriter
from atlas_agent.audit.redaction import redact_payload
from atlas_agent.backtest.execution import ExecutionSimulator
from atlas_agent.backtest.models import BacktestConfig, BacktestFill, BacktestOrder, BacktestPosition, MarketBar
from atlas_agent.backtest.strategy import StrategyContext
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PendingOrder, PortfolioSnapshot, RiskPosition


@dataclass
class KernelCycleResult:
    decision_state: str  # "no_trade", "risk_blocked", "paper_executed", "partially_executed", "failed"
    proposed_action: str  # "buy", "sell", "hold"
    proposed_order: dict[str, Any] | None
    observations: dict[str, Any]
    risk_result: dict[str, Any]
    fills: list[BacktestFill] = field(default_factory=list)
    rejected_orders: list[BacktestOrder] = field(default_factory=list)
    allowed_orders: list[BacktestOrder] = field(default_factory=list)
    cash: float = 0.0
    positions: dict[str, BacktestPosition] = field(default_factory=dict)
    audit_event_ids: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


def build_portfolio_snapshot(
    *,
    cash: float,
    positions: dict[str, BacktestPosition],
    pending_orders: list[BacktestOrder],
    current_price: float,
) -> PortfolioSnapshot:
    """Build a risk-system PortfolioSnapshot from backtest state."""
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


def apply_fill(
    *,
    fill: BacktestFill,
    cash: float,
    positions: dict[str, BacktestPosition],
    allow_shorting: bool = False,
) -> tuple[float, dict[str, BacktestPosition]]:
    """Return updated cash and positions after applying a paper fill."""
    cash = float(cash)
    positions = deepcopy(positions)
    if fill.side == "buy":
        cash -= fill.notional + fill.commission
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
        cash += fill.notional - fill.commission
        pos = positions.get(fill.symbol, BacktestPosition(symbol=fill.symbol))
        if fill.quantity > pos.quantity and not allow_shorting:
            raise ValueError("sell fill quantity exceeds position")
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


def observations_for_bar(bar: MarketBar, orders: list[BacktestOrder]) -> dict[str, Any]:
    """Build observation payload for a bar and the orders generated for it."""
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


def _order_to_payload(order: BacktestOrder) -> dict[str, Any]:
    """Serialize a BacktestOrder into a plain dictionary for audit payloads."""
    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "type": order.type,
        "price": order.price,
    }


def run_kernel_cycle(
    *,
    bar: MarketBar,
    fill_bar: MarketBar | None = None,
    bar_index: int,
    bars_so_far: list[MarketBar],
    cash: float,
    positions: dict[str, BacktestPosition],
    pending_orders: list[BacktestOrder],
    strategy,
    executor: ExecutionSimulator,
    risk_manager: RiskManager,
    symbol: str,
    run_id: str,
    config: BacktestConfig,
    audit_writer: AuditWriter,
    max_orders_per_cycle: int = 10,
    execute_fills: bool = True,
) -> KernelCycleResult:
    """Execute one execution-neutral cycle.

    Generates orders, evaluates each through RiskManager in paper mode,
    simulates allowed fills sequentially, and returns the updated state.

    Risk evaluation uses ``bar``; fill simulation uses ``fill_bar`` if
    provided, otherwise ``bar``. When ``execute_fills`` is False, allowed
    orders are captured in ``allowed_orders`` without modifying cash or
    positions.
    """
    context = StrategyContext(
        run_id=run_id,
        symbol=symbol,
        bar_index=bar_index,
        cash=cash,
        positions=dict(positions),
        pending_orders=list(pending_orders),
        config=config,
    )

    try:
        orders = strategy.generate_orders(bars=bars_so_far, context=context)
        observations = observations_for_bar(bar, orders)

        if not orders:
            decision_payload = {
                "run_id": run_id,
                "bar_index": bar_index,
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": symbol,
                "proposed_action": "hold",
                "proposed_order": None,
                "decision_state": "no_trade",
                "blocked_reason": None,
                "risk_result": {"status": "not_applicable", "allowed": True},
                "observations": observations,
                "fill_count": 0,
                "rejection_count": 0,
            }
            decision_event = audit_writer.write_event(
                "autonomous_paper_decision",
                run_id=run_id,
                iteration=bar_index,
                payload=redact_payload(decision_payload),
            )
            return KernelCycleResult(
                decision_state="no_trade",
                proposed_action="hold",
                proposed_order=None,
                observations=observations,
                risk_result={"status": "not_applicable", "allowed": True},
                fills=[],
                rejected_orders=[],
                cash=cash,
                positions=dict(positions),
                audit_event_ids=[decision_event.event_id],
                blocked_reason=None,
            )

        truncated = len(orders) > max_orders_per_cycle
        processed_orders = orders[:max_orders_per_cycle]
        warnings: list[str] = []
        if truncated:
            warnings.append(
                f"Strategy generated {len(orders)} orders; truncated to max_orders_per_cycle={max_orders_per_cycle}"
            )

        fills: list[BacktestFill] = []
        rejected_orders: list[BacktestOrder] = []
        allowed_orders: list[BacktestOrder] = []
        blocked_reasons: list[str] = []
        order_results: list[dict[str, Any]] = []
        audit_event_ids: list[str] = []

        proposed_action = processed_orders[0].side
        proposed_order = _order_to_payload(processed_orders[0])

        for order in processed_orders:
            snapshot = build_portfolio_snapshot(
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
            risk_decision = risk_manager.evaluate_order(risk_input, snapshot, mode="paper")
            order_result = {
                "order_id": order.order_id,
                "status": risk_decision.status,
                "allowed": risk_decision.allowed,
                "reason": risk_decision.reason,
                "violations": [v.model_dump() for v in risk_decision.violations],
                "classification": risk_decision.classification,
            }
            order_results.append(order_result)

            if risk_decision.allowed and risk_decision.status == "allowed":
                if execute_fills:
                    fill = executor.process_order(order, fill_bar if fill_bar is not None else bar)
                    if fill:
                        cash, positions = apply_fill(
                            fill=fill,
                            cash=cash,
                            positions=positions,
                            allow_shorting=risk_manager.limits.allow_shorting,
                        )
                        fills.append(fill)
                        fill_event = audit_writer.write_event(
                            "autonomous_paper_fill",
                            run_id=run_id,
                            iteration=bar_index,
                            payload=redact_payload(fill.model_dump(mode="json")),
                        )
                        audit_event_ids.append(fill_event.event_id)
                else:
                    allowed_orders.append(order)
            else:
                rejected_orders.append(order)
                blocked_reason = risk_decision.reason or "; ".join(
                    v.message for v in risk_decision.violations
                )
                if blocked_reason:
                    blocked_reasons.append(blocked_reason)

        executed_or_allowed = fills if execute_fills else allowed_orders
        if executed_or_allowed and not rejected_orders:
            decision_state = "paper_executed"
        elif rejected_orders and not executed_or_allowed:
            decision_state = "risk_blocked"
        elif executed_or_allowed and rejected_orders:
            decision_state = "partially_executed"
        else:
            decision_state = "no_trade"

        blocked_reason = "; ".join(blocked_reasons) if blocked_reasons else None

        all_allowed = all(r["allowed"] and r["status"] == "allowed" for r in order_results)

        risk_result: dict[str, Any] = {
            "status": "allowed" if all_allowed else "blocked",
            "allowed": all_allowed,
            "warnings": warnings,
            "orders_evaluated": len(processed_orders),
            "orders_generated": len(orders),
            "order_results": order_results,
        }
        if blocked_reasons:
            risk_result["reason"] = "; ".join(blocked_reasons)

        decision_payload = {
            "run_id": run_id,
            "bar_index": bar_index,
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": symbol,
            "proposed_action": proposed_action,
            "proposed_order": proposed_order,
            "decision_state": decision_state,
            "blocked_reason": blocked_reason,
            "risk_result": risk_result,
            "observations": observations,
            "fill_count": len(fills),
            "rejection_count": len(rejected_orders),
        }
        decision_event = audit_writer.write_event(
            "autonomous_paper_decision",
            run_id=run_id,
            iteration=bar_index,
            payload=redact_payload(decision_payload),
        )
        audit_event_ids.insert(0, decision_event.event_id)

        return KernelCycleResult(
            decision_state=decision_state,
            proposed_action=proposed_action,
            proposed_order=proposed_order,
            observations=observations,
            risk_result=risk_result,
            fills=fills,
            rejected_orders=rejected_orders,
            allowed_orders=allowed_orders,
            cash=cash,
            positions=positions,
            audit_event_ids=audit_event_ids,
            blocked_reason=blocked_reason,
        )

    except Exception as exc:
        error_type = type(exc).__name__
        blocked_reason = f"cycle_error: {error_type}"
        try:
            audit_writer.write_event(
                "autonomous_paper_cycle_failed",
                run_id=run_id,
                iteration=bar_index,
                payload=redact_payload(
                    {
                        "run_id": run_id,
                        "bar_index": bar_index,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "symbol": symbol,
                        "error_type": error_type,
                    }
                ),
            )
        except Exception:
            pass

        return KernelCycleResult(
            decision_state="failed",
            proposed_action="hold",
            proposed_order=None,
            observations={},
            risk_result={"status": "error", "allowed": False, "error_type": error_type},
            fills=[],
            rejected_orders=[],
            cash=cash,
            positions=dict(positions),
            audit_event_ids=[],
            blocked_reason=blocked_reason,
        )
