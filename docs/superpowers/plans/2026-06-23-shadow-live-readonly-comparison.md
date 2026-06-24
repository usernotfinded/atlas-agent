# CAND-005 Shadow-Live Read-Only Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strictly read-only, fixture-first shadow-live comparison layer that compares Atlas’s stateful paper / quality-gated hypothetical state against a recorded broker-like snapshot, producing deterministic JSON and Markdown artifacts.

**Architecture:** Single focused module `src/atlas_agent/agent/autonomous_paper_shadow_live.py` containing local snapshot dataclasses, loaders, comparison engine, status resolver, and artifact writers. CLI wiring in `src/atlas_agent/cli.py` adds `atlas agent shadow-live`. A contract checker in `scripts/check_shadow_live_readonly_contract.py` enforces safety boundaries. Tests, docs, demo, and release metadata complete the candidate.

**Tech Stack:** Python 3.11, `dataclasses`, `json`, `pathlib`, `datetime`, `pytest`, `argparse`.

---

## File structure

| File | Responsibility |
|---|---|
| `src/atlas_agent/agent/autonomous_paper_shadow_live.py` | Local snapshot models, loaders, comparison engine, status resolver, artifact writers. |
| `src/atlas_agent/cli.py` | Add `atlas agent shadow-live` subparser and handler. |
| `scripts/check_shadow_live_readonly_contract.py` | Static contract checker for CAND-005. |
| `tests/test_shadow_live_readonly.py` | Feature tests for snapshot loading, comparison, statuses, artifact writers, CLI. |
| `tests/test_shadow_live_readonly_contract.py` | Tests for the contract checker. |
| `scripts/demo_autonomous_paper_shadow_live.sh` | Deterministic demo: paper run → quality gate → snapshot fixture → shadow comparison. |
| `docs/shadow-live-readonly-comparison.md` | Main CAND-005 documentation. |
| `docs/shadow-live-readiness-contract.md` | Update to reflect CAND-005 implementation, CAND-006 future. |
| `docs/bounded-live-autonomy-governance.md` | Add CAND-005 stage. |
| `docs/autonomy-roadmap.md` | Mark CAND-005 implemented, CAND-006 future. |
| `docs/releases/v0.6.16-candidates.json` | Add CAND-005 entry. |
| `docs/releases/v0.6.16-candidates.md` | Add CAND-005 entry. |
| `docs/releases/v0.6.16-candidate-selection.md` | Add CAND-005 rationale. |
| `docs/releases/v0.6.16-plan.md` | Add CAND-005 to plan. |
| `CHANGELOG.md` | Add CAND-005 under `[Unreleased]`. |
| `scripts/dev_check.sh` | Wire shadow-live contract checker and tests. |
| `scripts/release_check.sh` | Wire shadow-live contract checker and tests. |
| `tests/fixtures/cli_command_contract.json` | Add `shadow-live` entry if the file checks CLI commands. |

---

## Task 1: Snapshot models and loader

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_shadow_live.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_shadow_live_readonly.py`:

```python
from atlas_agent.agent.autonomous_paper_shadow_live import (
    ShadowLiveThresholdPolicy,
    load_broker_snapshot,
)


