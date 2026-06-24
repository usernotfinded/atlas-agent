# CAND-003 Stateful Autonomous Paper Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen the CAND-001 contract checker and add an execution-neutral, stateful autonomous paper-trading kernel to Atlas that reuses existing backtest/risk/audit models, persists portfolio state across invocations, resumes from the last processed bar, prevents duplicate processing, and produces honest trading metrics — while preserving all safety boundaries (no live trading, no providers, no broker calls, no credentials, no shadow-live, no live-submit).

**Architecture:**
- `src/atlas_agent/agent/autonomous_paper_kernel.py` exposes a pure, execution-neutral cycle: load checkpoint → read next market-data bar(s) → build strategy context → generate proposed orders → evaluate each order through `RiskManager` in paper mode → simulate fills with next-bar timing and configurable costs via existing `ExecutionSimulator` → update a reusable portfolio state → write decisions/fills/metrics/checkpoint.
- `src/atlas_agent/agent/autonomous_paper_runner.py` wraps the kernel with persistence: it loads/saves `StatefulPaperState`, advances a cursor, deduplicates bars, processes all orders sequentially, and handles no-new-data deterministically.
- `src/atlas_agent/agent/autonomous_paper.py` keeps its existing public API and is extended with a `stateful=` path that delegates to the runner; existing non-stateful calls remain backward-compatible.
- Existing models are reused: `BacktestConfig`, `MarketBar`, `BacktestOrder`, `BacktestFill`, `BacktestPosition`, `ExecutionSimulator`, `StrategyContext`, `StrategyRegistry`, `MetricsCalculator`, `RiskManager`, `RiskLimits`, `PortfolioSnapshot`, `OrderRiskInput`, `PortfolioState`, `Position`, `AuditWriter`, `KillSwitchController`.
- CLI: extend `atlas agent autonomous-paper` with `--state-dir`, `--resume`, `--initial-cash`, `--commission-bps`, `--slippage-bps` (defaults preserve existing behavior).
- Artifacts are redacted/portable: paths and raw exceptions are sanitized before persistence.

**Tech Stack:** Python 3.11, Pydantic v2, dataclasses, pytest, existing Atlas backtest/risk/audit modules.

---

## Task 1: Strengthen CAND-001 Contract Checker

**Files:**
- Modify: `scripts/check_autonomous_paper_loop_contract.py`
- Modify: `tests/test_autonomous_paper_loop_contract.py`
- Reference: `scripts/check_autonomous_paper_scorecard_contract.py`

**Goal:** Add AST/source checks that reject forbidden runtime imports/usages in `src/atlas_agent/agent/autonomous_paper.py`, mirroring the CAND-002 scorecard checker. Do not weaken existing phrase/doc checks.

Forbidden to detect in `autonomous_paper.py`:
- `atlas_agent.brokers` (any import/reference)
- `atlas_agent.providers` (any import/reference)
- `atlas_agent.execution.live` (any import/reference)
- `atlas_agent.research.provider_` and `get_research_provider`
- broker resolver usage: `BrokerResolver(`, `.resolve_execution_broker(`, `.resolve_sync_provider(`, `.resolve_status(`
- broker guards: `guard_submit(`, `guard_sync(`
- broker state-changing calls: `.place_order(`, `.cancel_order(`, `.flatten_all(`
- order router/submit: `OrderRouter(`, `.route(`, `run_submit_execution(`, `run_submit_dry_run(`, `mark_submit_*`, `compute_client_order_id(`
- credential loading: `load_atlas_secrets(`, `get_secret(`, `get_secret_status(`, `set_secret(`, `os.getenv/os.environ` reads matching API-key/secret/token/password patterns
- live-side-effect strings: `live_trading_enabled=True`, `paper_only=False`, `can_submit`, `broker.submit`, `provider.execute`, `broker.execute`, `provider.submit`

Also add:
- `_check_cli_wiring`: assert `src/atlas_agent/cli.py` contains `'"autonomous-paper"'`.
- `_check_test_file`: assert `tests/test_autonomous_paper_loop.py` exists.

- [ ] **Step 1: Add source constants and helper to CAND-001 checker**

Add at the top of `scripts/check_autonomous_paper_loop_contract.py`:

