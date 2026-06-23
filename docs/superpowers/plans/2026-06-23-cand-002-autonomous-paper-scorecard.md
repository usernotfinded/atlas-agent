# CAND-002 Autonomous Paper Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a deterministic, offline scorecard and promotion gate for autonomous-paper artifacts.

**Architecture:** A new `src/atlas_agent/agent/autonomous_paper_scorecard.py` library reads `decisions.jsonl` + `manifest.json`, evaluates eleven conservative dimensions, and emits a machine-readable scorecard dict and Markdown report. A new `atlas agent autonomous-scorecard` CLI wraps it. A static contract checker, tests, docs, and release metadata updates follow the existing CAND-001 pattern.

**Tech Stack:** Python 3.11+, pydantic, stdlib `json`/`hashlib`/`pathlib`, existing `atlas_agent` backtest/report styles, pytest.

---

## File map

| File | Responsibility |
|---|---|
| `src/atlas_agent/agent/autonomous_paper_scorecard.py` | Scorecard builder, dimension evaluation, report rendering. |
| `src/atlas_agent/cli.py` | Register `autonomous-scorecard` parser and dispatch handler. |
| `scripts/check_autonomous_paper_scorecard_contract.py` | Static doc/CLI/test contract checker. |
| `scripts/demo_autonomous_paper_scorecard.sh` | Offline demo of paper loop + scorecard. |
| `tests/test_autonomous_paper_scorecard.py` | Unit/integration tests for the scorecard library and CLI. |
| `tests/test_autonomous_paper_scorecard_contract.py` | Tests for the static checker. |
| `tests/fixtures/cli_command_contract.json` | Add `autonomous-scorecard` to `agent` subcommands. |
| `docs/autonomous-paper-scorecard.md` | User-facing planning doc. |
| `docs/reviews/v0.6.16-cand-002-multimodel-review-packet.md` | Review handoff packet. |
| `docs/releases/v0.6.16-candidates.json` | Add CAND-002 as implemented in planning. |
| `docs/releases/v0.6.16-candidates.md` | Add CAND-002 implemented section. |
| `docs/releases/v0.6.16-plan.md` | Add CAND-002 to candidate table. |
| `docs/releases/v0.6.16-candidate-selection.md` | Add CAND-002 rationale. |
| `CHANGELOG.md` | Add CAND-002 bullets under `[Unreleased]`. |
| `scripts/dev_check.sh` / `scripts/release_check.sh` | Wire checker and tests. |

---

## Task 1: Implement the scorecard library

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_scorecard.py`

### Step 1.1: Define public API and constants

Create the module with:

```python
ARTIFACT_TYPE = "autonomous_paper_scorecard"
SCHEMA_VERSION = 1
PROMOTION_STATES = (
    "not_evaluated",
    "blocked",
    "paper_quality_observed",
    "eligible_for_shadow_live_review",
)
REQUIRED_DECISION_FIELDS = (
    "run_id", "iteration", "timestamp", "symbol", "mode",
    "data_source", "strategy_id", "proposed_action", "risk_result",
    "decision_state",
)
REQUIRED_MANIFEST_FIELDS = (
    "run_id", "mode", "symbol", "strategy_id", "data_source",
    "bars_processed", "decisions", "trades_executed", "trades_blocked",
    "no_trade_count", "decisions_path", "manifest_path",
)
SECRET_LIKE_PATTERNS = (
    "api_key", "apikey", "token", "password", "secret", "credential",
    "private_key", "privatekey", "auth_header", "bearer ", "ghp_", "sk-",
)
```

Add helper functions `_load_decisions(path)`, `_load_manifest(path)`, `_has_secret_like(text)`, `_dimension(name, passed, score, reason)`.

### Step 1.2: Implement dimension checks

Implement one function per dimension:

- `_check_schema_validity(decisions, manifest)` — JSONL parsed, required fields present, manifest fields present.
- `_check_replay_determinism(decisions, manifest, replay_decisions)` — consistent run_id, sequential iterations, monotonic timestamps, count match, optional replay equality.
- `_check_risk_gate_compliance(decisions)` — state/allowed consistency.
- `_check_kill_switch_compliance(decisions)` — no executed decision if kill-switch violation present.
- `_check_no_live_side_effects(decisions, manifest)` — mode==paper, no live broker/provider strings.
- `_check_audit_redaction(text)` — no secret-like substrings.
- `_check_decision_coverage(decisions, manifest)` — count match and >0.
- `_check_blocked_reason_quality(decisions)` — blocked reasons present.
- `_check_no_trade_reason_quality(decisions)` — hold/no-order consistency.
- `_check_artifact_completeness(decisions_path, manifest_path, manifest)` — files exist and non-empty.
- `_check_future_shadow_live_prerequisites(manifest, dimensions)` — completed, diversity, all safety dims pass.

### Step 1.3: Implement promotion gate

```python
def _determine_promotion_state(manifest, dimensions, blockers):
    if not manifest or not dimensions:
        return "not_evaluated", ["Missing or unreadable artifacts."]
    dim_map = {d["name"]: d for d in dimensions}
    critical = ["schema_validity", "no_live_side_effects", "audit_redaction", "artifact_completeness"]
    for name in critical:
        if not dim_map.get(name, {}).get("passed"):
            return "blocked", blockers + [f"Critical dimension failed: {name}"]
    safety = ["risk_gate_compliance", "kill_switch_compliance", "no_live_side_effects", "audit_redaction"]
    if all(dim_map[n]["passed"] for n in safety) and dim_map["future_shadow_live_prerequisites"]["passed"]:
        return "eligible_for_shadow_live_review", blockers
    if dim_map["schema_validity"]["passed"] and dim_map["artifact_completeness"]["passed"]:
        return "paper_quality_observed", blockers
    return "blocked", blockers
