# Autonomous Paper Workflow

> **Status:** planning/demo documentation for the v0.6.13 line. Paper-only, local-only,
> no credentials, no broker calls, no provider calls. **Not financial advice.**
> This document does **not** claim autonomous-live-trading-readiness, live-trading
> safety, production-readiness, or profit guarantees.

## Purpose

Demonstrate L1 autonomy from the
[Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md): an autonomous
paper workflow that uses only local simulation, deterministic data, and offline
commands.

## What this demo proves

- Atlas can initialize or reuse a local paper workspace.
- Atlas can validate safe config without human per-step prompting.
- Atlas can run one or more paper-only cycles (`atlas run --mode paper --dry-run`,
  `atlas routine run --mode paper`, `atlas backtest run`, `atlas report generate`)
  without manual intervention.
- Atlas can run the paper-only strategy evaluation gate (`atlas backtest compare`)
  on bundled sample data for further paper follow-up decisions.
- Atlas can produce local evidence.
- Live paths remain disabled or fail safely.

## What this demo does NOT prove

- Profitable trading, claims that live trading is safe, production-readiness,
  autonomous-live-trading-readiness claims, broker execution correctness, or real
  provider quality.

## Suggested command path

```bash
atlas init <temp-workspace> --template routine-trader
cd <temp-workspace>
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO
atlas validate
atlas run --mode paper --dry-run --symbol ATLAS-DEMO --max-cycles 1
atlas run --mode paper --offline --symbol ATLAS-DEMO --max-cycles 1
atlas routine run pre_market --mode paper --symbol ATLAS-DEMO
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas backtest compare --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas report generate --type daily --format text
```

These commands require no credentials, no network, and no broker access.
`ATLAS-DEMO` is a documentation symbol for agent/routine steps; `DEMO-SYMBOL` is the
symbol used in the bundled sample OHLCV data for backtesting.
The `--offline` flag uses the provider-free paper path described in
[Paper Mode Provider Isolation](paper-provider-isolation.md).

## Evidence outputs

- `.atlas/` workspace artifacts (untracked, generated, reproducible).
- Console PASS summary from `scripts/demo_autonomous_paper_workflow.sh`.
- Checker output from `scripts/check_autonomous_paper_workflow_demo.py`.

## Demo script

Run the full autonomous paper workflow demo with:

```bash
bash scripts/demo_autonomous_paper_workflow.sh
```

Set `DEMO_WORKSPACE` to reuse a directory, or let the script create a temporary
workspace that is removed on exit.

## Evidence gate

Verify the demo, documentation, and safety invariants are present with:

```bash
python3.11 scripts/check_autonomous_paper_workflow_demo.py
python3.11 scripts/check_autonomous_paper_workflow_demo.py --json
python3.11 -m pytest tests/test_autonomous_paper_workflow_demo.py -q
```

## See also

- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Autonomy Roadmap](autonomy-roadmap.md)
- [Paper-Trading Guide](paper-trading-guide.md)
- [Paper Mode Provider Isolation](paper-provider-isolation.md)
- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [scripts/demo_autonomous_paper_workflow.sh](../scripts/demo_autonomous_paper_workflow.sh)
- [scripts/check_autonomous_paper_workflow_demo.py](../scripts/check_autonomous_paper_workflow_demo.py)
