# Research-to-Backtest Bridge

## Status

This is the v0.6.2 roadmap line. It is read-only, paper-only, offline, and
requires no provider, broker, or network access.

This is not financial advice. It is not live readiness, not autonomous-live
readiness, not production-ready, and not a profit guarantee. A proposal is a
suggestion for what an operator could backtest, never an authorization to trade.

## Purpose

A research artifact records analysis. A backtest needs inputs. The bridge
connects the two without letting the first authorize the second: it reads one
local research artifact and returns a paper-only proposal naming the registered
strategies and validated parameters an operator could evaluate.

The bridge creates no pending orders, no approvals, and no broker or provider
calls. It writes nothing at all — it reads an artifact and returns a proposal.

## The trust boundary

Research artifacts are untrusted input. Provider output, retrieved pages, and
model summaries can all reach an artifact, so the bridge treats every field as a
claim rather than an instruction. An artifact may influence exactly three things:

| Field | Constraint |
|---|---|
| `symbol` | Read from the artifact, then sanitized. |
| Strategy selection | Must already be registered. An unknown id is rejected, never created. |
| Strategy parameters | Coerced and range-checked by the strategy's own parameter specs. |

Everything else is out of reach. An artifact cannot set the operating mode, a
risk limit, the kill-switch state, an approval, or an order. Any other field
inside the hypothesis block is reported in `notes` as unsupported rather than
silently dropped, so a reviewer can see what the artifact tried to say.

## Declaring a hypothesis

The bridge reads a structured block from artifact metadata. It never parses
prose: a thesis paragraph that mentions a moving average does not become a
strategy selection, because a summary is not a decision and inferring one would
manufacture a hypothesis the analysis never stated.

```json
{
  "metadata": {
    "backtest_hypothesis": {
      "strategies": ["moving_average_cross"],
      "parameters": {
        "moving_average_cross": {"short_window": 3, "long_window": 8}
      },
      "rationale": "Free-text note carried through to the proposal."
    }
  }
}
```

An artifact with no such block yields a proposal with status `no_hypothesis`,
an empty strategy list, and a note explaining the absence.

## Building a proposal

```bash
atlas research backtest-proposal <run_id>
atlas research backtest-proposal <run_id> --json
```

The command reads the named artifact and prints what it derived — accepted
strategies with their resolved parameters, rejected entries with the reason, and
any notes about fields it refused to honour. It exits non-zero only when the
artifact cannot be read; an artifact that proposes nothing is a valid answer, not
an error.

```
Backtest proposal (paper-only, no orders, no approvals)
  Symbol: AAPL
  Mode: paper
  Source Run ID: run-demo
  Status: proposed
  Accepted strategies: 1
    - moving_average_cross (exit_on_cross=True, long_window=8, position_pct=1.0, short_window=3)
  Rejected strategies: 1
    - not_a_strategy: Strategy is not registered; the bridge never invents one.
  Note: Ignoring unsupported hypothesis field(s): mode
  This proposal is not financial advice and authorizes no trading.
```

## Proposal status values

| Status | Meaning |
|---|---|
| `proposed` | At least one registered strategy passed validation. |
| `no_hypothesis` | The artifact declares no structured hypothesis. |
| `hypothesis_malformed` | A hypothesis exists, but nothing in it survived validation. |

Rejections are itemized in `rejected_strategies` with a `reason_code` of
`unknown_strategy`, `invalid_parameters`, `malformed_entry`, or
`duplicate_strategy`. A rejected entry is always reported; it is never dropped
in silence.

## Running the proposed strategies

A proposal describes inputs. Evaluating them stays an explicit operator action
against local data, through the existing paper evaluation:

```python
from atlas_agent.backtest.evaluation import build_paper_strategy_evaluation
from atlas_agent.research.backtest_bridge import build_backtest_proposal

proposal = build_backtest_proposal(workspace_path, run_id)
report = build_paper_strategy_evaluation(
    data_path="data/sample/ohlcv.csv",
    symbol=proposal["symbol"],
    strategies=[item["strategy_id"] for item in proposal["accepted_strategies"]],
    parameters={
        item["strategy_id"]: item["parameters"]
        for item in proposal["accepted_strategies"]
    },
)
```

The evaluation runs the deterministic paper engine with the risk manager
enabled. Parameters that pass the bridge still face every risk gate: an
allocation that exceeds a notional or exposure limit is blocked at the engine,
exactly as it would be for a hand-written configuration.

## Related documentation

- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Autonomy Roadmap](autonomy-roadmap.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
