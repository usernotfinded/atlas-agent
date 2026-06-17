# Paper Mode Provider Isolation

Atlas Agent supports provider-free paper workflows. In paper mode, the agent can run a bounded local cycle without an AI provider API key and without making network requests, unless the operator explicitly opts in to provider-backed paper analysis.

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading is disabled by default.

## Paper mode offline guarantee

When `atlas run --mode paper` or `atlas agent run --mode paper` is invoked:

- No provider API key is required by default.
- No network request to an AI provider is made by default.
- If a real provider is configured but its credentials are missing, Atlas falls back to the offline `NullProvider`, which returns a deterministic "hold" response.
- The fallback is logged and auditable; it never bypasses `RiskManager`, approval gates, or the kill switch.
- You can also force the offline path explicitly with `--offline`:

```bash
atlas run --mode paper --offline --symbol ATLAS-DEMO --max-cycles 1
atlas agent run --mode paper --offline --symbol ATLAS-DEMO --max-cycles 1
```

## Provider-backed paper analysis

Operators who want AI-generated analysis in paper mode can still configure a provider and API key. This is strictly opt-in and remains paper-only: no orders are submitted to a live broker unless every live-submit gate is explicitly satisfied.

```bash
atlas model set openai gpt-4o
# export OPENAI_API_KEY=...
atlas run --mode paper --symbol ATLAS-DEMO --max-cycles 1
```

Provider-backed paper analysis is never treated as execution authority. All proposed orders still pass through deterministic risk checks and, for live submit, human approval.

## Live mode remains fail-closed

The offline paper fallback **does not** apply to live mode. `atlas run --mode live` continues to require:

- `enable_live_trading=true`
- a configured live broker
- present broker credentials
- an explicit live-submit opt-in record
- a normal kill-switch state

If any of these are missing, live mode fails safely with an error and exit code 2.

## What this means for autonomy

- **L1 autonomous paper workflows** can run offline, with no provider, no broker contact, and no credentials.
- **Paper strategy evaluation** can compare registered backtest strategies offline with
  `atlas backtest compare`; see [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md).
- **L3/L4 live autonomy** remains out of scope and disabled by default.
- This is not a claim of autonomous-live-trading-readiness, production readiness, or trading without risk.

## Related documents

- [Autonomous Paper Workflow](autonomous-paper-workflow.md)
- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Live Submit Safety Contract](live-submit-safety-contract.md)
- [Paper Trading Guide](paper-trading-guide.md)