```

### Step 1.4: Implement builder and renderer

```python
def build_autonomous_paper_scorecard(decisions_path, manifest_path, *, replay_decisions_path=None):
    decisions, manifest, errors = _load_artifacts(decisions_path, manifest_path)
    if errors:
        return _empty_scorecard(errors)
    dimensions = [...]
    blockers = [d["reason"] for d in dimensions if not d["passed"]]
    state, blockers = _determine_promotion_state(manifest, dimensions, blockers)
    return { ... }

def write_autonomous_paper_scorecard_reports(scorecard, output_dir):
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "autonomous-paper-scorecard.json"
    md_path = destination / "autonomous-paper-scorecard.md"
    json_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True, allow_nan=False) + "\n")
    md_path.write_text(render_autonomous_paper_scorecard_markdown(scorecard))
    return json_path, md_path
```

The Markdown renderer must include a planning-only banner, safety flags, dimension table, promotion state, blockers, and explicit statement that this is not live readiness.

### Step 1.5: Compile and smoke test

```bash
python3.11 -m compileall src/atlas_agent/agent/autonomous_paper_scorecard.py
python3.11 -c "from atlas_agent.agent.autonomous_paper_scorecard import build_autonomous_paper_scorecard; print('import ok')"
```

---

## Task 2: Add scorecard unit/integration tests

**Files:**
- Create: `tests/test_autonomous_paper_scorecard.py`

### Step 2.1: Helpers

Reuse `_make_config` and `run_autonomous_paper_loop` patterns from `tests/test_autonomous_paper_loop.py`. Add helper `_scorecard_for_run(result)`.

### Step 2.2: Tests

Write tests:

```python
def test_valid_completed_run_scorecard(tmp_path):
    config = _make_config(tmp_path)
    result = run_autonomous_paper_loop(config=config, max_cycles=5, strategy_id="buy_and_hold", strategy_parameters={"position_pct": 0.2})
    scorecard = build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path)
    assert scorecard["artifact_type"] == "autonomous_paper_scorecard"
    assert scorecard["promotion_state"] in ("paper_quality_observed", "eligible_for_shadow_live_review")
    assert scorecard["mode"] == "paper"

def test_missing_artifacts_not_evaluated(tmp_path):
    scorecard = build_autonomous_paper_scorecard(str(tmp_path / "missing.jsonl"), str(tmp_path / "missing.json"))
    assert scorecard["promotion_state"] == "not_evaluated"