```python
AUTONOMOUS_PAPER_MODULE = REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper.py"
CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_autonomous_paper_loop.py"

FORBIDDEN_MODULE_IMPORTS = (
    "atlas_agent.brokers",
    "atlas_agent.providers",
    "atlas_agent.execution.live",
    "atlas_agent.research.provider_",
    "get_research_provider",
)

FORBIDDEN_BROKER_PATTERNS = (
    "BrokerResolver(",
    ".resolve_execution_broker(",
    ".resolve_sync_provider(",
    ".resolve_status(",
    "guard_submit(",
    "guard_sync(",
)

FORBIDDEN_SUBMISSION_PATTERNS = (
    ".place_order(",
    ".cancel_order(",
    ".flatten_all(",
    "broker.submit",
    "broker.submit_order",
    "OrderRouter(",
    ".route(",
    "run_submit_execution(",
    "run_submit_dry_run(",
    "mark_submit_requested(",
    "mark_acknowledged(",
    "mark_submit_failed(",
    "mark_submit_uncertain(",
    "compute_client_order_id(",
)

FORBIDDEN_PROVIDER_CALL_PATTERNS = (
    "provider.execute",
    "provider.submit",
    "provider.complete(",
    "provider.generate(",
)

FORBIDDEN_CREDENTIAL_PATTERNS = (
    "load_atlas_secrets(",
    "get_secret(",
    "get_secret_status(",
    "set_secret(",
)

FORBIDDEN_LIVE_FLAG_PATTERNS = (
    "live_trading_enabled=True",
    "paper_only=False",
    "can_submit",
)

CREDENTIAL_ENV_REGEX = re.compile(
    r"os\.(?:getenv|environ)\s*\[?\s*\(?\s*['\"][^'\"]*(?:ALPACA|BINANCE|CCXT|EXCHANGE|API_KEY|SECRET_KEY|SECRET|TOKEN|PASSWORD)"
)
```

Add to `REQUIRED_FILES`: `AUTONOMOUS_PAPER_MODULE`, `CLI_MODULE`, `TEST_MODULE`.

- [ ] **Step 2: Implement source/import checks**

Add functions:

```python
def _check_module_safety() -> list[str]:
    errors: list[str] = []
    if not AUTONOMOUS_PAPER_MODULE.exists():
        return errors
    text = _read(AUTONOMOUS_PAPER_MODULE)
    rel = AUTONOMOUS_PAPER_MODULE.relative_to(REPO_ROOT)
    for forbidden in FORBIDDEN_MODULE_IMPORTS:
        if forbidden in text:
            errors.append(f"[{rel}] Forbidden import/reference: {forbidden}")
    for group_name, patterns in [
        ("broker resolver/guard", FORBIDDEN_BROKER_PATTERNS),
        ("order submission/cancel/flatten", FORBIDDEN_SUBMISSION_PATTERNS),
        ("provider execution call", FORBIDDEN_PROVIDER_CALL_PATTERNS),
        ("credential loader", FORBIDDEN_CREDENTIAL_PATTERNS),
        ("live flag", FORBIDDEN_LIVE_FLAG_PATTERNS),
    ]:
        for pattern in patterns:
            if pattern in text:
                errors.append(f"[{rel}] Forbidden {group_name} usage: {pattern}")
    if CREDENTIAL_ENV_REGEX.search(text):
        errors.append(f"[{rel}] Forbidden credential environment access")
    return errors


def _check_cli_wiring() -> list[str]:
    errors: list[str] = []
    if not CLI_MODULE.exists():
        return errors
    text = _read(CLI_MODULE)
    if '"autonomous-paper"' not in text:
        errors.append("[src/atlas_agent/cli.py] Missing 'autonomous-paper' subparser registration")
    return errors
```

Wire into `check_all()` after existing checks.

- [ ] **Step 3: Add regression tests for the strengthened checker**

In `tests/test_autonomous_paper_loop_contract.py` add tests:

```python
def test_checker_fails_on_forbidden_import(tmp_path):
    checker = tmp_path / "check_autonomous_paper_loop_contract.py"
    original = Path("scripts/check_autonomous_paper_loop_contract.py").read_text()
    checker.write_text(original)
    module = tmp_path / "src" / "atlas_agent" / "agent" / "autonomous_paper.py"
    module.parent.mkdir(parents=True)
    module.write_text("import atlas_agent.brokers\n")
    result = subprocess.run(
        [sys.executable, str(checker), "--json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert not data["passed"]
    assert any("atlas_agent.brokers" in e for e in data["errors"])


def test_checker_fails_on_place_order(tmp_path):
    ...


def test_checker_fails_on_live_trading_enabled_true(tmp_path):
    ...


def test_checker_fails_on_credential_env_access(tmp_path):
    ...
```

- [ ] **Step 4: Run checker and its tests**

```bash
python3.11 scripts/check_autonomous_paper_loop_contract.py --json
pytest tests/test_autonomous_paper_loop_contract.py -v
```

Expected: checker passes on real repo; new regression tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_autonomous_paper_loop_contract.py tests/test_autonomous_paper_loop_contract.py
git commit -m "test: harden autonomous paper loop contract checker"
```

---

## Task 2: Define CAND-003 State and Configuration Models

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_models.py`

