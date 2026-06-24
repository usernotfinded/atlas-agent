from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShadowLiveThresholdPolicy:
    """Divergence thresholds for shadow-live read-only comparison."""

    minor_cash_pct: float = 1.0
    major_cash_pct: float = 5.0
    minor_equity_pct: float = 1.0
    major_equity_pct: float = 5.0
    minor_position_qty_abs: float = 1.0
    major_position_qty_abs: float = 5.0
    minor_position_value_pct: float = 2.0
    major_position_value_pct: float = 10.0
    max_snapshot_age_seconds: float = 300.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "minor_cash_pct": self.minor_cash_pct,
            "major_cash_pct": self.major_cash_pct,
            "minor_equity_pct": self.minor_equity_pct,
            "major_equity_pct": self.major_equity_pct,
            "minor_position_qty_abs": self.minor_position_qty_abs,
            "major_position_qty_abs": self.major_position_qty_abs,
            "minor_position_value_pct": self.minor_position_value_pct,
            "major_position_value_pct": self.major_position_value_pct,
            "max_snapshot_age_seconds": self.max_snapshot_age_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShadowLiveThresholdPolicy:
        """Build a policy from a dictionary, ignoring unknown keys."""
        kwargs: dict[str, Any] = {}
        for name in cls.__dataclass_fields__:
            if name in data:
                kwargs[name] = float(data[name])
        return cls(**kwargs)


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    symbol: str
    quantity: float
    side: str
    average_price: float | None
    market_price: float | None
    market_value: float | None


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    filled_quantity: float
    limit_price: float | None
    status: str


@dataclass(frozen=True)
class BrokerFillSnapshot:
    fill_id: str
    order_id: str | None
    symbol: str
    side: str
    quantity: float
    price: float
    filled_at: str


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    schema_version: str
    account_label: str
    broker_source: str
    currency: str
    cash: float
    equity: float
    buying_power: float
    market_timestamp: str | None
    snapshot_freshness_timestamp: str
    positions: tuple[BrokerPositionSnapshot, ...]
    open_orders: tuple[BrokerOrderSnapshot, ...]
    recent_fills: tuple[BrokerFillSnapshot, ...]
    completeness_flags: dict[str, bool]


STATUSES = (
    "matched",
    "minor_divergence",
    "major_divergence",
    "stale_snapshot",
    "incomplete_snapshot",
    "blocked",
    "not_evaluated",
)


