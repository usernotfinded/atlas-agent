from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import List, Dict, Any, Optional

from atlas_agent.backtest.models import (
    BacktestConfig, 
    BacktestResult, 
    BacktestMetrics, 
    BacktestOrder, 
    BacktestPosition,
    BacktestFill,
    MarketBar
)
from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.execution import ExecutionSimulator
from atlas_agent.backtest.metrics import calculate_metrics, TradeRecord
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot, PendingOrder
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.audit import AuditWriter


class BacktestEngine:
    def __init__(
        self, 
        config: BacktestConfig,
        audit_writer: Optional[AuditWriter] = None
    ):
        self.config = config
        self.audit_writer = audit_writer
        self.executor = ExecutionSimulator(config)
        
        # Internal state
        self.cash = config.initial_equity
        self.positions: Dict[str, BacktestPosition] = {}
        self.fills: List[BacktestFill] = []
        self.pending_orders: List[BacktestOrder] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.diagnostics: Dict[str, Any] = {"blocked_orders": []}

        # Initialize Risk Manager if enabled
        self.risk_manager = None
        if config.risk_enabled:
            # Create a simple RiskLimits based on config if needed, 
            # or use defaults. For backtest, we might want to be strict.
            limits = RiskLimits(
                max_position_notional=config.initial_equity * 0.5,
                max_single_trade_notional=config.initial_equity * 0.25,
                live_trading_enabled=False,
                paper_only=True
            )
            self.risk_manager = RiskManager(
                limits=limits,
                audit_writer=audit_writer,
                run_id=config.run_id,
                kill_switch_enabled=config.kill_switch_state
            )

    def run(self) -> BacktestResult:
        started_at = datetime.now()
        if self.audit_writer:
            self.audit_writer.write_event(
                "backtest_started",
                run_id=self.config.run_id,
                payload=self.config.model_dump(mode='json')
            )

        bars = load_market_data(self.config.data_path, self.config.symbol)
        
        for bar in bars:
            self._step(bar)

        # Finalize
        final_equity = self._calculate_equity(bars[-1].close)
        metrics = self._calculate_metrics(final_equity, bars)
        
        result = BacktestResult(
            run_id=self.config.run_id,
            status="completed",
            config=self.config,
            metrics=metrics,
            fills=self.fills,
            equity_curve=self.equity_curve,
            diagnostics=self.diagnostics,
            started_at=started_at,
            completed_at=datetime.now()
        )

        if self.audit_writer:
            self.audit_writer.write_event(
                "backtest_completed",
                run_id=self.config.run_id,
                payload=result.model_dump(mode='json')
            )

        return result

    def _step(self, bar: MarketBar):
        # 1. Update equity curve at start of bar
        current_equity = self._calculate_equity(bar.open)
        self.equity_curve.append({
            "timestamp": bar.timestamp.isoformat(),
            "equity": current_equity
        })

        # 2. Strategy logic (Buy and Hold MVP)
        if self.config.strategy_mode == "buy_and_hold":
            if not self.positions and not self.pending_orders:
                # Propose buy order
                qty = self.cash / bar.open
                if qty > 0:
                    order = BacktestOrder(
                        order_id=str(uuid4()),
                        timestamp=bar.timestamp,
                        symbol=bar.symbol or self.config.symbol,
                        side="buy",
                        quantity=qty,
                        price=bar.open
                    )
                    self.pending_orders.append(order)

        # 3. Process pending orders
        remaining_pending = []
        for order in self.pending_orders:
            # Risk check
            if self.risk_manager:
                risk_input = OrderRiskInput(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=bar.open,
                    notional=order.quantity * bar.open
                )
                portfolio_snapshot = self._get_portfolio_snapshot(bar.open)
                
                decision = self.risk_manager.evaluate_order(
                    risk_input, 
                    portfolio_snapshot,
                    mode="paper"
                )
                
                if not decision.allowed:
                    order.status = "blocked"
                    self.diagnostics["blocked_orders"].append({
                        "order_id": order.order_id,
                        "reason": decision.reason,
                        "violations": [v.model_dump() for v in decision.violations]
                    })
                    if self.audit_writer:
                        self.audit_writer.write_event(
                            "backtest_order_blocked",
                            run_id=self.config.run_id,
                            payload={"order_id": order.order_id, "reason": decision.reason}
                        )
                    continue

            # Execution simulation
            fill = self.executor.process_order(order, bar)
            if fill:
                self._apply_fill(fill)
                order.status = "filled"
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "backtest_order_filled",
                        run_id=self.config.run_id,
                        payload=fill.model_dump(mode='json')
                    )
            else:
                remaining_pending.append(order)
        
        self.pending_orders = remaining_pending

    def _apply_fill(self, fill: BacktestFill):
        self.fills.append(fill)
        if fill.side == "buy":
            self.cash -= (fill.notional + fill.commission)
            pos = self.positions.get(fill.symbol, BacktestPosition(symbol=fill.symbol))
            
            new_qty = pos.quantity + fill.quantity
            new_avg_price = ((pos.quantity * pos.average_entry_price) + (fill.quantity * fill.price)) / new_qty
            
            self.positions[fill.symbol] = BacktestPosition(
                symbol=fill.symbol,
                quantity=new_qty,
                average_entry_price=new_avg_price,
                notional=new_qty * fill.price
            )
        else:
            self.cash += (fill.notional - fill.commission)
            pos = self.positions.get(fill.symbol)
            if pos:
                new_qty = pos.quantity - fill.quantity
                if new_qty <= 0:
                    del self.positions[fill.symbol]
                else:
                    self.positions[fill.symbol] = BacktestPosition(
                        symbol=fill.symbol,
                        quantity=new_qty,
                        average_entry_price=pos.average_entry_price,
                        notional=new_qty * fill.price
                    )

    def _calculate_equity(self, current_price: float) -> float:
        position_value = sum(pos.quantity * current_price for pos in self.positions.values())
        return self.cash + position_value

    def _get_portfolio_snapshot(self, current_price: float) -> PortfolioSnapshot:
        positions = []
        for pos in self.positions.values():
            from atlas_agent.risk.models import PositionSnapshot
            positions.append(PositionSnapshot(
                symbol=pos.symbol,
                quantity=pos.quantity,
                average_price=pos.average_entry_price,
                notional=pos.quantity * current_price
            ))
        
        open_orders = []
        for o in self.pending_orders:
            open_orders.append(PendingOrder(
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                quantity=o.quantity,
                remaining_quantity=o.quantity,
                price=o.price or 0.0,
                status="pending"
            ))

        equity = self._calculate_equity(current_price)
        return PortfolioSnapshot(
            cash=self.cash,
            equity=equity,
            positions=positions,
            open_orders=open_orders,
            total_exposure=sum(p.notional for p in positions)
        )

    def _calculate_metrics(self, final_equity: float, bars: List[MarketBar]) -> BacktestMetrics:
        # Convert fills to TradeRecords for calculate_metrics
        trade_records = []
        for fill in self.fills:
            # We don't track realized PnL perfectly here for each trade record, 
            # but calculate_metrics handles it for closed returns if side is 'sell'.
            # For MVP, we pass realized_pnl=0 and it might miss some win_rate info if not perfectly tracked,
            # but let's try to pass what we can.
            realized_pnl = 0.0
            if fill.side == "sell":
                # Find corresponding buy
                # (Simple FIFO or Average would work, but metrics.py expects it per trade)
                pass

            trade_records.append(TradeRecord(
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                notional=fill.notional,
                realized_pnl=realized_pnl
            ))

        equity_curve_values = [entry["equity"] for entry in self.equity_curve]
        exposure_points = [entry["equity"] != self.cash for entry in self.equity_curve]

        return calculate_metrics(
            starting_cash=self.config.initial_equity,
            ending_equity=final_equity,
            equity_curve=equity_curve_values,
            trades=trade_records,
            exposure_points=exposure_points,
            start_price=bars[0].close,
            end_price=bars[-1].close
        )
