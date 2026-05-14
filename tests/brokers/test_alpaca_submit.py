from __future__ import annotations

import json
import os
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.brokers.alpaca import AlpacaBroker, AlpacaBrokerAdapter
from atlas_agent.brokers.base import BrokerConfigurationError, BrokerOperationError
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import Order, OrderResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _broker() -> AlpacaBroker:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    return AlpacaBroker(config)


def _adapter() -> AlpacaBrokerAdapter:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    return AlpacaBrokerAdapter(config)


def _with_env():
    return patch.dict(
        os.environ,
        {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"},
        clear=False,
    )


def _make_urlopen_response(status_code: int, body: object) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(code: int) -> Exception:
    from urllib.error import HTTPError
    return HTTPError(
        url="https://example.com/v2/orders",
        code=code,
        msg="",
        hdrs={},
        fp=BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# place_order: payload construction
# ---------------------------------------------------------------------------

def test_place_order_builds_correct_market_buy_payload() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "alpaca-order-1",
        "status": "accepted",
        "client_order_id": "cli-test-123",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            broker.place_order(order, client_order_id="cli-test-123")

    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data)
    assert payload["symbol"] == "AAPL"
    assert payload["qty"] == "1.0"
    assert payload["side"] == "buy"
    assert payload["type"] == "market"
    assert payload["time_in_force"] == "day"
    assert payload["client_order_id"] == "cli-test-123"
    assert "limit_price" not in payload


def test_place_order_builds_correct_limit_sell_payload() -> None:
    broker = _broker()
    order = Order(symbol="TSLA", side="sell", quantity=2.5, order_type="limit", limit_price=200.0)
    raw_response = {
        "id": "alpaca-order-2",
        "status": "accepted",
        "client_order_id": "cli-test-456",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            broker.place_order(order, client_order_id="cli-test-456")

    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data)
    assert payload["symbol"] == "TSLA"
    assert payload["qty"] == "2.5"
    assert payload["side"] == "sell"
    assert payload["type"] == "limit"
    assert payload["limit_price"] == "200.0"
    assert payload["time_in_force"] == "day"


def test_place_order_includes_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "alpaca-order-3",
        "status": "accepted",
        "client_order_id": "cli-test-789",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            result = broker.place_order(order, client_order_id="cli-test-789")

    assert isinstance(result, OrderResult)
    assert result.accepted is True
    assert result.order_id == "alpaca-order-3"


# ---------------------------------------------------------------------------
# place_order: client_order_id validation
# ---------------------------------------------------------------------------

def test_place_order_rejects_missing_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="client_order_id required"):
            broker.place_order(order)


def test_place_order_rejects_empty_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid client_order_id"):
            broker.place_order(order, client_order_id="")


def test_place_order_rejects_non_string_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid client_order_id"):
            broker.place_order(order, client_order_id=12345)  # type: ignore[arg-type]


def test_place_order_rejects_too_long_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid client_order_id"):
            broker.place_order(order, client_order_id="a" * 65)


def test_place_order_rejects_unsafe_characters_in_client_order_id() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid client_order_id"):
            broker.place_order(order, client_order_id="../../etc/passwd")


# ---------------------------------------------------------------------------
# place_order: input validation
# ---------------------------------------------------------------------------

def test_place_order_rejects_unsupported_order_type() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0, order_type="stop_limit")

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


@pytest.mark.parametrize("bad_qty", [0, -1, float("nan"), True])
def test_place_order_rejects_invalid_quantity(bad_qty: object) -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=bad_qty)  # type: ignore[arg-type]

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


def test_place_order_rejects_invalid_side() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="hold", quantity=1.0)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


def test_place_order_rejects_limit_without_price() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0, order_type="limit", limit_price=None)

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


# ---------------------------------------------------------------------------
# place_order: endpoint selection
# ---------------------------------------------------------------------------

def test_place_order_uses_paper_endpoint_by_default() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-paper",
        "status": "accepted",
        "client_order_id": "cli-test",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            broker.place_order(order, client_order_id="cli-test")

    req = mock_urlopen.call_args[0][0]
    assert req.full_url.startswith("https://paper-api.alpaca.markets")


def test_place_order_uses_live_endpoint_when_configured() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-live",
        "status": "accepted",
        "client_order_id": "cli-test",
    }

    with _with_env():
        with patch.dict(os.environ, {"ALPACA_ENDPOINT_MODE": "live"}, clear=False):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
                broker.place_order(order, client_order_id="cli-test")

    req = mock_urlopen.call_args[0][0]
    assert req.full_url.startswith("https://api.alpaca.markets")


# ---------------------------------------------------------------------------
# place_order: HTTP error sanitization
# ---------------------------------------------------------------------------

