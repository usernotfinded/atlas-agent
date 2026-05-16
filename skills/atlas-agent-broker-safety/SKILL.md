# atlas-agent-broker-safety

## When to use this skill

- Changes to broker adapters (Alpaca, Binance, CCXT, PaperBroker)
- Changes to `BrokerSyncService`, `BrokerResolver`, or broker status resolution
- Changes to `OrderRouter`, `ApprovalManager`, or order execution paths
- Changes to `RiskManager` evaluation of orders
- Changes to live/paper mode toggling or `can_submit` logic
- Changes to quote providers or market-order validation
- Changes to pending order creation, approval, or submission

## Files and areas this applies to

- `src/atlas_agent/brokers/` (all adapters, resolver, sync)
- `src/atlas_agent/execution/` (order router, approval, submit)
- `src/atlas_agent/risk/` (RiskManager, limits, evaluation)
- `src/atlas_agent/safety/` (kill switch, live-mode guards)
- `src/atlas_agent/cli.py` (broker subcommands, order subcommands)

## Non-negotiable rules

1. **Live submit remains disabled by default.** `BrokerResolver.can_submit` must be `false` for all live brokers unless every required opt-in condition is satisfied. Never change this default.
2. **`resolve_execution_broker("live")` returns `None` by default.** A real broker must only be resolved when `can_submit` is explicitly `true`.
3. **Strict broker sync is the default.** Partial or degraded sync results must be treated as failures. They must not feed risk validation, approval decisions, or order placement.
4. **Risk validation uses synced state.** In live mode, `RiskManager.evaluate_order` must use a fresh `PortfolioSnapshot` from broker sync. Do not use stale or mock portfolio state for live risk checks.
5. **Orders require approval in live mode.** Live orders must pass through `ApprovalManager` unless explicitly configured otherwise. Never bypass the approval gate.
6. **Kill switch blocks everything.** If the kill switch is active, no live order may proceed, regardless of other gates.
7. **Paper mode must never call live brokers.** Paper orders route through `PaperBroker` only. Verify that paper paths do not instantiate live broker adapters.
8. **Error ordering must be deterministic.** Broker errors, risk rejections, and approval failures must be checked in a documented order and reported consistently.
9. **Market orders require fresh quotes.** Market-order submit must have a validated quote. Missing or stale quotes block execution.

## Required checks

- [ ] `BrokerResolver.can_submit` remains `false` for default live brokers
- [ ] `resolve_execution_broker("live")` returns `None` in default configuration
- [ ] Paper mode does not instantiate live broker adapters
- [ ] Kill switch check happens before any broker contact
- [ ] Risk evaluation uses fresh synced state in live mode
- [ ] New order paths include approval gate checks

## Required tests or verification commands

```bash
python3.11 -m pytest tests/brokers -q
python3.11 -m pytest tests/execution -q
python3.11 -m pytest tests/risk -q
python3.11 -m pytest tests/ -q -k "broker or order or risk or submit"
```

## Output format expected

When changing broker or execution code, produce:
1. Live/paper mode impact assessment
2. Broker sync strategy (strict vs partial, fallback behavior)
3. Risk validation data source (synced state vs cached vs mock)
4. Approval gate behavior for the changed path
5. Kill switch interaction
6. A go/no-go recommendation for live-mode safety

## Common failure modes to avoid

- **Accidentally enabling live submit.** A config parsing change or default value change can flip `can_submit` to `true`. Always assert the default remains `false`.
- **Using partial sync for risk.** If sync returns degraded data, risk evaluation may be based on incorrect portfolio state. Reject degraded sync before risk evaluation.
- **Paper path leaking into live.** A shared helper that conditionally routes orders must be carefully reviewed to ensure the paper branch never instantiates live brokers.
- **Forgetting kill switch in new execution paths.** Any new live execution entrypoint must check the kill switch.
- **Approval bypass via direct broker call.** Never allow code paths that call `broker.place_order()` without going through `OrderRouter` and `ApprovalManager`.