def test_malformed_jsonl_blocked(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    manifest = tmp_path / "manifest.json"
    decisions.write_text("not json\n")
    manifest.write_text(json.dumps({"run_id": "r", "mode": "paper"}))
    scorecard = build_autonomous_paper_scorecard(str(decisions), str(manifest))
    assert scorecard["promotion_state"] == "blocked"

def test_risk_blocked_run_scoring(tmp_path):
    config = _make_config(tmp_path, risk={"symbol_allowlist": ["OTHER"]})
    result = run_autonomous_paper_loop(config=config, max_cycles=3, strategy_id="buy_and_hold", strategy_parameters={"position_pct": 0.2})
    scorecard = build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path)
    assert scorecard["scorecard_dimensions"]["risk_gate_compliance"]["passed"] is True
    assert scorecard["scorecard_dimensions"]["blocked_reason_quality"]["passed"] is True

def test_no_trade_run_scoring(tmp_path):
    config = _make_config(tmp_path)
    result = run_autonomous_paper_loop(config=config, max_cycles=3, strategy_id="moving_average_cross")
    scorecard = build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path)
    assert scorecard["scorecard_dimensions"]["no_trade_reason_quality"]["passed"] is True

def test_kill_switch_blocked_run_scoring(tmp_path):
    config = _make_config(tmp_path, safety={"kill_switch_enabled": True})
    result = run_autonomous_paper_loop(config=config, max_cycles=3, strategy_id="buy_and_hold", strategy_parameters={"position_pct": 0.2})
    scorecard = build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path)
    assert scorecard["trades_executed"] == 0
    assert scorecard["scorecard_dimensions"]["kill_switch_compliance"]["passed"] is True

def test_replay_mismatch_blocks_promotion(tmp_path):
    config = _make_config(tmp_path)
    result = run_autonomous_paper_loop(config=config, max_cycles=3, strategy_id="buy_and_hold", strategy_parameters={"position_pct": 0.2})
    replay = tmp_path / "replay.jsonl"
    replay.write_text(json.dumps({"run_id": "other", "iteration": 0, "decision_state": "paper_executed", ...}) + "\n")
    scorecard = build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path, replay_decisions_path=str(replay))
    assert scorecard["promotion_state"] == "blocked"

