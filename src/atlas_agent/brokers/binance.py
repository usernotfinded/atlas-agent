from __future__ import annotations

import os
from dataclasses import dataclass

from atlas_agent.config import AtlasConfig
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.execution.order import AccountSnapshot, FlattenResult, Order, OrderResult
from atlas_agent.portfolio.positions import Position


@dataclass(frozen=True)
class BinanceBroker:
    config: AtlasConfig

    def _validate_config(self) -> None:
        reasons = list(self.config.live_disabled_reasons())
        if self.config.live_broker != "binance":
            reasons.append("LIVE_BROKER must be binance")
        if not os.getenv("BINANCE_API_KEY"):
            reasons.append("BINANCE_API_KEY is missing")
        if not os.getenv("BINANCE_API_SECRET"):
            reasons.append("BINANCE_API_SECRET is missing")
        if reasons:
            raise BrokerConfigurationError("; ".join(reasons))

    def get_account(self) -> AccountSnapshot:
        self._validate_config()
        return AccountSnapshot(cash=0.0, equity=0.0, buying_power=0.0, mode="live")

    def get_positions(self) -> list[Position]:
        self._validate_config()
        return []

    def place_order(self, order: Order) -> OrderResult:
        self._validate_config()
        try:
            import ccxt  # type: ignore
        except ModuleNotFoundError as exc:
            raise BrokerConfigurationError("ccxt is required for BinanceBroker") from exc
        exchange = ccxt.binance(
            {
                "apiKey": os.environ["BINANCE_API_KEY"],
                "secret": os.environ["BINANCE_API_SECRET"],
                "options": {"defaultType": "spot"},
                "enableRateLimit": True,
            }
        )
        symbol = order.symbol.replace("-", "/")
        if order.order_type == "limit":
            raw = exchange.create_limit_order(
                symbol,
                order.side.lower(),
                order.quantity,
                order.limit_price,
            )
        else:
            raw = exchange.create_market_order(symbol, order.side.lower(), order.quantity)
        return OrderResult(
            accepted=True,
            filled=raw.get("status") == "closed",
            order_id=str(raw.get("id", order.id)),
            status=str(raw.get("status", "accepted")),
            message="Binance spot order submitted",
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        self._validate_config()
        return OrderResult(False, False, order_id, "not_sent", "cancel scaffolded")

    def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
        self._validate_config()
        return FlattenResult(
            accepted=False,
            status="failed",
            message="Binance flatten_all is not implemented yet",
            strategy=strategy,
            bps=bps,
            attempted=0,
            closed=0,
            failed=0,
        )
