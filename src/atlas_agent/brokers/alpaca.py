from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import ClassVar, List

from atlas_agent.config import AtlasConfig
from atlas_agent.brokers.base import BrokerConfigurationError, BrokerOperationError, BrokerProvider
from atlas_agent.brokers.models import (
    BrokerAccountState,
    BrokerBalance,
    BrokerOrder,
    BrokerPosition,
)
from atlas_agent.execution.order import AccountSnapshot, FlattenResult, Order, OrderResult
from atlas_agent.portfolio.positions import Position


@dataclass(frozen=True)
class AlpacaBroker:
    config: AtlasConfig
    paper_endpoint: str = "https://paper-api.alpaca.markets"
    live_endpoint: str = "https://api.alpaca.markets"

    _VALID_ORDER_TYPES = {"market", "limit"}
    _STATUS_ALLOWLIST = {
        "new",
        "partially_filled",
        "filled",
        "done_for_day",
        "canceled",
        "expired",
        "replaced",
        "pending_cancel",
        "pending_replace",
        "accepted",
        "pending_new",
        "accepted_for_bidding",
        "stopped",
        "rejected",
        "suspended",
        "calculated",
    }

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

    def place_order(
        self,
        order: Order,
        *,
        client_order_id: str | None = None,
    ) -> OrderResult:
        self._validate_config()

        # client_order_id is required for Alpaca submit
        if client_order_id is None:
            raise BrokerOperationError("client_order_id required")
        _validate_client_order_id(client_order_id)

        # Order validation
        if isinstance(order.quantity, bool) or not isinstance(order.quantity, (int, float)) or not math.isfinite(order.quantity) or order.quantity <= 0:
            raise BrokerOperationError("invalid order")
        if order.side not in ("buy", "sell"):
            raise BrokerOperationError("invalid order")
        if order.order_type not in self._VALID_ORDER_TYPES:
            raise BrokerOperationError("invalid order")
        if order.order_type == "limit":
            if order.limit_price is None or isinstance(order.limit_price, bool) or not isinstance(order.limit_price, (int, float)) or not math.isfinite(order.limit_price) or order.limit_price <= 0:
                raise BrokerOperationError("invalid order")

        endpoint = (
            self.live_endpoint
            if os.getenv("ALPACA_ENDPOINT_MODE", "paper").strip().lower() == "live"
            else self.paper_endpoint
        )
        payload: dict[str, object] = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.lower(),
            "type": order.order_type,
            "time_in_force": "day",
            "client_order_id": client_order_id,
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
        except TimeoutError:
            raise BrokerOperationError("broker transport request failed")
        except urllib.error.HTTPError as exc:
            code = getattr(exc, "code", 0)
            if code >= 500:
                raise BrokerOperationError("broker unavailable")
            raise BrokerOperationError("broker rejected order")
        except urllib.error.URLError:
            raise BrokerOperationError("broker transport request failed")
        except json.JSONDecodeError:
            raise BrokerOperationError("malformed broker response")

        if not isinstance(raw, dict):
            raise BrokerOperationError("malformed broker response")
        if "id" not in raw or "status" not in raw:
            raise BrokerOperationError("malformed broker response")
        status = raw.get("status")
        if not isinstance(status, str) or status not in self._STATUS_ALLOWLIST:
            raise BrokerOperationError("malformed broker response")
        resp_client_order_id = raw.get("client_order_id")
        if resp_client_order_id != client_order_id:
            raise BrokerOperationError("client_order_id mismatch")

        broker_order_id = str(raw["id"])
        if status == "rejected":
            return OrderResult(
                accepted=False,
                filled=False,
                order_id=broker_order_id,
                status="rejected",
                message="Alpaca order rejected",
                reasons=(),
            )
        return OrderResult(
            accepted=status in {"new", "partially_filled", "filled", "accepted", "pending_new", "accepted_for_bidding"},
            filled=status == "filled",
            order_id=broker_order_id,
            status=status,
            message="Alpaca order submitted",
            reasons=(),
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

    def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
        self._validate_config()
        return FlattenResult(
            accepted=False,
            status="failed",
            message="Alpaca flatten_all is not implemented yet",
            strategy=strategy,
            bps=bps,
            attempted=0,
            closed=0,
            failed=0,
        )


# ---------------------------------------------------------------------------
# Numeric validation helpers
# ---------------------------------------------------------------------------

def _require_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Alpaca returned invalid numeric value for {field_name}")
    v = float(value)  # type: ignore[arg-type]
    if not math.isfinite(v):
        raise ValueError(f"Alpaca returned invalid numeric value for {field_name}")
    return v


def _require_finite_non_negative(value: object, field_name: str) -> float:
    v = _require_finite(value, field_name)
    if v < 0:
        raise ValueError(f"Alpaca returned invalid numeric value for {field_name}")
    return v


def _require_finite_positive(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Alpaca returned invalid numeric value for {field_name}")
    v = float(value)  # type: ignore[arg-type]
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"Alpaca returned invalid numeric value for {field_name}")
    return v


# ---------------------------------------------------------------------------
# client_order_id validation helper
# ---------------------------------------------------------------------------

def _validate_client_order_id(client_order_id: str | None) -> None:
    if not isinstance(client_order_id, str) or not client_order_id:
        raise BrokerOperationError("invalid client_order_id")
    if len(client_order_id) > 64:
        raise BrokerOperationError("invalid client_order_id")
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", client_order_id):
        raise BrokerOperationError("invalid client_order_id")


# ---------------------------------------------------------------------------
# Alpaca read-only sync adapter
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AlpacaBrokerAdapter(BrokerProvider):
    """Read-only sync adapter for Alpaca Markets.

    Uses HTTP GET only. No order submission. No state mutation.
    All failures are sanitized through ``make_broker_error``.
    """

    config: AtlasConfig
    paper_endpoint: str = "https://paper-api.alpaca.markets"
    live_endpoint: str = "https://api.alpaca.markets"

    _ALPACA_STATUS_MAP: ClassVar[dict[str, str]] = {
        "new": "pending",
        "open": "open",
        "partially_filled": "partially_filled",
        "filled": "filled",
        "done_for_day": "open",
        "canceled": "cancelled",
        "expired": "cancelled",
        "replaced": "open",
        "pending_cancel": "open",
        "pending_replace": "open",
        "accepted": "pending",
        "pending_new": "pending",
        "accepted_for_bidding": "pending",
        "stopped": "open",
        "rejected": "rejected",
    }

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

    @property
    def _endpoint(self) -> str:
        mode = os.getenv("ALPACA_ENDPOINT_MODE", "paper").strip().lower()
        return self.live_endpoint if mode == "live" else self.paper_endpoint

    def _request(self, method: str, path: str) -> dict:
        """Make an HTTP request and return parsed JSON.

        Exceptions are left to bubble up so ``BrokerSyncService``
        can sanitize them via ``make_broker_error``.
        """
        url = f"{self._endpoint}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_account_state(self) -> BrokerAccountState:
        self._validate_config()
        raw = self._request("GET", "/v2/account")
        cash = _require_finite_non_negative(raw["cash"], "cash")
        equity = _require_finite_non_negative(raw["portfolio_value"], "portfolio_value")
        buying_power = _require_finite_non_negative(raw["buying_power"], "buying_power")
        mode = os.getenv("ALPACA_ENDPOINT_MODE", "paper").strip().lower()
        return BrokerAccountState(
            account_id="alpaca_live" if mode == "live" else "alpaca_paper",
            currency="USD",
            cash=cash,
            equity=equity,
            buying_power=buying_power,
            is_live=True,
        )

    def get_positions(self) -> List[BrokerPosition]:
        self._validate_config()
        raw_list = self._request("GET", "/v2/positions")
        if not isinstance(raw_list, list):
            raise ValueError("Alpaca positions response is not a list")
        positions: List[BrokerPosition] = []
        for raw in raw_list:
            qty = _require_finite(raw["qty"], "qty")
            avg_price = _require_finite_positive(raw["avg_entry_price"], "avg_entry_price")
            current_price = _require_finite_positive(raw["current_price"], "current_price")
            side: str = "long" if qty > 0 else "short" if qty < 0 else "flat"
            positions.append(
                BrokerPosition(
                    symbol=str(raw["symbol"]),
                    quantity=qty,
                    average_price=avg_price,
                    market_price=current_price,
                    side=side,  # type: ignore[arg-type]
                )
            )
        return positions

    def get_open_orders(self) -> List[BrokerOrder]:
        self._validate_config()
        raw_list = self._request("GET", "/v2/orders?status=open")
        if not isinstance(raw_list, list):
            raise ValueError("Alpaca orders response is not a list")
        orders: List[BrokerOrder] = []
        for raw in raw_list:
            qty = _require_finite_positive(raw["qty"], "qty")
            filled_qty = _require_finite_non_negative(raw.get("filled_qty", 0), "filled_qty")
            limit_price_raw = raw.get("limit_price")
            limit_price = (
                _require_finite_positive(limit_price_raw, "limit_price")
                if limit_price_raw is not None
                else None
            )
            orders.append(
                BrokerOrder(
                    order_id=str(raw["id"]),
                    symbol=str(raw["symbol"]),
                    side=str(raw["side"]).lower(),
                    quantity=qty,
                    limit_price=limit_price,
                    status="open",
                    filled_quantity=filled_qty,
                )
            )
        return orders

    def get_balances(self) -> List[BrokerBalance]:
        self._validate_config()
        # Alpaca does not have multi-asset balances.
        # Derive a single USD balance from the account state.
        account = self.get_account_state()
        return [
            BrokerBalance(
                asset="USD",
                free=account.cash,
                locked=0.0,
                total=account.cash,
            )
        ]

    @classmethod
    def _map_alpaca_status(cls, raw_status: str) -> str:
        mapped = cls._ALPACA_STATUS_MAP.get(raw_status)
        if mapped is None:
            raise BrokerOperationError("malformed broker response")
        return mapped

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder:
        """Fetch a single order by client_order_id. Raises BrokerOperationError on failure."""
        self._validate_config()
        _validate_client_order_id(client_order_id)

        import urllib.parse
        query = urllib.parse.urlencode({"client_order_id": client_order_id})
        try:
            raw = self._request("GET", f"/v2/orders:by_client_order_id?{query}")
        except TimeoutError:
            raise BrokerOperationError("broker transport request failed")
        except urllib.error.HTTPError as exc:
            code = getattr(exc, "code", 0)
            if code == 404:
                raise BrokerOperationError("order not found")
            if code >= 500:
                raise BrokerOperationError("broker unavailable")
            raise BrokerOperationError("broker rejected order")
        except urllib.error.URLError:
            raise BrokerOperationError("broker transport request failed")
        except json.JSONDecodeError:
            raise BrokerOperationError("malformed broker response")

        if not isinstance(raw, dict):
            raise BrokerOperationError("malformed broker response")
        required_fields = {"id", "symbol", "side", "qty", "status"}
        if not required_fields.issubset(raw.keys()):
            raise BrokerOperationError("malformed broker response")

        try:
            status = self._map_alpaca_status(str(raw["status"]))
            qty = _require_finite_positive(raw["qty"], "qty")
            filled_qty = _require_finite_non_negative(raw.get("filled_qty", 0), "filled_qty")
            limit_price_raw = raw.get("limit_price")
            limit_price = (
                _require_finite_positive(limit_price_raw, "limit_price")
                if limit_price_raw is not None
                else None
            )
            side = str(raw["side"]).lower()
            if side not in ("buy", "sell"):
                raise BrokerOperationError("malformed broker response")
            return BrokerOrder(
                order_id=str(raw["id"]),
                symbol=str(raw["symbol"]),
                side=side,  # type: ignore[arg-type]
                quantity=qty,
                limit_price=limit_price,
                status=status,  # type: ignore[arg-type]
                filled_quantity=filled_qty,
            )
        except BrokerOperationError:
            raise
        except Exception:
            raise BrokerOperationError("malformed broker response")
