from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.brokers.base import BrokerConfigurationError
from omni_trade_ai.execution.order import AccountSnapshot, Order, OrderResult
from omni_trade_ai.portfolio.positions import Position


@dataclass(frozen=True)
class AlpacaBroker:
    config: OmniTradeConfig
    paper_endpoint: str = "https://paper-api.alpaca.markets"
    live_endpoint: str = "https://api.alpaca.markets"

    def _validate_config(self) -> None:
        reasons = list(self.config.live_disabled_reasons())
        if self.config.live_broker != "alpaca":
            reasons.append("LIVE_BROKER must be alpaca")
        if not os.getenv("ALPACA_API_KEY"):
            reasons.append("ALPACA_API_KEY is missing")
        if not os.getenv("ALPACA_SECRET_KEY"):
            reasons.append("ALPACA_SECRET_KEY is missing")
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
        endpoint = (
            self.live_endpoint
            if os.getenv("ALPACA_ENDPOINT_MODE", "paper").strip().lower() == "live"
            else self.paper_endpoint
        )
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.lower(),
            "type": order.order_type,
            "time_in_force": "day",
        }
        if order.order_type == "limit":
            payload["limit_price"] = str(order.limit_price)
        request = urllib.request.Request(
            f"{endpoint}/v2/orders",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=order.id,
                status="failed",
                message="Alpaca order request failed",
                reasons=(exc.__class__.__name__,),
            )
        return OrderResult(
            accepted=True,
            filled=raw.get("status") == "filled",
            order_id=str(raw.get("id", order.id)),
            status=str(raw.get("status", "accepted")),
            message="Alpaca order submitted",
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        self._validate_config()
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order_id,
            status="not_sent",
            message="Alpaca cancel transport is scaffolded",
        )