**Goal:** Add portable, serializable models for the stateful paper runner. Keep them independent of broker/provider/live execution.

- [ ] **Step 1: Create models file**

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from atlas_agent.backtest.models import BacktestFill, BacktestOrder, BacktestPosition


class StatefulPaperConfig(BaseModel):
    run_id: str
    symbol: str
    strategy_id: str
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    data_path: str
    output_dir: str
    state_dir: str
    initial_cash: float = 10_000.0
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    max_orders_per_cycle: int = 10


class StatefulPaperCursor(BaseModel):
    last_processed_bar_index: int = -1
    last_processed_bar_timestamp: str | None = None
    processed_bar_hashes: list[str] = Field(default_factory=list)


class StatefulPaperState(BaseModel):
    run_id: str
    symbol: str
    strategy_id: str
    data_path: str
    cash: float
    positions: dict[str, BacktestPosition]
    cursor: StatefulPaperCursor
    fill_history: list[BacktestFill]
    decision_refs: list[dict[str, Any]]
    metrics_history: list[dict[str, Any]]
    created_at: str
    updated_at: str
    status: Literal["active", "completed", "failed"] = "active"
    errors: list[str] = Field(default_factory=list)


class StatefulPaperMetrics(BaseModel):
    starting_cash: float
    ending_cash: float
    ending_equity: float
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    total_return_pct: float
    max_drawdown_pct: float
    number_of_trades: int
    number_of_fills: int
    number_of_rejections: int
    turnover: float | None = None
    gross_exposure: float
    net_exposure: float
    total_commission: float
    total_slippage: float
    bars_processed: int
    data_source_redacted: str
    generated_at: str
    notes: list[str] = Field(default_factory=list)


class StatefulPaperResult(BaseModel):
    run_id: str
    status: Literal["completed", "failed", "blocked", "no_new_data"]
    bars_processed_this_run: int
    total_bars_processed: int
    decisions_path: str
    fills_path: str
    metrics_path: str
    checkpoint_path: str
    manifest_path: str
    audit_log_path: str
    metrics: StatefulPaperMetrics | None = None
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Add tiny tests for model serialization**

Create `tests/test_autonomous_paper_models.py`:

```python
from atlas_agent.agent.autonomous_paper_models import StatefulPaperState, StatefulPaperCursor


def test_state_serializes_round_trip():
    state = StatefulPaperState(
        run_id="run-1",
        symbol="DEMO",
        strategy_id="buy_and_hold",
        data_path="data/sample/ohlcv.csv",
        cash=10000.0,
        positions={},
        cursor=StatefulPaperCursor(last_processed_bar_index=2),
        fill_history=[],
        decision_refs=[],
        metrics_history=[],
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    data = state.model_dump(mode="json")
    restored = StatefulPaperState.model_validate(data)
    assert restored.cursor.last_processed_bar_index == 2
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_autonomous_paper_models.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_models.py tests/test_autonomous_paper_models.py
git commit -m "feat(cand-003): add stateful paper runner models"
```

---

## Task 3: Implement the Execution-Neutral Autonomous Trading Kernel

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_kernel.py`
- Modify: `src/atlas_agent/agent/autonomous_paper.py` (import helper)

**Goal:** Implement a reusable kernel that performs one deterministic cycle per bar without knowing about real broker submission.

- [ ] **Step 1: Implement kernel functions**

Key functions:

```python
def build_strategy_context(
    *,
    run_id: str,
    symbol: str,
    bar_index: int,
    cash: float,
    positions: dict[str, BacktestPosition],
    pending_orders: list[BacktestOrder],
    config: BacktestConfig,
) -> StrategyContext:
    return StrategyContext(...)


def build_portfolio_snapshot(
    *,
    cash: float,
    positions: dict[str, BacktestPosition],
    pending_orders: list[BacktestOrder],
    current_price: float,
) -> PortfolioSnapshot:
    # Reuse/adapt existing _build_portfolio_snapshot from autonomous_paper.py
    ...


def apply_fill(
    *,
    fill: BacktestFill,
    cash: float,
    positions: dict[str, BacktestPosition],
) -> tuple[float, dict[str, BacktestPosition]]:
    # Reuse/adapt existing _apply_fill from autonomous_paper.py
    ...


def run_kernel_cycle(
    *,
    bar: MarketBar,
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
) -> KernelCycleResult:
    """Execute one execution-neutral cycle.

    Returns decision record, updated cash/positions, and audit event ids.
    Processes all generated orders sequentially; any order blocked by risk does
    not update portfolio; earlier fills affect later order risk snapshots.
    """
    ...
