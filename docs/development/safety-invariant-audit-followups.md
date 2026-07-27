# Safety Invariant Audit — Follow-ups

An audit walked the ten hard invariants in
[Bounded Live Autonomy Governance](../bounded-live-autonomy-governance.md) and
the defect classes this project has fixed before, asking of each whether the
code enforces what the documentation promises.

Everything found was either fixed, or is recorded below because fixing it is a
decision for a maintainer rather than a correction. Each open item states what
the current behaviour is, why it was not changed, and what deciding either way
would involve.

## Classification

| Label | Meaning |
|-------|---------|
| `contract_change` | The fix alters a published artifact vocabulary or schema that consumers read. |
| `semantics_change` | The fix changes what a safety component decides, not just how it reports. |
| `architecture` | The fix moves a boundary the project documented as deliberate. |
| `cleanup` | Redundancy with no behavioural effect. |

## Open items

### 1. `allocation_drift` measures movement, not drift — `contract_change`

`backtest/portfolio.py::_check_allocation_drift` compounds a window's
portfolio-level returns and reports `|prod(1 + r) - 1|`. That is how far the
portfolio moved, not how far holdings drifted from their target weights, and
the two can point opposite ways: a window where every holding gains the same
10% has no allocation drift and is flagged, while a window that ends flat after
one holding doubled and another halved is reported as fine, which is where real
drift peaks.

The docstring and `docs/paper-portfolio-monitoring.md` now state what is
measured, and a test pins it. The trigger key still reads `allocation_drift`.

Deciding it: renaming the key touches the published monitoring vocabulary, its
checker allowlist in `scripts/check_paper_portfolio_monitoring.py`, and the
docs. Computing true drift instead would need a per-strategy return series,
which does not exist at that layer — the simulation receives one aggregate
series.

### 2. A missing heartbeat does not fail closed — `semantics_change`

`safety/heartbeat.py::is_expired` reports a corrupt heartbeat as expired and an
absent one as fresh. The asymmetry is deliberate — a first run has no dead agent
to detect — but `HeartbeatManager` cannot tell "never recorded" from "recorded
and then deleted", so deleting the file has the same effect as never writing
one. The weaker failure is treated more permissively than the stronger one.

On the order path this stays unreachable: `agent/runner.py` records a heartbeat
at the start of every cycle, before `KillSwitch.evaluate` can run. Both branches
are pinned by tests and the limitation is documented in `docs/kill-switch.md`.

Deciding it: making an absent heartbeat expire needs a way to distinguish a
first run from lost state. A marker written at first start would do it, at the
cost of another file the deadman depends on.

### 3. CLI startup imports the whole backtest domain — `architecture`

`atlas --help` takes roughly 400 ms, most of it importing
`atlas_agent.backtest` (~157 ms) at `cli.py` module scope, for commands that do
not use it.

This was left alone because the narrow pre-router in `cli_bootstrap.py` is
deliberate: it peels off exactly four configless trust-contract commands and
says so in its own comment — "that is a feature, not a gap". Widening it, or
making `cli.py` import lazily, is a decision about that boundary.

### 4. `default_strategy_registry()` is rebuilt per call — `architecture`

Every call constructs the registry and rescans entry points. Twenty lookups
measured at 66 ms through the module-level helpers against 3 ms against a single
registry. Call sites that looped were fixed; the per-call cost remains.

Deciding it: a process-wide cache would fix it everywhere, and would change when
plugin discovery happens — currently every call sees newly installed entry
points.

### 5. `guard_submit` and `guard_sync` have no callers — `cleanup`

`brokers/guards.py` holds two fail-closed guards. `guard_submit` was found to
disagree with the resolver, which answered `live_submit_ready` for brokers the
support registry marks disabled; the registry half was extracted into
`guard_broker_live_submit_capability` and the resolver now calls it. The
remaining flag checks in `guard_submit` duplicate the resolver's own gates.

`guard_sync` is also uncalled, but its rules and the resolver agree: both allow
read-only sync for `alpaca` only. Wiring it in could only loosen behaviour, so
it was left as it is.

Deciding it: both are exported from `brokers/__init__.py`, so removing either is
a public API change.

### 6. The broker allowlist exists twice as a literal — `semantics_change`

`brokers/resolver.py` and `cli.py` each carry
`{"alpaca", "binance", "ccxt", "ibkr_stub"}` while the support registry holds
the same knowledge with richer status. They have already drifted: `ibkr_stub` is
in both literals and unknown to the registry, and `ibkr` is known to the registry
and in neither literal.

Deciding it: replacing the literals with `is_broker_known` changes behaviour in
both directions — `ibkr_stub` would become unsupported and `ibkr` supported —
so it needs a call on which list is correct rather than a mechanical swap.

## What the audit did change

For context on the boundaries above, the same pass fixed: a risk gate that
stopped rejecting when portfolio equity was non-finite; a review pack that
discarded the evidence it was handed; a reconcile failure that left no trace
while its report claimed otherwise; and `can_submit` reporting ready for brokers
the registry disables. It also added structural tests for the provider/execution
boundary, the set of modules that may reach a broker, and the credential paths
that must stay untracked.