def test_redaction_requirements_enforced(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    manifest = tmp_path / "manifest.json"
    bad = {... "risk_result": {"secret_token": "abc123"} ...}
    decisions.write_text(json.dumps(bad) + "\n")
    manifest.write_text(json.dumps({"run_id": "r", "mode": "paper", "decisions": 1, ...}))
    scorecard = build_autonomous_paper_scorecard(str(decisions), str(manifest))
    assert scorecard["scorecard_dimensions"]["audit_redaction"]["passed"] is False

def test_promotion_state_conservative_defaults():
    scorecard = build_autonomous_paper_scorecard("", "")
    assert scorecard["promotion_state"] == "not_evaluated"

def test_cli_smoke(tmp_path, monkeypatch):
    # Use atlas agent autonomous-scorecard --help / --json smoke similar to test_autonomous_paper_loop.py
```

### Step 2.3: Run focused tests

```bash
python3.11 -m pytest tests/test_autonomous_paper_scorecard.py -q
```

---

## Task 3: Wire CLI command

**Files:**
- Modify: `src/atlas_agent/cli.py` (parser registration around line 827; handler around line 5812)
- Modify: `tests/fixtures/cli_command_contract.json`

### Step 3.1: Register parser

After the `agent_autonomous_paper` block add:

```python
agent_autonomous_scorecard = agent_sub.add_parser(
    "autonomous-scorecard",
    help="Evaluate autonomous-paper decision artifacts and produce a promotion scorecard.",
)
agent_autonomous_scorecard.add_argument("--decisions", required=True, help="Path to decisions.jsonl")
agent_autonomous_scorecard.add_argument("--manifest", required=True, help="Path to manifest.json")
agent_autonomous_scorecard.add_argument("--replay-decisions", help="Optional second decisions file for replay comparison")
agent_autonomous_scorecard.add_argument("--output-dir", help="Directory for scorecard JSON/Markdown reports")
agent_autonomous_scorecard.add_argument("--json", action="store_true", help="Emit scorecard as JSON")
```

### Step 3.2: Add handler

Inside `if args.command == "agent":` add:

```python
elif args.agent_command == "autonomous-scorecard":
    from atlas_agent.agent.autonomous_paper_scorecard import (
        build_autonomous_paper_scorecard,
        write_autonomous_paper_scorecard_reports,
    )
    output_dir = getattr(args, "output_dir", None) or str(config.reports_dir / "autonomous_paper_scorecard")
    scorecard = build_autonomous_paper_scorecard(
        decisions_path=args.decisions,
        manifest_path=args.manifest,
        replay_decisions_path=getattr(args, "replay_decisions", None),
    )
    write_autonomous_paper_scorecard_reports(scorecard, output_dir)
    if getattr(args, "json", False):
        return emit_cli_success("atlas agent autonomous-scorecard", scorecard)
    print(f"autonomous-scorecard: {scorecard['promotion_state']}")
    print(f"  output dir: {output_dir}")
    for blocker in scorecard.get("blockers", []):
        print(f"  blocker: {blocker}")
    return 0 if scorecard["promotion_state"] not in ("blocked", "not_evaluated") else 2
```

### Step 3.3: Update CLI contract

Add `"autonomous-scorecard"` to the `agent` subcommand list in `tests/fixtures/cli_command_contract.json`.

### Step 3.4: Test CLI

```bash
atlas agent autonomous-scorecard --help
python3.11 scripts/check_cli_command_compatibility.py
```

---

## Task 4: Create static contract checker

**Files:**
- Create: `scripts/check_autonomous_paper_scorecard_contract.py`

Mirror `scripts/check_autonomous_paper_loop_contract.py`.

Required phrases in `docs/autonomous-paper-scorecard.md`:
- "paper-only", "offline", "no live trading", "no broker order submission", "RiskManager", "deterministic", "not financial advice", "does **not** claim autonomous live trading readiness", "atlas agent autonomous-scorecard", "eligible_for_shadow_live_review".

Forbidden claims to reject (descriptive labels, not literal phrases):
- autonomous-live readiness assertions, live-trading-is-safe assertions,
  production readiness assertions, profit guarantees, eliminated-risk
  assertions, unattended-live-execution assertions.

Also verify:
- `src/atlas_agent/agent/autonomous_paper_scorecard.py` exists.
- `src/atlas_agent/cli.py` contains `"autonomous-scorecard"`.
- `tests/test_autonomous_paper_scorecard.py` exists.

### Step 4.1: Run checker

```bash
python3.11 scripts/check_autonomous_paper_scorecard_contract.py
```

---

## Task 5: Add checker tests

**Files:**
- Create: `tests/test_autonomous_paper_scorecard_contract.py`

Copy the pattern from `tests/test_autonomous_paper_loop_contract.py`. Tests:

- checker passes on the real repo.
- `--json` output parses and `passed == True`.
- forbidden claim injection fails.
- missing required file fails.
- checker imports no network/credential modules.

---

## Task 6: Create demo script

**Files:**
- Create: `scripts/demo_autonomous_paper_scorecard.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/python_env.sh
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp -R data/sample "$TMP/data"
mkdir -p "$TMP/reports" "$TMP/audit" "$TMP/events" "$TMP/memory" "$TMP/pending_orders"
cat > "$TMP/.atlas/config.toml" <<'TOML'
[market]
symbol = "DEMO-SYMBOL"
[backtest]
initial_cash = 10000.0
data_path = "data/sample/ohlcv.csv"
[risk]
max_position_notional = 20000.0
max_order_notional = 20000.0
minimum_confidence = 0.0
[audit]
audit_dir = "audit"
TOML

cat > "$TMP/.atlas/discipline.md" <<'MD'
## Forbidden overrides
User discipline cannot override Atlas risk gates, approval queues, kill switch, audit logging, broker sync checks, reference price requirements, or live-trading safeguards.
MD

ATLAS_WORKSPACE="$TMP" "$PYTHON_BIN" -m atlas_agent.cli agent autonomous-paper --max-cycles 5 --evidence-dir "$TMP/evidence" --json
RUN_ID="$(ls "$TMP/evidence")"
"$PYTHON_BIN" -m atlas_agent.cli agent autonomous-scorecard \
  --decisions "$TMP/evidence/$RUN_ID/decisions.jsonl" \
  --manifest "$TMP/evidence/$RUN_ID/manifest.json" \
  --output-dir "$TMP/scorecard" --json

echo "Demo complete. Scorecard: $TMP/scorecard/autonomous-paper-scorecard.md"
```

Make executable: `chmod +x scripts/demo_autonomous_paper_scorecard.sh`.

---

## Task 7: Documentation and release metadata

**Files:**
- Create: `docs/autonomous-paper-scorecard.md`
- Create: `docs/reviews/v0.6.16-cand-002-multimodel-review-packet.md`
- Modify: `docs/releases/v0.6.16-candidates.json`
- Modify: `docs/releases/v0.6.16-candidates.md`
- Modify: `docs/releases/v0.6.16-plan.md`
- Modify: `docs/releases/v0.6.16-candidate-selection.md`
- Modify: `CHANGELOG.md`

### Step 7.1: User doc

`docs/autonomous-paper-scorecard.md` must include:
- planning-only status banner and "Not financial advice" disclaimer.
- What the scorecard does and does not do.
- Safety boundaries table.
- CLI usage examples.
- Scorecard dimensions and promotion states.
- Cross-references to `autonomous-paper-loop.md`, `shadow-live-readiness-contract.md`, `bounded-live-autonomy-governance.md`.

### Step 7.2: Review packet

`docs/reviews/v0.6.16-cand-002-multimodel-review-packet.md` mirrors CAND-001 packet with prompts for GPT-5.5, Claude Opus 4.6 Thinking, Gemini 3.1 Pro, Kimi k2.7-code focused on the scorecard gate.

### Step 7.3: Release metadata

Add CAND-002 object to `v0.6.16-candidates.json`:

```json
{
  "id": "CAND-002",
  "status": "implemented",
  "title": "Autonomous Paper Decision Quality Scorecard and Promotion Gate",
  "description": "Deterministic offline scorecard that evaluates autonomous-paper artifacts for future shadow-live/read-only review eligibility.",
  "notes": "No live trading, live submit, broker order submission, or real provider calls. No version bump, tag, release, or PyPI publication."
}
```

Update `.md`, `-plan.md`, and `-candidate-selection.md` accordingly.

### Step 7.4: CHANGELOG

Add under `[Unreleased]`:
- CAND-002 bullet with command, module, checker, tests, docs.
- Safety bullet reiterating boundaries.

---

## Task 8: Wire into gate scripts

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/release_check.sh`

Add after the existing autonomous-paper loop contract section (around section 4m):

```bash
echo ""
echo "4m. autonomous paper scorecard contract check"
SECONDS=0
"$PYTHON_BIN" scripts/check_autonomous_paper_scorecard_contract.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4n. autonomous paper scorecard tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_autonomous_paper_scorecard.py tests/test_autonomous_paper_scorecard_contract.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Adjust existing section labels if necessary to avoid collisions.

---

## Task 9: Final verification

Run the verification commands from the design spec:

```bash
git status
git diff --check
python3.11 -m compileall src
python3.11 -m pytest tests/test_autonomous_paper_scorecard.py tests/test_autonomous_paper_scorecard_contract.py -q
python3.11 scripts/check_autonomous_paper_scorecard_contract.py
python3.11 -m pip check
atlas validate
atlas agent autonomous-paper --help
atlas agent autonomous-scorecard --help
./scripts/demo_autonomous_paper_scorecard.sh
atlas run --mode paper
atlas run --mode live  # expect non-zero
./scripts/release_check.sh --quick
```

---

## Spec coverage self-check

- Scorecard dimensions: Task 1.
- Promotion states: Task 1.
- JSON + Markdown output: Task 1.
- CLI command: Tasks 3.
- Static checker: Task 4.
- Tests: Tasks 2 and 5.
- Docs/release metadata: Task 7.
- Gate script wiring: Task 8.
- Safety boundaries: enforced in dimension logic, doc phrases, and checker.