```

`KernelCycleResult` is a dataclass/Pydantic model containing:
- `decision: AutonomousDecision`
- `cash: float`
- `positions: dict[str, BacktestPosition]`
- `fills: list[BacktestFill]`
- `rejected_orders: list[BacktestOrder]`
- `audit_event_ids: list[str]`

Implementation notes:
- Generate orders with `strategy.generate_orders(bars=bars_so_far, context=context)`.
- If no orders, return `decision_state="no_trade"`.
- For each order, build fresh `PortfolioSnapshot`, call `risk_manager.evaluate_order(..., mode="paper")`.
- If allowed, simulate fill with `executor.process_order(order, bar)`. If fill returned, apply it and emit `autonomous_paper_fill` audit event.
- If blocked, emit nothing and record rejection.
- Always emit `autonomous_paper_decision`.
- Do not import or call anything from `atlas_agent.brokers`, `atlas_agent.providers`, or `atlas_agent.execution.live`.

- [ ] **Step 2: Add kernel unit tests**

Create `tests/test_autonomous_paper_kernel.py`:

```python
def test_kernel_no_trade_when_strategy_returns_no_orders():
    ...


def test_kernel_processes_all_orders_sequentially():
    ...


def test_kernel_risk_blocked_order_does_not_change_portfolio():
    ...


def test_kernel_fill_updates_cash_and_position():
    ...
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_autonomous_paper_kernel.py -v
python3.11 -m compileall src/atlas_agent/agent/autonomous_paper_kernel.py
```

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_kernel.py tests/test_autonomous_paper_kernel.py
git commit -m "feat(cand-003): add execution-neutral autonomous paper kernel"
```

---

## Task 4: Implement the Stateful Paper Runner

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_runner.py`
- Modify: `src/atlas_agent/agent/autonomous_paper.py`

**Goal:** Add persistence, resume, duplicate-prevention, and no-new-data handling on top of the kernel.

- [ ] **Step 1: Implement state loading/saving helpers**

```python
def _state_path(state_dir: str | Path, run_id: str) -> Path:
    return Path(state_dir) / f"{run_id}-state.json"


def _checkpoint_path(state_dir: str | Path, run_id: str) -> Path:
    return Path(state_dir) / f"{run_id}-checkpoint.json"


def load_state_or_initialize(
    *,
    state_dir: str | Path,
    run_id: str,
    config: StatefulPaperConfig,
    resume: bool = False,
) -> StatefulPaperState:
    state_path = _state_path(state_dir, run_id)
    if state_path.exists() and resume:
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return StatefulPaperState.model_validate(data)
        except Exception as exc:
            raise ValueError(f"malformed_state: {type(exc).__name__}") from None
    return _initialize_state(config)