def test_load_broker_snapshot_minimal(tmp_path):
    snapshot = {
        "schema_version": "shadow-live-snapshot.v1",
        "account_label": "paper-shadow-001",
        "broker_source": "fixture",
        "currency": "USD",
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": 20000.0,
        "market_timestamp": "2026-06-23T12:00:00Z",
        "snapshot_freshness_timestamp": "2026-06-23T12:05:00Z",
        "positions": [
            {"symbol": "AAPL", "quantity": 10, "side": "long", "average_price": 150.0, "market_price": 155.0, "market_value": 1550.0}
        ],
        "open_orders": [],
        "recent_fills": [],
        "completeness_flags": {
            "account": True,
            "positions": True,
            "open_orders": True,
            "recent_fills": True,
            "market_prices": True,
        },
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is not None
    assert not errors
    assert result.account_label == "paper-shadow-001"
    assert result.positions[0].quantity == 10
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_load_broker_snapshot_minimal -v
```

Expected: FAIL — module/file not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/atlas_agent/agent/autonomous_paper_shadow_live.py`:

```python
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShadowLiveThresholdPolicy:
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
        return cls(**{k: cls.__dataclass_fields__[k].type(data[k]) for k in cls.__dataclass_fields__ if k in data})


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
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc if fmt.endswith("Z") else None), None
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")), None
    except ValueError as exc:
        return None, f"invalid ISO timestamp: {exc}"


def load_broker_snapshot(path: str | Path) -> tuple[BrokerAccountSnapshot | None, list[str]]:
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

    required_top = ("schema_version", "account_label", "broker_source", "currency", "cash", "equity", "buying_power", "snapshot_freshness_timestamp", "completeness_flags")
    for key in required_top:
        if key not in data:
            errors.append(f"missing required snapshot field: {key}")

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
        positions.append(BrokerPositionSnapshot(
            symbol=str(raw.get("symbol", "")),
            quantity=float(raw.get("quantity", 0)),
            side=str(raw.get("side", "")),
            average_price=float(raw["average_price"]) if raw.get("average_price") is not None else None,
            market_price=float(raw["market_price"]) if raw.get("market_price") is not None else None,
            market_value=float(raw["market_value"]) if raw.get("market_value") is not None else None,
        ))

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
        if raw.get("limit_price") is not None and (not _is_finite(raw.get("limit_price")) or float(raw["limit_price"]) <= 0):
            errors.append(f"open_order[{idx}] limit_price must be finite and positive or null")
        open_orders.append(BrokerOrderSnapshot(
            order_id=str(raw.get("order_id", "")),
            symbol=str(raw.get("symbol", "")),
            side=str(raw.get("side", "")),
            order_type=str(raw.get("order_type", "")),
            quantity=float(raw.get("quantity", 0)),
            filled_quantity=float(raw.get("filled_quantity", 0)),
            limit_price=float(raw["limit_price"]) if raw.get("limit_price") is not None else None,
            status=str(raw.get("status", "")),
        ))

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
        recent_fills.append(BrokerFillSnapshot(
            fill_id=str(raw.get("fill_id", "")),
            order_id=str(raw["order_id"]) if raw.get("order_id") is not None else None,
            symbol=str(raw.get("symbol", "")),
            side=str(raw.get("side", "")),
            quantity=float(raw.get("quantity", 0)),
            price=float(raw.get("price", 0)),
            filled_at=str(raw.get("filled_at", "")),
        ))

    completeness = data.get("completeness_flags", {})
    if not isinstance(completeness, dict):
        errors.append("completeness_flags must be an object")
        completeness = {}
    for key in ("account", "positions", "open_orders", "recent_fills", "market_prices"):
        if key not in completeness:
            errors.append(f"completeness_flags missing key: {key}")

    if errors:
        return None, errors

    _, ts_err = _parse_iso_timestamp(data.get("snapshot_freshness_timestamp"))
    if ts_err:
        errors.append(f"snapshot_freshness_timestamp: {ts_err}")

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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_load_broker_snapshot_minimal -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_shadow_live.py tests/test_shadow_live_readonly.py
git commit -m "feat(cand-005): add broker snapshot models and loader"
```

---

## Task 2: Quality gate loader and paper state extraction

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_shadow_live.py`
- Test: `tests/test_shadow_live_readonly.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shadow_live_readonly.py`:

```python
def test_load_quality_gate_eligible(tmp_path):
    gate = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
        "dimensions": [],
        "metrics": {"ending_cash": 10000.0, "ending_equity": 10500.0, "number_of_fills": 2, "bars_processed": 50},
        "threshold_policy": {},
        "input_artifacts": {},
        "disclaimer": "...",
    }
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    result, errors = load_quality_gate(path)
    assert result is not None
    assert not errors
    assert result["quality_state"] == "eligible_for_shadow_live_quality_review"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_load_quality_gate_eligible -v