def _is_finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _parse_iso_timestamp(value: Any) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "timestamp is not a string"
    formats = (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt.endswith("Z"):
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed, None
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")), None
    except ValueError as exc:
        return None, f"invalid ISO timestamp: {exc}"


def load_broker_snapshot(path: str | Path) -> tuple[BrokerAccountSnapshot | None, list[str]]:
    """Load and strictly validate a local broker snapshot fixture."""
    p = Path(path)
    errors: list[str] = []
    if not p.is_file():
        return None, [f"broker snapshot file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return None, [f"failed to read broker snapshot: {exc}"]
    if not text.strip():
        return None, ["broker snapshot file is empty"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"broker snapshot is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["broker snapshot is not a JSON object"]

    required_top = (
        "schema_version",
        "account_label",
        "broker_source",
        "currency",
        "cash",
        "equity",
        "buying_power",
        "snapshot_freshness_timestamp",
        "completeness_flags",
    )
    for key in required_top:
        if key not in data:
            errors.append(f"missing required snapshot field: {key}")

    if data.get("schema_version") != "shadow-live-snapshot.v1":
        errors.append("broker snapshot schema_version mismatch")

    if errors:
        return None, errors

    numeric_fields = ("cash", "equity", "buying_power")
    for key in numeric_fields:
        if not _is_finite(data.get(key)):
            errors.append(f"{key} must be a finite number")
        elif float(data[key]) < 0:
            errors.append(f"{key} must be non-negative")

    positions: list[BrokerPositionSnapshot] = []
    for idx, raw in enumerate(data.get("positions", [])):
        if not isinstance(raw, dict):
            errors.append(f"position[{idx}] is not an object")
            continue
        for key in ("symbol", "quantity", "side"):
            if key not in raw:
                errors.append(f"position[{idx}] missing {key}")
        if not _is_finite(raw.get("quantity")):
            errors.append(f"position[{idx}] quantity must be finite")
        elif float(raw["quantity"]) < 0:
            errors.append(f"position[{idx}] quantity must be non-negative")
        if raw.get("side") not in ("long", "short"):
            errors.append(f"position[{idx}] side must be 'long' or 'short'")
        for key in ("average_price", "market_price", "market_value"):
            if raw.get(key) is not None and not _is_finite(raw.get(key)):
                errors.append(f"position[{idx}] {key} must be finite or null")
        positions.append(
            BrokerPositionSnapshot(
                symbol=str(raw.get("symbol", "")),
                quantity=float(raw.get("quantity", 0)),
                side=str(raw.get("side", "")),
                average_price=float(raw["average_price"]) if raw.get("average_price") is not None else None,
                market_price=float(raw["market_price"]) if raw.get("market_price") is not None else None,
                market_value=float(raw["market_value"]) if raw.get("market_value") is not None else None,
            )
        )

    open_orders: list[BrokerOrderSnapshot] = []
    for idx, raw in enumerate(data.get("open_orders", [])):
        if not isinstance(raw, dict):
            errors.append(f"open_order[{idx}] is not an object")
            continue
        for key in ("order_id", "symbol", "side", "order_type", "quantity", "filled_quantity", "status"):
            if key not in raw:
                errors.append(f"open_order[{idx}] missing {key}")
        if not _is_finite(raw.get("quantity")) or float(raw.get("quantity", -1)) < 0:
            errors.append(f"open_order[{idx}] quantity must be finite and non-negative")
        if not _is_finite(raw.get("filled_quantity")) or float(raw.get("filled_quantity", -1)) < 0:
            errors.append(f"open_order[{idx}] filled_quantity must be finite and non-negative")
        if raw.get("limit_price") is not None and (
            not _is_finite(raw.get("limit_price")) or float(raw["limit_price"]) <= 0
        ):
            errors.append(f"open_order[{idx}] limit_price must be finite and positive or null")
        open_orders.append(
            BrokerOrderSnapshot(
                order_id=str(raw.get("order_id", "")),
                symbol=str(raw.get("symbol", "")),
                side=str(raw.get("side", "")),
                order_type=str(raw.get("order_type", "")),
                quantity=float(raw.get("quantity", 0)),
                filled_quantity=float(raw.get("filled_quantity", 0)),
                limit_price=float(raw["limit_price"]) if raw.get("limit_price") is not None else None,
                status=str(raw.get("status", "")),
            )
        )

    recent_fills: list[BrokerFillSnapshot] = []
    for idx, raw in enumerate(data.get("recent_fills", [])):
        if not isinstance(raw, dict):
            errors.append(f"recent_fill[{idx}] is not an object")
            continue
        for key in ("fill_id", "symbol", "side", "quantity", "price", "filled_at"):
            if key not in raw:
                errors.append(f"recent_fill[{idx}] missing {key}")
        if not _is_finite(raw.get("quantity")) or float(raw.get("quantity", -1)) < 0:
            errors.append(f"recent_fill[{idx}] quantity must be finite and non-negative")
        if not _is_finite(raw.get("price")) or float(raw.get("price", -1)) <= 0:
            errors.append(f"recent_fill[{idx}] price must be finite and positive")
        _, fill_ts_err = _parse_iso_timestamp(raw.get("filled_at"))
        if fill_ts_err:
            errors.append(f"recent_fill[{idx}] filled_at: {fill_ts_err}")
        recent_fills.append(
            BrokerFillSnapshot(
                fill_id=str(raw.get("fill_id", "")),
                order_id=str(raw["order_id"]) if raw.get("order_id") is not None else None,
                symbol=str(raw.get("symbol", "")),
                side=str(raw.get("side", "")),
                quantity=float(raw.get("quantity", 0)),
                price=float(raw.get("price", 0)),
                filled_at=str(raw.get("filled_at", "")),
            )
        )

    completeness = data.get("completeness_flags", {})
    if not isinstance(completeness, dict):
        errors.append("completeness_flags must be an object")
        completeness = {}
    for key in ("account", "positions", "open_orders", "recent_fills", "market_prices"):
        if key not in completeness:
            errors.append(f"completeness_flags missing key: {key}")

    _, ts_err = _parse_iso_timestamp(data.get("snapshot_freshness_timestamp"))
    if ts_err:
        errors.append(f"snapshot_freshness_timestamp: {ts_err}")

    if data.get("market_timestamp") is not None:
        _, market_ts_err = _parse_iso_timestamp(data.get("market_timestamp"))
        if market_ts_err:
            errors.append(f"market_timestamp: {market_ts_err}")

    if errors:
        return None, errors

    return BrokerAccountSnapshot(
        schema_version=str(data["schema_version"]),
        account_label=str(data["account_label"]),
        broker_source=str(data["broker_source"]),
        currency=str(data["currency"]),
        cash=float(data["cash"]),
        equity=float(data["equity"]),
        buying_power=float(data["buying_power"]),
        market_timestamp=str(data["market_timestamp"]) if data.get("market_timestamp") is not None else None,
        snapshot_freshness_timestamp=str(data["snapshot_freshness_timestamp"]),
        positions=tuple(positions),
        open_orders=tuple(open_orders),
        recent_fills=tuple(recent_fills),
        completeness_flags={k: bool(v) for k, v in completeness.items()},
    ), errors


def load_quality_gate(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load a trading quality gate fixture."""
    p = Path(path)
    errors: list[str] = []
    if not p.is_file():
        return None, [f"quality gate file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return None, [f"failed to read quality gate: {exc}"]
    if not text.strip():
        return None, ["quality gate file is empty"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"quality gate is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["quality gate is not a JSON object"]
    if data.get("artifact_type") != "trading_quality_gate":
        errors.append("quality gate artifact_type mismatch")
    if data.get("schema_version") != "trading-quality-gate.v1":
        errors.append("quality gate schema_version mismatch")
    if data.get("mode") != "paper":
        errors.append("quality gate mode must be 'paper'")
    if "quality_state" not in data:
        errors.append("quality gate missing quality_state")
    if "metrics" not in data or not isinstance(data.get("metrics"), dict):
        errors.append("quality gate missing metrics object")
    if errors:
        return None, errors
    return data, errors


def _load_json(path: str | Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    p = Path(path)
    if not p.is_file():
        return None, [f"{label} file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return None, [f"failed to read {label} file: {exc}"]
    if not text.strip():
        return None, [f"{label} file is empty"]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"{label} is not valid JSON: {exc}"]
    if not isinstance(obj, dict):
        return None, [f"{label} is not a JSON object"]
    return obj, []


def _load_jsonl(path: str | Path, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    p = Path(path)
    if not p.is_file():
        return [], [f"{label} file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return [], [f"failed to read {label} file: {exc}"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} line {line_number}: invalid JSON ({exc})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{label} line {line_number}: not a JSON object")
            continue
        rows.append(obj)
    return rows, errors


def extract_paper_state(
    quality_gate: dict[str, Any],
    state_path: str | Path | None,
    metrics_path: str | Path | None,
    decisions_path: str | Path | None,
    fills_path: str | Path | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract paper-side state from the quality gate and optional override files."""
    errors: list[str] = []
    metrics = quality_gate.get("metrics", {})
    if metrics_path:
        loaded_metrics, m_errs = _load_json(metrics_path, "metrics")
        if loaded_metrics is None:
            errors.extend(m_errs)
        else:
            metrics = loaded_metrics

    state = None
    if state_path:
        state, s_errs = _load_json(state_path, "state")
        if state is None:
            errors.extend(s_errs)

    decisions: list[dict[str, Any]] = []
    if decisions_path:
        decisions, d_errs = _load_jsonl(decisions_path, "decisions")
        errors.extend(d_errs)

    fills: list[dict[str, Any]] = []
    if fills_path:
        fills, f_errs = _load_jsonl(fills_path, "fills")
        errors.extend(f_errs)

    paper_cash: float | None = None
    if state and _is_finite(state.get("cash")):
        paper_cash = float(state["cash"])
    elif _is_finite(metrics.get("ending_cash")):
        paper_cash = float(metrics["ending_cash"])

    paper_equity: float | None = None
    if state and _is_finite(state.get("equity")):
        paper_equity = float(state["equity"])
    elif _is_finite(metrics.get("ending_equity")):
        paper_equity = float(metrics["ending_equity"])

    paper_buying_power: float | None = None
    if state and _is_finite(state.get("buying_power")):
        paper_buying_power = float(state["buying_power"])

    paper_positions: list[dict[str, Any]] = []
    if state and isinstance(state.get("positions"), list):
        paper_positions = state["positions"]
    elif isinstance(metrics.get("positions"), list):
        paper_positions = metrics["positions"]

    paper_open_orders: list[dict[str, Any]] = []
    if state and isinstance(state.get("open_orders"), list):
        paper_open_orders = state["open_orders"]
    elif isinstance(metrics.get("open_orders"), list):
        paper_open_orders = metrics["open_orders"]

    return {
        "run_id": quality_gate.get("run_id"),
        "symbol": quality_gate.get("symbol"),
        "cash": paper_cash,
        "equity": paper_equity,
        "buying_power": paper_buying_power,
        "positions": paper_positions,
        "open_orders": paper_open_orders,
        "decisions": decisions,
        "fills": fills,
        "metrics": metrics,
    }, errors


def _to_position_snapshot(raw: dict[str, Any]) -> BrokerPositionSnapshot | None:
    if not isinstance(raw, dict):
        return None
    quantity = raw.get("quantity")
    side = raw.get("side")
    if not _is_finite(quantity) or side not in ("long", "short"):
        return None
    qty = float(quantity)
    return BrokerPositionSnapshot(
        symbol=str(raw.get("symbol", "")),
        quantity=qty,
        side=str(side),
        average_price=float(raw["average_price"]) if _is_finite(raw.get("average_price")) else None,
        market_price=float(raw["market_price"]) if _is_finite(raw.get("market_price")) else None,
        market_value=float(raw["market_value"]) if _is_finite(raw.get("market_value")) else None,
    )


def _signed_quantity(pos: BrokerPositionSnapshot | dict[str, Any]) -> float:
    if isinstance(pos, BrokerPositionSnapshot):
        return pos.quantity if pos.side == "long" else -pos.quantity
    qty = pos.get("quantity", 0)
    side = pos.get("side", "long")
    return float(qty) if side == "long" else -float(qty)


def _market_value(pos: BrokerPositionSnapshot | dict[str, Any]) -> float | None:
    if isinstance(pos, BrokerPositionSnapshot):
        return pos.market_value
    val = pos.get("market_value")
    return float(val) if _is_finite(val) else None


def _pct_diff(diff: float, broker_value: float | None, paper_value: float | None) -> float:
    denom = max(
        abs(broker_value) if broker_value is not None else 0.0,
        abs(paper_value) if paper_value is not None else 0.0,
        1.0,
    )
    return abs(diff) / denom * 100.0


def compare_paper_to_broker(
    paper_state: dict[str, Any],
    snapshot: BrokerAccountSnapshot,
    policy: ShadowLiveThresholdPolicy,
) -> dict[str, Any]:
    """Diff paper state against a broker snapshot."""
    paper_cash = paper_state.get("cash")
    paper_equity = paper_state.get("equity")
    paper_buying_power = paper_state.get("buying_power")

    cash_diff: float | None = None
    if _is_finite(paper_cash):
        cash_diff = float(paper_cash) - snapshot.cash

    equity_diff: float | None = None
    if _is_finite(paper_equity):
        equity_diff = float(paper_equity) - snapshot.equity

    buying_power_result: dict[str, Any]
    if _is_finite(paper_buying_power):
        buying_power_result = {
            "available": True,
            "paper_buying_power": float(paper_buying_power),
            "broker_buying_power": snapshot.buying_power,
            "difference": float(paper_buying_power) - snapshot.buying_power,
        }
    else:
        buying_power_result = {"available": False, "reason": "paper_buying_power_unavailable"}

    paper_positions = paper_state.get("positions", [])
    paper_pos_by_symbol: dict[str, BrokerPositionSnapshot | dict[str, Any]] = {}
    for raw in paper_positions:
        conv = _to_position_snapshot(raw)
        if conv is not None:
            paper_pos_by_symbol[conv.symbol] = conv
        elif isinstance(raw, dict) and raw.get("symbol"):
            paper_pos_by_symbol[str(raw["symbol"])] = raw

    broker_pos_by_symbol = {p.symbol: p for p in snapshot.positions}
    all_symbols = set(paper_pos_by_symbol) | set(broker_pos_by_symbol)
    position_differences: list[dict[str, Any]] = []
    for symbol in sorted(all_symbols):
        paper_pos = paper_pos_by_symbol.get(symbol)
        broker_pos = broker_pos_by_symbol.get(symbol)
        entry: dict[str, Any] = {"symbol": symbol}
        if paper_pos is None:
            entry["paper_only"] = False
            entry["broker_only"] = True
            entry["broker_quantity"] = broker_pos.quantity if broker_pos else None
            entry["broker_side"] = broker_pos.side if broker_pos else None
            entry["quantity_difference"] = -_signed_quantity(broker_pos) if broker_pos else None
            entry["market_value_difference"] = -(_market_value(broker_pos) or 0.0) if broker_pos else None
        elif broker_pos is None:
            entry["paper_only"] = True
            entry["broker_only"] = False
            entry["paper_quantity"] = (
                paper_pos.quantity if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("quantity")
            )
            entry["paper_side"] = (
                paper_pos.side if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("side")
            )
            entry["quantity_difference"] = _signed_quantity(paper_pos)
            entry["market_value_difference"] = _market_value(paper_pos) or 0.0
        else:
            entry["paper_only"] = False
            entry["broker_only"] = False
            entry["paper_quantity"] = (
                paper_pos.quantity if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("quantity")
            )
            entry["paper_side"] = (
                paper_pos.side if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("side")
            )
            entry["broker_quantity"] = broker_pos.quantity
            entry["broker_side"] = broker_pos.side
            entry["quantity_difference"] = _signed_quantity(paper_pos) - _signed_quantity(broker_pos)
            pmv = _market_value(paper_pos)
            bmv = _market_value(broker_pos)
            entry["paper_market_value"] = pmv
            entry["broker_market_value"] = bmv
            entry["market_value_difference"] = (pmv or 0.0) - (bmv or 0.0)
        position_differences.append(entry)

    open_order_result: dict[str, Any]
    if snapshot.completeness_flags.get("open_orders"):
        open_order_result = _compare_open_orders(paper_state.get("open_orders", []), snapshot.open_orders)
    else:
        open_order_result = {"available": False, "reason": "open_orders_incomplete"}

    fill_result: dict[str, Any]
    if snapshot.completeness_flags.get("recent_fills"):
        fill_result = _compare_fills(paper_state.get("fills", []), snapshot.recent_fills)
    else:
        fill_result = {"available": False, "reason": "recent_fills_incomplete"}

    return {
        "cash_difference": cash_diff,
        "equity_difference": equity_diff,
        "buying_power_difference": buying_power_result,
        "position_differences": position_differences,
        "open_order_differences": open_order_result,
        "fill_differences": fill_result,
        "missing_critical_fields": [],
        "stale_snapshot": False,
    }


def _compare_open_orders(
    paper_orders: list[Any], broker_orders: tuple[BrokerOrderSnapshot, ...]
) -> dict[str, Any]:
    broker_by_id = {o.order_id: o for o in broker_orders}
    differences: list[dict[str, Any]] = []
    paper_ids: set[str] = set()
    for raw in paper_orders:
        if not isinstance(raw, dict):
            continue
        order_id = raw.get("order_id") or f"paper-derived-{raw.get('symbol')}-{raw.get('side')}-{raw.get('quantity')}"
        paper_ids.add(order_id)
        broker_order = broker_by_id.get(order_id)
        if broker_order is None:
            differences.append({"order_id": order_id, "paper_only": True})
            continue
        diff: dict[str, Any] = {"order_id": order_id, "paper_only": False, "broker_only": False}
        for field in ("symbol", "side", "quantity", "filled_quantity", "limit_price", "status"):
            pv = raw.get(field)
            bv = getattr(broker_order, field)
            if pv != bv:
                diff[f"{field}_difference"] = {"paper": pv, "broker": bv}
        if len(diff) > 3:
            differences.append(diff)
    for order_id, broker_order in broker_by_id.items():
        if order_id not in paper_ids:
            differences.append({"order_id": order_id, "broker_only": True})
    return {"available": True, "differences": differences, "count": len(differences)}


def _compare_fills(paper_fills: list[Any], broker_fills: tuple[BrokerFillSnapshot, ...]) -> dict[str, Any]:
    broker_by_id = {f.fill_id: f for f in broker_fills}
    differences: list[dict[str, Any]] = []
    paper_ids: set[str] = set()
    for raw in paper_fills:
        if not isinstance(raw, dict):
            continue
        fill_id = raw.get("fill_id") or f"paper-derived-{raw.get('symbol')}-{raw.get('filled_at')}"
        paper_ids.add(fill_id)
        broker_fill = broker_by_id.get(fill_id)
        if broker_fill is None:
            differences.append({"fill_id": fill_id, "paper_only": True})
            continue
        diff: dict[str, Any] = {"fill_id": fill_id, "paper_only": False, "broker_only": False}
        for field in ("symbol", "side", "quantity", "price", "filled_at"):
            pv = raw.get(field)
            bv = getattr(broker_fill, field)
            if pv != bv:
                diff[f"{field}_difference"] = {"paper": pv, "broker": bv}
        if len(diff) > 3:
            differences.append(diff)
    for fill_id, broker_fill in broker_by_id.items():
        if fill_id not in paper_ids:
            differences.append({"fill_id": fill_id, "broker_only": True})
    return {"available": True, "differences": differences, "count": len(differences)}


def _is_snapshot_stale(
    snapshot: BrokerAccountSnapshot, policy: ShadowLiveThresholdPolicy, now: datetime | None = None
) -> bool:
    if now is None:
        now = datetime.now(timezone.utc)
    freshness, err = _parse_iso_timestamp(snapshot.snapshot_freshness_timestamp)
    if err or freshness is None:
        return True
    if freshness.tzinfo is None:
        freshness = freshness.replace(tzinfo=timezone.utc)
    age_seconds = (now - freshness).total_seconds()
    return age_seconds > policy.max_snapshot_age_seconds


def _missing_critical_fields(snapshot: BrokerAccountSnapshot) -> list[str]:
    missing: list[str] = []
    critical = ("account", "positions", "market_prices")
    for key in critical:
        if not snapshot.completeness_flags.get(key):
            missing.append(f"completeness_flags.{key}")
    for field in ("cash", "equity", "buying_power"):
        if not _is_finite(getattr(snapshot, field)):
            missing.append(f"account.{field}")
    return missing


def resolve_shadow_live_status(
    divergence: dict[str, Any],
    snapshot: BrokerAccountSnapshot,
    policy: ShadowLiveThresholdPolicy,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    """Resolve final shadow-live status using a fail-closed hierarchy."""
    blockers: list[str] = []
    missing = _missing_critical_fields(snapshot)
    if missing:
        blockers.extend(f"missing critical field: {m}" for m in missing)
        return "incomplete_snapshot", blockers

    if _is_snapshot_stale(snapshot, policy, now):
        blockers.append("snapshot exceeds max age")
        return "stale_snapshot", blockers

    if divergence.get("cash_difference") is not None:
        cash_pct = _pct_diff(divergence["cash_difference"], snapshot.cash, None)
        if cash_pct > policy.major_cash_pct:
            blockers.append(f"cash divergence {cash_pct:.2f}% exceeds major threshold")
            return "major_divergence", blockers
        if cash_pct > policy.minor_cash_pct:
            blockers.append(f"cash divergence {cash_pct:.2f}% exceeds minor threshold")

    if divergence.get("equity_difference") is not None:
        equity_pct = _pct_diff(divergence["equity_difference"], snapshot.equity, None)
        if equity_pct > policy.major_equity_pct:
            blockers.append(f"equity divergence {equity_pct:.2f}% exceeds major threshold")
            return "major_divergence", blockers
        if equity_pct > policy.minor_equity_pct:
            blockers.append(f"equity divergence {equity_pct:.2f}% exceeds minor threshold")

    has_minor = bool(blockers)
    for pos in divergence.get("position_differences", []):
        qd = pos.get("quantity_difference")
        if qd is not None:
            if abs(qd) > policy.major_position_qty_abs:
                blockers.append(f"position {pos['symbol']} quantity divergence exceeds major threshold")
                return "major_divergence", blockers
            if abs(qd) > policy.minor_position_qty_abs:
                blockers.append(f"position {pos['symbol']} quantity divergence exceeds minor threshold")
                has_minor = True
        mvd = pos.get("market_value_difference")
        if mvd is not None:
            mv_pct = _pct_diff(mvd, pos.get("broker_market_value"), pos.get("paper_market_value"))
            if mv_pct > policy.major_position_value_pct:
                blockers.append(f"position {pos['symbol']} market value divergence exceeds major threshold")
                return "major_divergence", blockers
            if mv_pct > policy.minor_position_value_pct:
                blockers.append(f"position {pos['symbol']} market value divergence exceeds minor threshold")
                has_minor = True

    if has_minor:
        return "minor_divergence", blockers
    return "matched", blockers


def _redact_path(path: Any) -> str:
    if path is None:
        return ""
    try:
        return Path(path).name
    except Exception:
        return str(path)


def build_shadow_live_comparison(
    quality_gate_path: str | Path,
    broker_snapshot_path: str | Path,
    output_dir: str | Path | None = None,
    state_path: str | Path | None = None,
    metrics_path: str | Path | None = None,
    decisions_path: str | Path | None = None,
    fills_path: str | Path | None = None,
    policy: ShadowLiveThresholdPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic shadow-live comparison report."""
    if policy is None:
        policy = ShadowLiveThresholdPolicy()

    gate, gate_errors = load_quality_gate(quality_gate_path)
    snapshot, snapshot_errors = load_broker_snapshot(broker_snapshot_path)

    input_artifacts: dict[str, Any] = {
        "quality_gate": _redact_path(quality_gate_path),
        "broker_snapshot": _redact_path(broker_snapshot_path),
    }
    if state_path:
        input_artifacts["state"] = _redact_path(state_path)
    if metrics_path:
        input_artifacts["metrics"] = _redact_path(metrics_path)
    if decisions_path:
        input_artifacts["decisions"] = _redact_path(decisions_path)
    if fills_path:
        input_artifacts["fills"] = _redact_path(fills_path)

    base_report: dict[str, Any] = {
        "artifact_type": "shadow_live_comparison",
        "schema_version": "shadow-live-comparison.v1",
        "run_id": gate.get("run_id") if gate else None,
        "symbol": gate.get("symbol") if gate else None,
        "quality_state": gate.get("quality_state") if gate else None,
        "status": "not_evaluated",
        "blockers": [],
        "broker_snapshot_summary": {},
        "freshness_assessment": {},
        "divergence_results": {},
        "missing_critical_fields": [],
        "threshold_policy": policy.to_dict(),
        "input_artifacts": input_artifacts,
        "disclaimer": "This is a read-only fixture comparison. It does not indicate live readiness, trading safety, profitability, or permission to submit orders.",
    }

    if gate is None:
        base_report["blockers"] = gate_errors
        base_report["status"] = "blocked"
        return base_report

    if gate.get("mode") != "paper":
        base_report["blockers"].append("quality gate mode is not 'paper'")
        base_report["status"] = "blocked"
        return base_report

    quality_state = gate.get("quality_state")
    if quality_state != "eligible_for_shadow_live_quality_review":
        base_report["blockers"].append(
            f"quality_state is '{quality_state}', required 'eligible_for_shadow_live_quality_review'"
        )
        base_report["status"] = "blocked" if quality_state not in ("not_evaluated",) else "not_evaluated"
        return base_report

    if snapshot is None:
        base_report["blockers"].extend(snapshot_errors)
        base_report["status"] = "blocked"
        return base_report

    paper_state, paper_errors = extract_paper_state(
        gate, state_path, metrics_path, decisions_path, fills_path
    )
    if paper_state is None:
        base_report["blockers"].extend(paper_errors)
        base_report["status"] = "blocked"
        return base_report
    base_report["blockers"].extend(paper_errors)

    if not _is_finite(paper_state.get("cash")) or not _is_finite(paper_state.get("equity")):
        base_report["blockers"].append("insufficient paper-side data for comparison")
        base_report["status"] = "not_evaluated"
        return base_report

    divergence = compare_paper_to_broker(paper_state, snapshot, policy)
    status, blockers = resolve_shadow_live_status(divergence, snapshot, policy, now)
    base_report["status"] = status
    base_report["blockers"].extend(blockers)
    base_report["divergence_results"] = divergence
    base_report["missing_critical_fields"] = _missing_critical_fields(snapshot)
    base_report["freshness_assessment"] = {
        "stale": _is_snapshot_stale(snapshot, policy, now),
        "snapshot_freshness_timestamp": snapshot.snapshot_freshness_timestamp,
    }
    base_report["broker_snapshot_summary"] = {
        "account_label": snapshot.account_label,
        "broker_source": snapshot.broker_source,
        "currency": snapshot.currency,
        "cash": snapshot.cash,
        "equity": snapshot.equity,
        "buying_power": snapshot.buying_power,
        "position_count": len(snapshot.positions),
        "open_order_count": len(snapshot.open_orders),
        "recent_fill_count": len(snapshot.recent_fills),
        "completeness_flags": snapshot.completeness_flags,
    }

    if output_dir:
        write_shadow_live_artifacts(base_report, output_dir)

    return base_report


def write_shadow_live_artifacts(report: dict[str, Any], output_dir: str | Path) -> None:
    """Write JSON and Markdown shadow-live artifacts with redacted paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "shadow-live-comparison.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = out / "shadow-live-report.md"
    lines: list[str] = []
    lines.append("# Shadow-Live Read-Only Comparison Report\n")
    lines.append(
        "> **This is a read-only fixture comparison.** It does not indicate live readiness, "
        "trading safety, profitability, or permission to submit orders.\n"
    )
    lines.append(f"**Status:** `{report['status']}`\n")
    lines.append(f"**Quality gate state:** `{report['quality_state']}`\n")
    lines.append(f"**Run ID:** {report.get('run_id') or 'N/A'}\n")
    lines.append(f"**Symbol:** {report.get('symbol') or 'N/A'}\n\n")

    lines.append("## Input artifacts\n")
    for key, value in sorted(report.get("input_artifacts", {}).items()):
        lines.append(f"- `{key}`: `{value}`\n")
    lines.append("\n")

    lines.append("## Broker snapshot summary\n")
    summary = report.get("broker_snapshot_summary", {})
    for key, value in sorted(summary.items()):
        if key == "completeness_flags":
            continue
        lines.append(f"- **{key}:** {value}\n")
    lines.append("\n")

    lines.append("## Freshness assessment\n")
    freshness = report.get("freshness_assessment", {})
    lines.append(f"- **Stale:** {freshness.get('stale', 'unknown')}\n")
    lines.append(f"- **Snapshot freshness timestamp:** {freshness.get('snapshot_freshness_timestamp', 'N/A')}\n\n")

    lines.append("## Divergence results\n")
    divergence = report.get("divergence_results", {})
    lines.append(f"- **Cash difference:** {divergence.get('cash_difference')}\n")
    lines.append(f"- **Equity difference:** {divergence.get('equity_difference')}\n")
    bp = divergence.get("buying_power_difference", {})
    if bp.get("available"):
        lines.append(f"- **Buying power difference:** {bp.get('difference')}\n")
    else:
        lines.append(f"- **Buying power difference:** unavailable ({bp.get('reason')})\n")
    lines.append("\n### Position differences\n")
    for pos in divergence.get("position_differences", []):
        lines.append(
            f"- `{pos['symbol']}`: qty_diff={pos.get('quantity_difference')}, "
            f"mv_diff={pos.get('market_value_difference')}, "
            f"paper_only={pos.get('paper_only')}, broker_only={pos.get('broker_only')}\n"
        )
    lines.append("\n")

    lines.append("## Missing critical fields\n")
    missing = report.get("missing_critical_fields", [])
    if missing:
        for field in missing:
            lines.append(f"- `{field}`\n")
    else:
        lines.append("- None\n")
    lines.append("\n")

    lines.append("## Blocked reasons\n")
    blockers = report.get("blockers", [])
    if blockers:
        for reason in blockers:
            lines.append(f"- {reason}\n")
    else:
        lines.append("- None\n")
    lines.append("\n")

    lines.append("## Disclaimer\n\n")
    lines.append(report.get("disclaimer", "") + "\n")

    md_path.write_text("".join(lines), encoding="utf-8")