def save_state(state: StatefulPaperState, state_dir: str | Path) -> Path:
    state_path = _state_path(state_dir, state.run_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return state_path
```

- [ ] **Step 2: Implement runner main function**

```python
def run_stateful_autonomous_paper(
    *,
    config: StatefulPaperConfig,
    atlas_config: AtlasConfig,
    resume: bool = False,
    max_cycles: int = 0,
    audit_writer: AuditWriter | None = None,
    event_logger: EventLogger | None = None,
    kill_switch=None,
) -> StatefulPaperResult:
    """Run a stateful paper loop, resuming from the last processed bar.

    If no new bars are available, returns `status="no_new_data"` without
    modifying state. Duplicate bars (by index and hash) are skipped.
    """
    ...
```

Key behaviors:
- Load market data with `load_market_data(config.data_path, symbol=config.symbol)`.
- Load or initialize `StatefulPaperState`.
- Validate state consistency (run_id, symbol, strategy_id, data_path match).
- Determine start index = `state.cursor.last_processed_bar_index + 1`.
- Determine end index based on `max_cycles` or all remaining bars.
- For each new bar:
  - Check kill switch; if enabled, fail closed (`status="blocked"`).
  - Compute bar hash (e.g., SHA-256 of canonical bar JSON) and skip if already in `processed_bar_hashes`.
  - Run `run_kernel_cycle(...)`.
  - Update state cash/positions/cursor/fill_history/decision_refs.
  - Write decision to `decisions.jsonl`.
  - Write fill to `fills.jsonl` if any.
- After loop, compute metrics and write `metrics.json`.
- Save state and checkpoint.
- Write manifest.
- Return `StatefulPaperResult`.

- [ ] **Step 3: Wire into autonomous_paper.py**

Add a new public function `run_stateful_autonomous_paper_loop(...)` in `src/atlas_agent/agent/autonomous_paper.py` that:
- Builds a `StatefulPaperConfig` from AtlasConfig + CLI args.
- Calls `run_stateful_autonomous_paper(...)`.
- Adapts result to an `AutonomousPaperResult`-like response or returns the new result directly.

Keep `run_autonomous_paper_loop` unchanged for backward compatibility.

- [ ] **Step 4: Add runner tests**

Create `tests/test_autonomous_paper_runner.py`:

```python
def test_runner_initializes_state_on_first_run(tmp_path):
    ...


def test_runner_resumes_from_cursor(tmp_path):
    ...


def test_runner_does_not_reprocess_duplicate_bars(tmp_path):
    ...


def test_runner_returns_no_new_data_cleanly(tmp_path):
    ...


def test_runner_malformed_state_fails_closed(tmp_path):
    ...


def test_runner_corrupt_checkpoint_fails_closed(tmp_path):
    ...
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_autonomous_paper_runner.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_runner.py tests/test_autonomous_paper_runner.py src/atlas_agent/agent/autonomous_paper.py
git commit -m "feat(cand-003): add stateful autonomous paper runner"
```

---

## Task 5: Add Execution Realism (Next-Bar Fills, Costs, Slippage)

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_kernel.py`
- Modify: `src/atlas_agent/agent/autonomous_paper_runner.py`
- Modify: `src/atlas_agent/backtest/execution.py` if needed

**Goal:** Avoid same-bar look-ahead. Use next-bar fill semantics or a clearly documented deterministic fill timing model. Apply nonzero configurable commission and slippage defaults that are conservative.

- [ ] **Step 1: Add fill timing option**

In `StatefulPaperConfig` add:

```python
fill_timing: Literal["same_bar", "next_bar"] = "next_bar"
```

- [ ] **Step 2: Implement next-bar fill in runner**

In the runner, when an order is allowed by risk on bar `i`, do not immediately simulate a fill. Instead:
- Record the order as pending.
- On bar `i+1`, process pending orders from the previous bar using bar `i+1`'s prices.
- If `fill_timing == "same_bar"`, preserve existing behavior for backward compatibility.

Document the model clearly: "Orders generated at bar `i` are evaluated against risk using bar `i` close and, if allowed, filled at bar `i+1` open (or close) with slippage/commission applied. This avoids same-bar look-ahead."

- [ ] **Step 3: Default conservative costs**

Set defaults in `StatefulPaperConfig`:

```python
commission_bps: float = 1.0  # 1 bp
slippage_bps: float = 1.0    # 1 bp
```

Ensure `ExecutionSimulator` already applies these; if not, extend it to handle `slippage_bps` and `commission_bps` from config.

- [ ] **Step 4: Add cost/slippage tests**

```python
def test_next_bar_fill_avoids_same_bar_lookahead():
    ...


def test_commission_reduces_ending_cash():
    ...


def test_slippage_changes_fill_price():
    ...
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_autonomous_paper_kernel.py tests/test_autonomous_paper_runner.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_kernel.py src/atlas_agent/agent/autonomous_paper_runner.py src/atlas_agent/backtest/execution.py tests/test_autonomous_paper_kernel.py tests/test_autonomous_paper_runner.py
git commit -m "feat(cand-003): deterministic next-bar fills with configurable costs"
```

---

## Task 6: Implement Trading Metrics

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_runner.py`
- Create: `src/atlas_agent/agent/autonomous_paper_metrics.py`

**Goal:** Produce honest trading metrics, reusing existing `MetricsCalculator` where possible.

- [ ] **Step 1: Create metrics calculator**

```python
def calculate_stateful_paper_metrics(
    *,
    starting_cash: float,
    cash: float,
    positions: dict[str, BacktestPosition],
    fill_history: list[BacktestFill],
    bars_processed: int,
    current_price: float,
    data_source: str,
) -> StatefulPaperMetrics:
    ending_equity = cash + sum(
        pos.quantity * current_price for pos in positions.values()
    )
    # Build equity curve from fills + starting cash if full history not stored
    # Build TradeRecord list from fills
    # Use MetricsCalculator for total_return_pct, max_drawdown_pct, etc.
    # Compute turnover if feasible, else omit with note
    # Compute realized_pnl from sell fills if feasible
    # unrealized_pnl = (current_price - avg_entry) * qty for long positions
    ...
```

Honesty rules:
- If a metric cannot be computed accurately, set it to `None` and add a note.
- `realized_pnl` only computed when sell-side fills provide enough info.
- `turnover` computed as sum of notional traded / average equity if feasible; otherwise `None` with note.

- [ ] **Step 2: Integrate metrics into runner**

After processing bars, call `calculate_stateful_paper_metrics` and write `metrics.json`.

- [ ] **Step 3: Add metrics tests**

```python
def test_metrics_include_drawdown_and_return():
    ...


def test_metrics_omit_uncomputable_with_note():
    ...
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_autonomous_paper_metrics.py tests/test_autonomous_paper_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_metrics.py src/atlas_agent/agent/autonomous_paper_runner.py tests/test_autonomous_paper_metrics.py
git commit -m "feat(cand-003): honest trading metrics for stateful paper runner"
```

---

## Task 7: Audit, Evidence, and Redaction

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_runner.py`
- Modify: `src/atlas_agent/agent/autonomous_paper.py`
- Modify: `scripts/build_release_evidence_bundle.py` if needed

**Goal:** Ensure new artifacts are portable and redacted.

- [ ] **Step 1: Sanitize paths and exceptions**

Add helpers in runner:

```python
def _redact_data_source(path: str) -> str:
    """Return a portable representation of the data source."""
    p = Path(path)
    return f"<repo>/{p.name}"


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: error details redacted"
```

Use `_safe_error` when writing state errors or audit final status. Do not put `str(exc)` directly into JSON/audit.

- [ ] **Step 2: Redact all persisted payloads**

Use `redact_payload(...)` from `atlas_agent.audit.redaction` before writing decisions, fills, metrics, manifest, and state.

- [ ] **Step 3: Ensure state file is portable**

Store data source as basename or redacted path, not absolute path. If absolute path is needed for runtime, store it separately and redact it in exported artifacts.

- [ ] **Step 4: Add redaction tests**

```python
def test_state_does_not_leak_home_directory(tmp_path):
    ...


def test_error_messages_are_redacted(tmp_path):
    ...
```

- [ ] **Step 5: Fix release evidence portability if needed**

If `scripts/build_release_evidence_bundle.py` still leaks temp paths, extend `_redact()` to cover `/var/folders/`, `/private/var/`, `/tmp/`, `/Users/`. (Baseline already noted this.)

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_autonomous_paper_redaction.py -v
python3.11 scripts/build_release_evidence_bundle.py --skip-slow
```

- [ ] **Step 7: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_runner.py src/atlas_agent/agent/autonomous_paper.py scripts/build_release_evidence_bundle.py tests/test_autonomous_paper_redaction.py
git commit -m "feat(cand-003): redact and portable stateful paper artifacts"
```

---

## Task 8: Extend CLI for Stateful Autonomous Paper

**Files:**
- Modify: `src/atlas_agent/cli.py`
- Modify: `tests/fixtures/cli_command_contract.json`
- Modify: `tests/test_cli_command_compatibility.py` if needed
- Modify: `docs/cli-command-compatibility.md`

**Goal:** Add stateful options to `atlas agent autonomous-paper` without breaking existing behavior.

- [ ] **Step 1: Add CLI arguments**

In `src/atlas_agent/cli.py` around the `autonomous-paper` parser (lines 827–851), add:

```python
ap.add_argument(
    "--state-dir",
    default=None,
    help="Directory to persist stateful paper runner state/checkpoint.",
)
ap.add_argument(
    "--resume",
    action="store_true",
    help="Resume from existing state in --state-dir if present.",
)
ap.add_argument(
    "--initial-cash",
    type=float,
    default=None,
    help="Initial cash for stateful paper runner (default from config).",
)
ap.add_argument(
    "--commission-bps",
    type=float,
    default=None,
    help="Commission in basis points for simulated fills.",
)
ap.add_argument(
    "--slippage-bps",
    type=float,
    default=None,
    help="Slippage in basis points for simulated fills.",
)
ap.add_argument(
    "--fill-timing",
    choices=["same_bar", "next_bar"],
    default="next_bar",
    help="Deterministic fill timing model.",
)
```

- [ ] **Step 2: Update handler**

In the `autonomous-paper` handler (lines 5898–5936), branch:

```python
if getattr(args, "state_dir", None):
    from atlas_agent.agent.autonomous_paper import run_stateful_autonomous_paper_loop
    result = run_stateful_autonomous_paper_loop(
        config=config,
        symbol=args.symbol,
        strategy_id=args.strategy,
        data_path=args.data_path,
        max_cycles=args.max_cycles,
        state_dir=args.state_dir,
        resume=args.resume,
        initial_cash=args.initial_cash,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        fill_timing=args.fill_timing,
        json_output=args.json,
    )
else:
    # existing non-stateful path
    ...
```

- [ ] **Step 3: Update CLI contract**

Add new options to `tests/fixtures/cli_command_contract.json` under `subcommands.agent.autonomous-paper.options` if the contract tracks options; otherwise just ensure the subcommand remains listed.

- [ ] **Step 4: Add CLI tests**

```python
def test_autonomous_paper_stateful_cli_runs(tmp_path):
    ...


def test_autonomous_paper_stateful_resume(tmp_path):
    ...
```

- [ ] **Step 5: Update docs**

Add `autonomous-paper` stateful options to `docs/cli-command-compatibility.md` stable list.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_cli_command_compatibility.py -v
python3.11 scripts/check_cli_command_compatibility.py
```

- [ ] **Step 7: Commit**

```bash
git add src/atlas_agent/cli.py tests/fixtures/cli_command_contract.json tests/test_cli_command_compatibility.py docs/cli-command-compatibility.md tests/cli/test_autonomous_paper_stateful_cli.py
git commit -m "feat(cand-003): extend CLI for stateful autonomous paper"
```

---

## Task 9: Comprehensive Tests

**Files:**
- Create/Modify: `tests/test_autonomous_paper_*.py`

**Goal:** Cover all required behaviors with deterministic local-only tests.

Required tests:
1. Checker catches forbidden CAND-001 imports/usages.
2. State persists across invocations.
3. Second invocation resumes from cursor.
4. Duplicate bars are not reprocessed.
5. No-new-data exits cleanly.
6. All generated orders processed deterministically.
7. Risk-blocked order does not update portfolio.
8. Paper fill updates cash/position.
9. Cost/slippage changes fill/equity outcome.
10. Max drawdown/equity metrics produced.
11. Kill switch blocks new trading cycle.
12. Malformed state fails closed.
13. Corrupted checkpoint fails closed.
14. Artifacts are redacted/portable.
15. No broker/provider/live execution import is reachable.

- [ ] **Step 1: Create or extend test files**

Use existing `_make_config` pattern from `tests/test_autonomous_paper_loop.py`. Reuse `data/sample/ohlcv.csv`.

- [ ] **Step 2: Run focused tests**

```bash
pytest tests/test_autonomous_paper_loop.py tests/test_autonomous_paper_loop_contract.py tests/test_autonomous_paper_kernel.py tests/test_autonomous_paper_runner.py tests/test_autonomous_paper_metrics.py tests/test_autonomous_paper_redaction.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_autonomous_paper_*.py
git commit -m "test(cand-003): add comprehensive stateful paper runner tests"
```

---

## Task 10: Documentation and Candidate Metadata

**Files:**
- Modify: `docs/autonomous-paper-loop.md`
- Modify: `docs/releases/v0.6.16-candidates.md`
- Modify: `docs/releases/v0.6.16-candidates.json`
- Modify: `docs/releases/v0.6.16-plan.md`
- Modify: `docs/releases/v0.6.16-candidate-selection.md`
- Modify: `docs/bounded-live-autonomy-governance.md`
- Modify: `docs/autonomy-roadmap.md`
- Modify: `CHANGELOG.md`

**Goal:** Document CAND-003 accurately as stateful execution-neutral paper capability; preserve all safety disclaimers.

- [ ] **Step 1: Update autonomous-paper-loop.md**

Add a section "Stateful execution-neutral kernel (CAND-003)" that explains:
- New `--state-dir`, `--resume`, cost options.
- Execution-neutral kernel design.
- Next-bar fill semantics and configurable costs.
- Metrics produced.
- Reiterate: paper-only, no live trading, no broker submission, no provider calls, not shadow-live, not live-ready.

- [ ] **Step 2: Add CAND-003 to v0.6.16 candidate docs**

In JSON:

```json
{
  "id": "CAND-003",
  "status": "implemented",
  "title": "Execution-Neutral Autonomous Trading Kernel and Stateful Paper Runner",
  "description": "Adds a reusable execution-neutral trading kernel and a stateful paper runner that persists portfolio state, resumes from the last bar, prevents duplicate processing, and produces honest trading metrics. Remains paper-only; no live trading, no broker submission, no provider calls.",
  "notes": [
    "Does not implement shadow-live.",
    "Does not implement live submit.",
    "Does not load credentials or call real brokers/providers."
  ]
}
```

Mirror in Markdown files.

- [ ] **Step 3: Update CHANGELOG**

Under `## [Unreleased]`:

```markdown
### Added
- CAND-003: execution-neutral autonomous trading kernel and stateful paper runner with resume, duplicate-prevention, next-bar fills, configurable costs, and honest trading metrics.

### Safety
- CAND-003 remains paper-only and does not enable live trading, shadow-live, broker submission, provider execution, or credential loading.
```

- [ ] **Step 4: Commit**

```bash
git add docs/autonomous-paper-loop.md docs/releases/v0.6.16-candidates.json docs/releases/v0.6.16-candidates.md docs/releases/v0.6.16-plan.md docs/releases/v0.6.16-candidate-selection.md docs/bounded-live-autonomy-governance.md docs/autonomy-roadmap.md CHANGELOG.md
git commit -m "docs(cand-003): document stateful execution-neutral paper kernel"
```

---

## Task 11: Demo Script

**Files:**
- Create/Modify: `scripts/demo_autonomous_paper_stateful.sh` or `examples/paper_trading_demo/stateful_paper_demo.py`

**Goal:** Demonstrate real capability: stateful resume, at least one fill, at least one hold, at least one risk rejection, equity/cost metrics, redacted artifacts.

- [ ] **Step 1: Create deterministic demo**

The demo should:
1. Create a temp working directory.
2. Run `atlas agent autonomous-paper --state-dir <dir> --symbol DEMO --strategy buy_and_hold --data-path data/sample/ohlcv.csv --max-cycles 3 --commission-bps 1 --slippage-bps 1`.
3. Run again with `--resume` to show cursor advance.
4. Inspect `metrics.json` for fill, hold, rejection counts and cost summary.
5. Assert artifacts contain no home directory paths.
6. Print a concise summary.

Use a strategy that triggers a fill (e.g., `buy_and_hold`) and a risk limit that triggers a rejection (e.g., tiny `max_single_trade_notional`).

- [ ] **Step 2: Add demo test**

```python
def test_stateful_paper_demo_succeeds():
    subprocess.run(["bash", "scripts/demo_autonomous_paper_stateful.sh"], check=True)
```

- [ ] **Step 3: Run demo**

```bash
bash scripts/demo_autonomous_paper_stateful.sh
```

- [ ] **Step 4: Commit**

```bash
git add scripts/demo_autonomous_paper_stateful.sh tests/test_autonomous_paper_stateful_demo.py
git commit -m "demo(cand-003): add stateful autonomous paper demo"
```

---

## Task 12: Verification Gate

**Files:**
- All changed files

**Goal:** Run the strongest feasible validation before declaring success or pushing.

- [ ] **Step 1: Static checks**

```bash
git status
git diff --check
python3.11 -m compileall src
```

- [ ] **Step 2: Run focused CAND tests**

```bash
pytest tests/test_autonomous_paper_loop.py tests/test_autonomous_paper_loop_contract.py tests/test_autonomous_paper_scorecard.py tests/test_autonomous_paper_scorecard_contract.py tests/test_autonomous_paper_kernel.py tests/test_autonomous_paper_runner.py tests/test_autonomous_paper_metrics.py tests/test_autonomous_paper_redaction.py -v
```

- [ ] **Step 3: Run checkers**

```bash
python3.11 scripts/check_autonomous_paper_loop_contract.py --json
python3.11 scripts/check_autonomous_paper_scorecard_contract.py --json
python3.11 scripts/check_shadow_live_contract.py --json
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_cli_command_compatibility.py --json
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
```

- [ ] **Step 4: CLI smoke tests**

```bash
atlas validate
atlas config set market.symbol AAPL
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas run --mode paper
atlas run --mode live  # must remain fail-closed or analysis-only
atlas agent autonomous-paper --help
atlas agent autonomous-scorecard --help
```

- [ ] **Step 5: Stateful paper smoke**

```bash
TMPDIR=$(mktemp -d)
atlas agent autonomous-paper --symbol DEMO --strategy buy_and_hold --data-path data/sample/ohlcv.csv --max-cycles 3 --state-dir "$TMPDIR/state" --commission-bps 1 --slippage-bps 1 --json
atlas agent autonomous-paper --symbol DEMO --strategy buy_and_hold --data-path data/sample/ohlcv.csv --max-cycles 3 --state-dir "$TMPDIR/state" --resume --json
```

- [ ] **Step 6: Release gate**

```bash
python3.11 -m pip check
./scripts/release_check.sh --quick
```

- [ ] **Step 7: Final commit if clean**

```bash
git status
git log --oneline -5
```

If all checks pass and working tree is clean, push to origin main:

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ Mandatory checker cleanup — Task 1.
- ✅ Execution-neutral kernel — Task 3.
- ✅ Stateful runner with resume/dedup — Task 4.
- ✅ Next-bar fills and costs — Task 5.
- ✅ Trading metrics — Task 6.
- ✅ Redaction/portability — Task 7.
- ✅ CLI extension — Task 8.
- ✅ Tests — Task 9.
- ✅ Docs/candidate metadata — Task 10.
- ✅ Demo — Task 11.
- ✅ Verification — Task 12.

**Placeholder scan:** No `TBD` or `TODO` placeholders remain in code sections. Implementation details are delegated to subagents per step.

**Type consistency:** `StatefulPaperConfig`, `StatefulPaperState`, `StatefulPaperCursor`, `StatefulPaperMetrics`, `StatefulPaperResult` are defined in Task 2 and reused consistently.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-23-cand-003-stateful-paper-kernel.md`.

**Execution approach:** Subagent-Driven (recommended) — dispatch a fresh subagent per task, with spec compliance and code quality reviews between tasks.
