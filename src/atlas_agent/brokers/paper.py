# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/paper.py
# PURPOSE: The default broker: a deterministic simulator with no network calls and
#          no credentials. It is the fallback everything else degrades TO, so it has
#          to behave like a real broker in every respect that matters — including
#          rejecting the orders a real one would reject.
# DEPS:    portfolio.state (the simulated book), execution.order (the contract),
#          execution.audit + portfolio.journal (the same records a live run writes)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import math
from dataclasses import dataclass, field
from uuid import uuid4
from typing import List

from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import (
    AccountSnapshot,
    FlattenResult,
    Order,
    OrderResult,
)
from atlas_agent.portfolio.journal import TradeJournal
from atlas_agent.portfolio.positions import Position
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.brokers.models import (
    BrokerAccountState,
    BrokerPosition,
    BrokerOrder,
    BrokerBalance,
)
from atlas_agent.brokers.base import BrokerProvider


# ==============================================================================
# PAPER BROKER
# ==============================================================================

@dataclass
class PaperBroker:
    state: PortfolioState
    audit: AuditLogger | None = None
    journal: TradeJournal | None = None
    fills: list[Order] = field(default_factory=list)
    open_orders_list: list[BrokerOrder] = field(default_factory=list)

    # --- Account ---

    def get_account(self) -> AccountSnapshot:
        equity = self.state.equity()
        return AccountSnapshot(
            cash=self.state.cash,
            equity=equity,
            buying_power=self.state.cash,
            mode="paper",
        )

    def get_positions(self) -> list[Position]:
        return list(self.state.positions.values())

    # --- Orders ---

    def place_order(self, order: Order) -> OrderResult:
        # The paper broker validates as strictly as a live one would. That is the point:
        # if a bad price sailed through here, the bug would only ever surface in
        # production, and paper mode's whole job is to be the place where it does not.
        price = order.limit_price
        if price is None or isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="paper orders require a positive price",
                reasons=("missing price",),
            )
        if isinstance(order.quantity, bool) or not isinstance(order.quantity, (int, float)) or not math.isfinite(order.quantity) or order.quantity <= 0:
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="paper orders require a positive quantity",
                reasons=("invalid quantity",),
            )
        symbol = order.symbol.upper()
        if order.side.lower() == "buy":
            cost = order.quantity * price
            if cost > self.state.cash:
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="rejected",
                    message="insufficient paper cash",
                    reasons=("insufficient cash",),
                )
            position = self.state.positions.get(symbol, Position(symbol=symbol))
            total_cost = position.quantity * position.average_price + cost
            position.quantity += order.quantity
            position.average_price = total_cost / position.quantity
            self.state.positions[symbol] = position
            self.state.cash -= cost
        else:
            position = self.state.positions.get(symbol)
            if position is None or position.quantity < order.quantity:
                return OrderResult(
                    accepted=False,
                    filled=False,
                    order_id=order.id,
                    status="rejected",
                    message="cannot sell more than current paper position",
                    reasons=("insufficient position",),
                )
            self.state.cash += order.quantity * price
            position.quantity -= order.quantity
            if position.quantity == 0:
                position.average_price = 0.0
            self.state.positions[symbol] = position
        self.state.trades_today += 1
        self.state.seen_order_ids.add(order.id)
        self.fills.append(order)
        if self.audit:
            self.audit.write("paper_order_filled", {"order": order})
        if self.journal:
            self.journal.append("executed", f"{order.side} {order.quantity} {symbol}")
        return OrderResult(
            accepted=True,
            filled=True,
            order_id=order.id,
            status="filled",
            message="paper order filled",
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(
            accepted=True,
            filled=False,
            order_id=order_id,
            status="cancelled",
            message="paper order cancelled",
        )

    def flatten_all(
        self,
        strategy: str = "market",
        bps: int = 25,
    ) -> FlattenResult:
        if strategy not in {"market", "aggressive_limit"}:
            return FlattenResult(
                accepted=False,
                status="failed",
                message=f"unsupported flatten strategy: {strategy}",
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )
        if bps < 0:
            return FlattenResult(
                accepted=False,
                status="failed",
                message="bps must be non-negative",
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )

        open_positions = [
            position
            for position in self.state.positions.values()
            if abs(position.quantity) > 0
        ]
        if not open_positions:
            return FlattenResult(
                accepted=True,
                status="noop",
                message="no open positions to flatten",
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )

        order_results: list[OrderResult] = []
        failed_symbols: list[str] = []
        for position in open_positions:
            if position.quantity < 0:
                order_results.append(
                    OrderResult(
                        accepted=False,
                        filled=False,
                        order_id=f"flatten-{position.symbol.lower()}-unsupported",
                        status="rejected",
                        message="paper flatten does not support negative quantities",
                        reasons=("unsupported short position",),
                    )
                )
                failed_symbols.append(position.symbol)
                continue

            side = "sell"
            quantity = abs(position.quantity)
            price = _flatten_price(position, strategy=strategy, bps=bps)
            order = Order(
                symbol=position.symbol,
                side=side,
                quantity=quantity,
                order_type="limit",
                limit_price=price,
                source="kill_switch_flatten",
                id=f"flatten-{position.symbol.lower()}-{uuid4()}",
            )
            result = self.place_order(order)
            order_results.append(result)
            if not result.filled:
                failed_symbols.append(position.symbol)

        closed = sum(1 for result in order_results if result.filled)
        failed = len(order_results) - closed
        if failed == 0:
            status = "flattened"
            message = "all positions flattened"
        elif closed == 0:
            status = "failed"
            message = "flatten failed for all positions"
        else:
            status = "partial"
            message = "flatten completed with partial success"
        return FlattenResult(
            accepted=closed > 0,
            status=status,
            message=message,
            strategy=strategy,
            bps=bps,
            attempted=len(order_results),
            closed=closed,
            failed=failed,
            order_results=tuple(order_results),
            failed_symbols=tuple(failed_symbols),
        )


@dataclass
class PaperBrokerAdapter(BrokerProvider):
    broker: PaperBroker

    def get_account_state(self) -> BrokerAccountState:
        acc = self.broker.get_account()
        return BrokerAccountState(
            account_id="paper_account",
            cash=acc.cash,
            equity=acc.equity,
            buying_power=acc.buying_power,
            is_live=False
        )

    def get_positions(self) -> List[BrokerPosition]:
        return [
            BrokerPosition(
                symbol=p.symbol,
                quantity=p.quantity,
                average_price=p.average_price,
                market_price=p.average_price, # Simple paper pricing
                side="long" if p.quantity > 0 else "short" if p.quantity < 0 else "flat"
            )
            for p in self.broker.get_positions()
        ]

    def get_open_orders(self) -> List[BrokerOrder]:
        return self.broker.open_orders_list

    def get_balances(self) -> List[BrokerBalance]:
        return [
            BrokerBalance(
                asset="USD",
                free=self.broker.state.cash,
                locked=0.0,
                total=self.broker.state.cash
            )
        ]


def _flatten_price(position: Position, *, strategy: str, bps: int) -> float:
    base_price = position.average_price if position.average_price > 0 else 1.0
    if strategy == "market":
        return base_price
    spread = bps / 10_000.0
    if position.quantity > 0:
        return max(base_price * (1.0 - spread), 0.01)
    return max(base_price * (1.0 + spread), 0.01)