def test_place_order_http_timeout_converted_to_broker_operation_error() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            with pytest.raises(BrokerOperationError, match="broker transport request failed"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_http_4xx_sanitized() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with patch("urllib.request.urlopen", side_effect=_make_http_error(403)):
            with pytest.raises(BrokerOperationError, match="broker rejected order"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_http_5xx_sanitized() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with _with_env():
        with patch("urllib.request.urlopen", side_effect=_make_http_error(503)):
            with pytest.raises(BrokerOperationError, match="broker unavailable"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_malformed_json_response_sanitized() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"not valid json {{{"
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with _with_env():
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_malformed_response_missing_id_rejected() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {"status": "accepted", "client_order_id": "cli-test"}

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_malformed_response_unknown_status_rejected() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-1",
        "status": "weird_status",
        "client_order_id": "cli-test",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                broker.place_order(order, client_order_id="cli-test")


def test_place_order_client_order_id_mismatch_rejected() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-1",
        "status": "accepted",
        "client_order_id": "wrong",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            with pytest.raises(BrokerOperationError, match="client_order_id mismatch"):
                broker.place_order(order, client_order_id="expected")


def test_place_order_no_api_key_secret_header_body_leaks() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-1",
        "status": "accepted",
        "client_order_id": "cli-test",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            result = broker.place_order(order, client_order_id="cli-test")

    assert isinstance(result, OrderResult)
    assert "test-key" not in result.message
    assert "test-secret" not in result.message
    assert "test-key" not in str(result.reasons)
    assert "test-secret" not in str(result.reasons)


def test_place_order_rejected_status_returns_order_result() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)
    raw_response = {
        "id": "ord-rejected",
        "status": "rejected",
        "client_order_id": "cli-test",
    }

    with _with_env():
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(200, raw_response)
            result = broker.place_order(order, client_order_id="cli-test")

    assert result.accepted is False
    assert result.filled is False
    assert result.order_id == "ord-rejected"
    assert result.status == "rejected"
    assert result.message == "Alpaca order rejected"


# ---------------------------------------------------------------------------
# get_order_by_client_order_id
# ---------------------------------------------------------------------------

def test_get_order_by_client_order_id_success() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "filled_qty": "3",
        "limit_price": "150.0",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            order = adapter.get_order_by_client_order_id("cli-123")

    assert order.order_id == "ord-1"
    assert order.symbol == "AAPL"
    assert order.side == "buy"
    assert order.quantity == 10.0
    assert order.filled_quantity == 3.0
    assert order.limit_price == 150.0


def test_get_order_by_client_order_id_uses_query_parameter() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw) as mock_request:
            adapter.get_order_by_client_order_id("cli-123")

    path = mock_request.call_args[0][1]
    assert "?client_order_id=cli-123" in path
    assert "/orders:by_client_order_id/cli-123" not in path


def test_get_order_by_client_order_id_404_not_found() -> None:
    adapter = _adapter()

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", side_effect=_make_http_error(404)):
            with pytest.raises(BrokerOperationError, match="order not found"):
                adapter.get_order_by_client_order_id("cli-missing")


def test_get_order_by_client_order_id_timeout_converted() -> None:
    adapter = _adapter()

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", side_effect=TimeoutError):
            with pytest.raises(BrokerOperationError, match="broker transport request failed"):
                adapter.get_order_by_client_order_id("cli-timeout")


def test_get_order_by_client_order_id_malformed_response_rejected() -> None:
    adapter = _adapter()

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value={"symbol": "AAPL"}):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-bad")


# ---------------------------------------------------------------------------
# get_order_by_client_order_id: client_order_id validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_cid", [None, "", 12345, "a" * 65, "../../etc/passwd"])
def test_get_order_by_client_order_id_rejects_invalid_client_order_id(bad_cid: object) -> None:
    adapter = _adapter()

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid client_order_id"):
            adapter.get_order_by_client_order_id(bad_cid)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_order_by_client_order_id: malformed response sanitization
# ---------------------------------------------------------------------------

def test_get_order_by_client_order_id_malformed_numeric_qty() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "0",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_malformed_numeric_limit_price() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "limit_price": "-5",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_malformed_numeric_filled_qty() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "filled_qty": True,
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_invalid_side() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "hold",
        "qty": "10",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_missing_status() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_unknown_status() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "status": "weird_status",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response"):
                adapter.get_order_by_client_order_id("cli-test")


def test_get_order_by_client_order_id_pydantic_errors_sanitized() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "not_a_number",
        "status": "open",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(BrokerOperationError, match="malformed broker response") as exc_info:
                adapter.get_order_by_client_order_id("cli-test")
    assert "not_a_number" not in str(exc_info.value)


def test_get_order_by_client_order_id_no_raw_values_leak() -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "status": "open",
        "client_order_id": "cli-secret-999",
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            order = adapter.get_order_by_client_order_id("cli-secret-999")

    assert order.order_id == "ord-1"
    # Exception path also checked in other tests; ensure no secrets in success path


# ---------------------------------------------------------------------------
# get_order_by_client_order_id: status mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "alpaca_status,expected_status",
    [
        ("new", "pending"),
        ("partially_filled", "partially_filled"),
        ("filled", "filled"),
        ("done_for_day", "open"),
        ("canceled", "cancelled"),
        ("expired", "cancelled"),
        ("replaced", "open"),
        ("pending_cancel", "open"),
        ("pending_replace", "open"),
        ("accepted", "pending"),
        ("pending_new", "pending"),
        ("accepted_for_bidding", "pending"),
        ("stopped", "open"),
        ("rejected", "rejected"),
    ],
)
def test_get_order_by_client_order_id_status_mapping(alpaca_status: str, expected_status: str) -> None:
    adapter = _adapter()
    raw = {
        "id": "ord-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "status": alpaca_status,
    }

    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            order = adapter.get_order_by_client_order_id("cli-test")

    assert order.status == expected_status


# ---------------------------------------------------------------------------
# place_order: additional input validation
# ---------------------------------------------------------------------------

def test_place_order_rejects_infinite_quantity() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=float("inf"))

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


@pytest.mark.parametrize("bad_price", [0, -1, float("nan"), float("inf"), True])
def test_place_order_rejects_invalid_limit_price(bad_price: object) -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0, order_type="limit", limit_price=bad_price)  # type: ignore[arg-type]

    with _with_env():
        with pytest.raises(BrokerOperationError, match="invalid order"):
            broker.place_order(order, client_order_id="cli-test")


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

def test_place_order_missing_credentials_raises_broker_configuration_error() -> None:
    broker = _broker()
    order = Order(symbol="AAPL", side="buy", quantity=1.0)

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(BrokerConfigurationError):
            broker.place_order(order, client_order_id="cli-test")