```

Expected: FAIL — `load_quality_gate` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `src/atlas_agent/agent/autonomous_paper_shadow_live.py`:

```python
def load_quality_gate(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
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
    if data.get("mode") != "paper":
        errors.append("quality gate mode must be 'paper'")
    if "quality_state" not in data:
        errors.append("quality gate missing quality_state")
    if "metrics" not in data or not isinstance(data.get("metrics"), dict):
        errors.append("quality gate missing metrics object")
    return data, errors


def extract_paper_state(
    quality_gate: dict[str, Any],
    state_path: str | Path | None,
    metrics_path: str | Path | None,
    decisions_path: str | Path | None,
    fills_path: str | Path | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    metrics = quality_gate.get("metrics", {})
    if metrics_path:
        metrics, m_errs = _load_json(metrics_path, "metrics")
        if metrics is None:
            errors.extend(m_errs)
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

    paper_cash = None
    if state and _is_finite(state.get("cash")):
        paper_cash = float(state["cash"])
    elif _is_finite(metrics.get("ending_cash")):
        paper_cash = float(metrics["ending_cash"])

    paper_equity = None
    if state and _is_finite(state.get("equity")):
        paper_equity = float(state["equity"])
    elif _is_finite(metrics.get("ending_equity")):
        paper_equity = float(metrics["ending_equity"])

    paper_buying_power = None
    if state and _is_finite(state.get("buying_power")):
        paper_buying_power = float(state["buying_power"])

    paper_positions: list[dict[str, Any]] = []
    if state and isinstance(state.get("positions"), list):
        paper_positions = state["positions"]
    elif isinstance(metrics.get("positions"), list):
        paper_positions = metrics["positions"]

    return {
        "run_id": quality_gate.get("run_id"),
        "symbol": quality_gate.get("symbol"),
        "cash": paper_cash,
        "equity": paper_equity,
        "buying_power": paper_buying_power,
        "positions": paper_positions,
        "decisions": decisions,
        "fills": fills,
        "metrics": metrics,
    }, errors


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
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_load_quality_gate_eligible -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_shadow_live.py tests/test_shadow_live_readonly.py
git commit -m "feat(cand-005): add quality gate loader and paper state extraction"
```

---

## Task 3: Comparison engine and status resolver

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_shadow_live.py`
- Test: `tests/test_shadow_live_readonly.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shadow_live_readonly.py`:

```python
from atlas_agent.agent.autonomous_paper_shadow_live import (
    compare_paper_to_broker,
    resolve_shadow_live_status,
)


def test_compare_matched():
    paper_state = {"cash": 10000.0, "equity": 10500.0, "buying_power": None, "positions": []}
    snapshot = BrokerAccountSnapshot(
        schema_version="shadow-live-snapshot.v1",
        account_label="paper-shadow-001",
        broker_source="fixture",
        currency="USD",
        cash=10000.0,
        equity=10500.0,
        buying_power=20000.0,
        market_timestamp="2026-06-23T12:00:00Z",
        snapshot_freshness_timestamp="2026-06-23T12:05:00Z",
        positions=(),
        open_orders=(),
        recent_fills=(),
        completeness_flags={"account": True, "positions": True, "open_orders": True, "recent_fills": True, "market_prices": True},
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    assert result["cash_difference"] == 0.0
    assert result["equity_difference"] == 0.0
    status, _ = resolve_shadow_live_status(result, snapshot, policy)
    assert status == "matched"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_compare_matched -v
```

Expected: FAIL — functions not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `src/atlas_agent/agent/autonomous_paper_shadow_live.py`:

```python
STATUSES = (
    "matched",
    "minor_divergence",
    "major_divergence",
    "stale_snapshot",
    "incomplete_snapshot",
    "blocked",
    "not_evaluated",
)


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
    denom = max(abs(broker_value) if broker_value is not None else 0, abs(paper_value) if paper_value is not None else 0, 1.0)
    return abs(diff) / denom * 100.0


def compare_paper_to_broker(
    paper_state: dict[str, Any],
    snapshot: BrokerAccountSnapshot,
    policy: ShadowLiveThresholdPolicy,
) -> dict[str, Any]:
    paper_cash = paper_state.get("cash")
    paper_equity = paper_state.get("equity")
    paper_buying_power = paper_state.get("buying_power")

    cash_diff = None
    if _is_finite(paper_cash):
        cash_diff = float(paper_cash) - snapshot.cash

    equity_diff = None
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
            entry["paper_quantity"] = paper_pos.quantity if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("quantity")
            entry["paper_side"] = paper_pos.side if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("side")
            entry["quantity_difference"] = _signed_quantity(paper_pos)
            entry["market_value_difference"] = _market_value(paper_pos) or 0.0
        else:
            entry["paper_only"] = False
            entry["broker_only"] = False
            entry["paper_quantity"] = paper_pos.quantity if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("quantity")
            entry["paper_side"] = paper_pos.side if isinstance(paper_pos, BrokerPositionSnapshot) else paper_pos.get("side")
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


def _compare_open_orders(paper_orders: list[Any], broker_orders: tuple[BrokerOrderSnapshot, ...]) -> dict[str, Any]:
    broker_by_id = {o.order_id: o for o in broker_orders}
    differences: list[dict[str, Any]] = []
    paper_ids = set()
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
    paper_ids = set()
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


def _is_snapshot_stale(snapshot: BrokerAccountSnapshot, policy: ShadowLiveThresholdPolicy, now: datetime | None = None) -> bool:
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
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py -v
```

Expected: focused tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_shadow_live.py tests/test_shadow_live_readonly.py
git commit -m "feat(cand-005): add comparison engine and status resolver"
```

---

## Task 4: Top-level builder and artifact writers

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_shadow_live.py`
- Test: `tests/test_shadow_live_readonly.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shadow_live_readonly.py`:

```python
def test_build_shadow_live_comparison_blocked_by_quality_gate(tmp_path):
    gate = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "blocked",
        "blockers": ["drawdown too high"],
        "dimensions": [],
        "metrics": {"ending_cash": 10000.0, "ending_equity": 10500.0},
        "threshold_policy": {},
        "input_artifacts": {},
        "disclaimer": "...",
    }
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps({"schema_version": "shadow-live-snapshot.v1", ...}))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
    )
    assert report["status"] == "blocked"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_build_shadow_live_comparison_blocked_by_quality_gate -v
```

Expected: FAIL — `build_shadow_live_comparison` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `src/atlas_agent/agent/autonomous_paper_shadow_live.py`:

```python
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
    if policy is None:
        policy = ShadowLiveThresholdPolicy()

    gate, gate_errors = load_quality_gate(quality_gate_path)
    snapshot, snapshot_errors = load_broker_snapshot(broker_snapshot_path)

    input_artifacts: dict[str, Any] = {
        "quality_gate": Path(quality_gate_path).name,
        "broker_snapshot": Path(broker_snapshot_path).name,
    }
    if state_path:
        input_artifacts["state"] = Path(state_path).name
    if metrics_path:
        input_artifacts["metrics"] = Path(metrics_path).name
    if decisions_path:
        input_artifacts["decisions"] = Path(decisions_path).name
    if fills_path:
        input_artifacts["fills"] = Path(fills_path).name

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
        base_report["blockers"].append(f"quality_state is '{quality_state}', required 'eligible_for_shadow_live_quality_review'")
        base_report["status"] = "blocked" if quality_state not in ("not_evaluated",) else "not_evaluated"
        return base_report

    if snapshot is None:
        base_report["blockers"].extend(snapshot_errors)
        base_report["status"] = "blocked"
        return base_report

    paper_state, paper_errors = extract_paper_state(gate, state_path, metrics_path, decisions_path, fills_path)
    if paper_state is None:
        base_report["blockers"].extend(paper_errors)
        base_report["status"] = "blocked"
        return base_report
    base_report["blockers"].extend(paper_errors)

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


def _redact_path(path: Any) -> str:
    if path is None:
        return ""
    try:
        return Path(path).name
    except Exception:
        return str(path)


def write_shadow_live_artifacts(report: dict[str, Any], output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "shadow-live-comparison.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = out / "shadow-live-report.md"
    lines: list[str] = []
    lines.append("# Shadow-Live Read-Only Comparison Report\n")
    lines.append("> **This is a read-only fixture comparison.** It does not indicate live readiness, "
                 "trading safety, profitability, or permission to submit orders.\n")
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
        lines.append(f"- `{pos['symbol']}`: qty_diff={pos.get('quantity_difference')}, mv_diff={pos.get('market_value_difference')}, paper_only={pos.get('paper_only')}, broker_only={pos.get('broker_only')}\n")
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
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_shadow_live.py tests/test_shadow_live_readonly.py
git commit -m "feat(cand-005): add shadow-live builder and artifact writers"
```

---

## Task 5: CLI wiring

**Files:**
- Modify: `src/atlas_agent/cli.py`
- Test: `tests/test_shadow_live_readonly.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shadow_live_readonly.py`:

```python
def test_cli_help_includes_readonly_disclaimer():
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "agent", "shadow-live", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "read-only fixture-first comparison" in result.stdout
    assert "does not submit orders or call broker APIs" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_cli_help_includes_readonly_disclaimer -v
```

Expected: FAIL — command not found.

- [ ] **Step 3: Write minimal implementation**

In `src/atlas_agent/cli.py`, find the `agent_sub.add_parser("autonomous-paper-quality", ...)` block and add immediately after it:

```python
    shadow_live_parser = agent_sub.add_parser(
        "shadow-live",
        help="read-only fixture-first comparison of paper state against a recorded broker snapshot",
        description=(
            "Read-only fixture-first comparison of Atlas paper state against a recorded broker snapshot. "
            "Does not submit orders or call broker APIs. Does not load credentials. "
            "Does not implement live trading or live readiness."
        ),
    )
    shadow_live_parser.add_argument("--quality-gate", required=True, help="path to trading-quality-gate.json")
    shadow_live_parser.add_argument("--broker-snapshot", required=True, help="path to local broker snapshot JSON fixture")
    shadow_live_parser.add_argument("--output-dir", required=True, help="directory for shadow-live artifacts")
    shadow_live_parser.add_argument("--state", default=None, help="optional persisted runner state JSON")
    shadow_live_parser.add_argument("--metrics", default=None, help="optional metrics JSON")
    shadow_live_parser.add_argument("--decisions", default=None, help="optional decisions jsonl")
    shadow_live_parser.add_argument("--fills", default=None, help="optional fills jsonl")
    shadow_live_parser.add_argument("--max-snapshot-age-seconds", type=float, default=300, help="max snapshot age in seconds")
    shadow_live_parser.add_argument("--json", action="store_true", help="print comparison JSON to stdout")
    shadow_live_parser.set_defaults(func=cmd_agent_shadow_live)
```

Add the handler function near the other agent command handlers:

```python
def cmd_agent_shadow_live(args: argparse.Namespace) -> int:
    from atlas_agent.agent.autonomous_paper_shadow_live import (
        ShadowLiveThresholdPolicy,
        build_shadow_live_comparison,
    )

    policy = ShadowLiveThresholdPolicy(max_snapshot_age_seconds=args.max_snapshot_age_seconds)
    report = build_shadow_live_comparison(
        quality_gate_path=args.quality_gate,
        broker_snapshot_path=args.broker_snapshot,
        output_dir=args.output_dir,
        state_path=args.state,
        metrics_path=args.metrics,
        decisions_path=args.decisions,
        fills_path=args.fills,
        policy=policy,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") in ("matched", "minor_divergence"):
        return 0
    return 2
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py::test_cli_help_includes_readonly_disclaimer -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/cli.py tests/test_shadow_live_readonly.py
git commit -m "feat(cand-005): add atlas agent shadow-live CLI"
```

---

## Task 6: Expand feature tests

**Files:**
- Modify: `tests/test_shadow_live_readonly.py`

- [ ] **Step 1: Add tests for all statuses and edge cases**

Add tests covering:
- `matched`
- `minor_divergence`
- `major_divergence`
- `stale_snapshot`
- `incomplete_snapshot`
- `blocked` from quality gate below threshold
- `not_evaluated` from missing quality gate
- malformed snapshot
- paper-only and broker-only positions
- open order divergence
- missing critical fields
- absolute path redaction
- input file mutation (hash unchanged)
- CLI rejects unknown flags like `--live`, `--submit`, `--api-key`

Example snippet:

```python
import hashlib
import subprocess
import sys


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_input_files_not_mutated(tmp_path):
    gate = _make_eligible_gate(tmp_path)
    snapshot = _make_snapshot(tmp_path)
    gate_path = tmp_path / "gate.json"
    snap_path = tmp_path / "snapshot.json"
    gate_path.write_text(json.dumps(gate))
    snap_path.write_text(json.dumps(snapshot))
    gate_hash = _file_hash(gate_path)
    snap_hash = _file_hash(snap_path)
    build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snap_path,
        output_dir=tmp_path / "out",
    )
    assert _file_hash(gate_path) == gate_hash
    assert _file_hash(snap_path) == snap_hash
```

- [ ] **Step 2: Run all feature tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_shadow_live_readonly.py
git commit -m "test(cand-005): expand shadow-live feature tests"
```

---

## Task 7: Contract checker

**Files:**
- Create: `scripts/check_shadow_live_readonly_contract.py`
- Create: `tests/test_shadow_live_readonly_contract.py`

- [ ] **Step 1: Write the failing contract test**

Create `tests/test_shadow_live_readonly_contract.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_contract_checker_runs():
    result = subprocess.run(
        [sys.executable, "scripts/check_shadow_live_readonly_contract.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly_contract.py::test_contract_checker_runs -v
```

Expected: FAIL — script not found.

- [ ] **Step 3: Write contract checker**

Create `scripts/check_shadow_live_readonly_contract.py` based on the CAND-004 checker pattern. Check:
- source exists (`src/atlas_agent/agent/autonomous_paper_shadow_live.py`)
- tests exist (`tests/test_shadow_live_readonly.py`, `tests/test_shadow_live_readonly_contract.py`)
- docs exist (`docs/shadow-live-readonly-comparison.md`, `docs/shadow-live-readiness-contract.md`, `docs/bounded-live-autonomy-governance.md`)
- CLI wiring (`"shadow-live"` in `src/atlas_agent/cli.py`)
- required statuses present in source
- required artifact names present (`shadow-live-comparison.json`, `shadow-live-report.md`)
- required disclaimers in doc and source
- forbidden imports/usages absent (`atlas_agent.brokers`, `atlas_agent.providers`, `place_order`, `cancel_order`, etc.)
- forbidden claims absent (`live-ready`, `profitable`, `guaranteed`, etc.)

- [ ] **Step 4: Run contract tests**

```bash
python3.11 -m pytest tests/test_shadow_live_readonly_contract.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_shadow_live_readonly_contract.py tests/test_shadow_live_readonly_contract.py
git commit -m "feat(cand-005): add shadow-live read-only contract checker"
```

---

## Task 8: Wire check scripts and CLI contract fixture

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/release_check.sh`
- Modify: `tests/fixtures/cli_command_contract.json` (if exists)

- [ ] **Step 1: Add shadow-live checks to dev_check.sh and release_check.sh**

In `scripts/dev_check.sh`, after the CAND-004 quality contract checks, add:

```bash
# CAND-005 shadow-live read-only contract
python3.11 scripts/check_shadow_live_readonly_contract.py || exit 1
python3.11 -m pytest tests/test_shadow_live_readonly.py -v || exit 1
python3.11 -m pytest tests/test_shadow_live_readonly_contract.py -v || exit 1
```

Mirror the same in `scripts/release_check.sh`.

- [ ] **Step 2: Update CLI fixture**

If `tests/fixtures/cli_command_contract.json` exists, add:

```json
{
  "command": "atlas agent shadow-live --help",
  "expected_in_stdout": ["read-only fixture-first comparison", "does not submit orders or call broker APIs"]
}
```

- [ ] **Step 3: Run dev_check.sh focused segment**

```bash
bash scripts/dev_check.sh
```

Expected: PASS (or at least shadow-live segment passes; fix unrelated pre-existing issues only if they block this work).

- [ ] **Step 4: Commit**

```bash
git add scripts/dev_check.sh scripts/release_check.sh tests/fixtures/cli_command_contract.json
git commit -m "feat(cand-005): wire shadow-live checker into dev and release checks"
```

---

## Task 9: Documentation

**Files:**
- Create: `docs/shadow-live-readonly-comparison.md`
- Modify: `docs/shadow-live-readiness-contract.md`
- Modify: `docs/bounded-live-autonomy-governance.md`
- Modify: `docs/autonomy-roadmap.md`
- Modify: `docs/autonomous-paper-quality-gate.md` (add cost_impact_pct approximation note)

- [ ] **Step 1: Write main CAND-005 doc**

Create `docs/shadow-live-readonly-comparison.md` covering:
- what it is / what it is not
- no live submit / no broker mutation / no credentials / no real broker API calls by default
- CLI usage
- snapshot schema
- completeness flags (critical vs optional)
- comparison statuses and thresholds
- quality gate integration
- output artifacts
- safety boundaries
- reviewer checklist

- [ ] **Step 2: Update related docs**

- `docs/shadow-live-readiness-contract.md`: mark CAND-005 implemented, CAND-006 future planning-only.
- `docs/bounded-live-autonomy-governance.md`: add CAND-005 read-only comparison stage.
- `docs/autonomy-roadmap.md`: mark CAND-005 implemented, CAND-006 future gated submit conformance rehearsal.
- `docs/autonomous-paper-quality-gate.md`: add note that `cost_impact_pct` is an approximation/proxy.

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs(cand-005): add shadow-live comparison docs and update governance"
```

---

## Task 10: Release metadata and CHANGELOG

**Files:**
- Modify: `docs/releases/v0.6.16-candidates.json`
- Modify: `docs/releases/v0.6.16-candidates.md`
- Modify: `docs/releases/v0.6.16-candidate-selection.md`
- Modify: `docs/releases/v0.6.16-plan.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update release candidate files**

Add CAND-005 entries consistently. Preserve v0.6.15 as current public release and v0.6.16 as planning-only.

- [ ] **Step 2: Update CHANGELOG**

Add under `[Unreleased]`:

```markdown
### Added
- CAND-005: Shadow-Live Read-Only Comparison fixture-first layer.
```

- [ ] **Step 3: Commit**

```bash
git add docs/releases/ CHANGELOG.md
git commit -m "docs(cand-005): add v0.6.16 release metadata and changelog entry"
```

---

## Task 11: Demo script

**Files:**
- Create: `scripts/demo_autonomous_paper_shadow_live.sh`

- [ ] **Step 1: Write demo script**

Create a deterministic bash demo that:
1. Runs a stateful paper loop (or reuses existing demo artifacts).
2. Runs CAND-004 quality gate.
3. Writes a local broker snapshot fixture with one matched field and one intentional divergence.
4. Runs `atlas agent shadow-live`.
5. Prints the final status and shows the Markdown report path.

Requires no credentials, no network, no broker API.

- [ ] **Step 2: Run demo**

```bash
bash scripts/demo_autonomous_paper_shadow_live.sh
```

Expected: exits 0 or 2 deterministically; shows matched field and intentional divergence.

- [ ] **Step 3: Commit**

```bash
git add scripts/demo_autonomous_paper_shadow_live.sh
git commit -m "demo(cand-005): add shadow-live read-only comparison demo"
```

---

## Task 12: Final verification

**Files:**
- All of the above

- [ ] **Step 1: Run verification commands**

```bash
git status
git diff --check
python3.11 -m compileall src
python3.11 -m pytest tests/test_shadow_live_readonly.py tests/test_shadow_live_readonly_contract.py -v
python3.11 scripts/check_shadow_live_readonly_contract.py
python3.11 scripts/check_autonomous_paper_loop_contract.py
python3.11 scripts/check_autonomous_paper_scorecard_contract.py
python3.11 scripts/check_autonomous_paper_quality_contract.py
python3.11 scripts/check_shadow_live_contract.py
# run any existing forbidden-claims checker
python3.11 -m pip check
atlas validate
atlas agent shadow-live --help
atlas run --mode paper  # should work
atlas run --mode live   # must remain fail-closed
bash scripts/release_check.sh --quick
```

- [ ] **Step 2: Fix any failures**

Iterate on code/tests/docs until all checks pass. Do not weaken checks.

- [ ] **Step 3: Final commit(s)**

```bash
git add ...
git commit -m "feat(cand-005): add shadow-live read-only comparison"
```

- [ ] **Step 4: Push (only if clean and checks pass)**

```bash
git status  # working tree clean
git push origin main
```

---

## Self-review checklist

- [ ] Spec coverage: every design section maps to at least one task.
- [ ] No placeholders: no TBD/TODO/"implement later"/"similar to Task N".
- [ ] Type consistency: `ShadowLiveThresholdPolicy`, `BrokerAccountSnapshot`, and function names match across tasks.
- [ ] Safety: no broker/provider/live imports in CAND-005 module.
- [ ] Fail-closed: missing/malformed inputs produce `blocked` or `not_evaluated`.
- [ ] Determinism: no wall-clock timestamps except from inputs; stable JSON sort keys.
