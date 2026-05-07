from __future__ import annotations

from dataclasses import dataclass, field

from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import AccountSnapshot, Order, OrderResult
from atlas_agent.portfolio.journal import TradeJournal
from atlas_agent.portfolio.positions import Position
from atlas_agent.portfolio.state import PortfolioState


@dataclass
class PaperBroker:
    state: PortfolioState
    audit: AuditLogger | None = None
    journal: TradeJournal | None = None
    fills: list[Order] = field(default_factory=list)

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

    def place_order(self, order: Order) -> OrderResult:
        price = order.limit_price
        if price is None or price <= 0:
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="rejected",
                message="paper orders require a positive price",
                reasons=("missing price",),
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

