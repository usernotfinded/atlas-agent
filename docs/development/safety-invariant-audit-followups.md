# Safety Invariant Audit — Follow-ups

An audit walked the ten hard invariants in
[Bounded Live Autonomy Governance](../bounded-live-autonomy-governance.md) and
the defect classes this project has fixed before, asking of each whether the
code enforces what the documentation promises.

Everything found was either fixed, or is recorded below because fixing it is a
decision for a maintainer rather than a correction. Each open item states what
the current behaviour is, why it was not changed, and what deciding either way
would involve. Items that have since been decided keep their finding and gain
the decision, so a later reader sees what was traded away rather than only the
result.

## Classification

| Label | Meaning |
|-------|---------|
| `contract_change` | The fix alters a published artifact vocabulary or schema that consumers read. |
| `semantics_change` | The fix changes what a safety component decides, not just how it reports. |
| `architecture` | The fix moves a boundary the project documented as deliberate. |
| `cleanup` | Redundancy with no behavioural effect. |

## Decided

### `allocation_drift` measured movement, not drift — `contract_change`

`backtest/portfolio.py::_check_allocation_drift` compounded a window's
portfolio-level returns and reported `|prod(1 + r) - 1|`. That is how far the
portfolio moved, not how far holdings drifted from their target weights, and
the two can point opposite ways: a window where every holding gains the same
10% has no allocation drift and is flagged, while a window that ends flat after
one holding doubled and another halved is reported as fine, which is where real
drift peaks.

**Decided: renamed.** The check is `_check_portfolio_movement` and the trigger
key is `portfolio_movement`, in the checker allowlist and the docs with it. A
key that names the wrong quantity is worse than a coarse one, because a reviewer
reading a flat window takes it as evidence the weights held — the case where
real drift peaks. Monitoring artifacts are generated locally and untracked, so
nothing persisted carries the old name;
`docs/paper-portfolio-monitoring.md` records what it was called through
v0.6.26.

Computing true drift remains out of reach at that layer: it would need a
per-strategy return series, and the simulation receives one aggregate series.

### The broker allowlist existed twice as a literal — `semantics_change`

`brokers/resolver.py` and `cli.py` each carried
`{"alpaca", "binance", "ccxt", "ibkr_stub"}` while the support registry held the
same knowledge with richer status. They had drifted in both directions:
`ibkr_stub` was in both literals and unknown to the registry, `ibkr` was known
to the registry and in neither literal — so neither name worked coherently.

**Decided: unified on the registry.** `diagnostics/preflight.py` already carried
the answer inline (`"ibkr" if requested_broker == "ibkr_stub" else …`), which is
what settled which list was correct: someone had met this divergence before and
resolved it toward the registry. That mapping is now `_BROKER_ID_ALIASES` in
`brokers/status.py`, both literals are gone, and preflight's special case with
them.

The gate reads `is_live_broker_known`, not `is_broker_known`: `paper` is in the
inventory, so the plain form would have let `live_broker = "paper"` past a gate
written to reject it.

### `default_strategy_registry()` rescanned the installed packages per call — `architecture`

Every call rebuilt the registry and rescanned entry points. The original note
recorded twenty lookups at 66 ms through the module-level helpers against 3 ms
against a single registry, and said the looping call sites had been fixed.

They had, but the per-call cost was not the small residue that suggests. The
registry is rebuilt once per `BacktestEngine`, and 94% of building an engine was
`importlib.metadata.entry_points()` walking every installed distribution: thirty
engine constructions measured 104.3 ms, of which 97.8 ms was thirty repeats of
that one scan. Any command that runs a sweep — `backtest compare`, sensitivity,
robustness, walk-forward — paid it per run.

**Decided: cache the scan, not the registry.** `_discovered_entry_point_factories`
is `lru_cache`d, so discovery happens once per process; the same thirty
constructions now measure 5.1 ms with one scan. `default_strategy_registry()`
still returns a fresh registry and `get()` still returns a fresh strategy
instance, which is the distinction that matters — caching one call further up
would hand every caller the same mutable registry and reuse strategies that
carry per-run state. A test pins both halves.

What this gives up is that a plugin installed *after* the process started is not
seen until restart. Nothing depended on it, and for a supervised trading run it
is the wrong behaviour to preserve: strategy code appearing mid-run enters with
no restart and no review. `cache_clear()` on that function rescans if a caller
ever needs it.

### A missing heartbeat does not fail closed — `semantics_change`

`safety/heartbeat.py::is_expired` reports a corrupt heartbeat as expired and an
absent one as fresh. The asymmetry is deliberate — a first run has no dead agent
to detect — but `HeartbeatManager` cannot tell "never recorded" from "recorded
and then deleted", so deleting the file has the same effect as never writing
one. The weaker failure is treated more permissively than the stronger one.

**Decided: kept.** Making an absent heartbeat expire needs a marker written at
first start, which adds a second file the deadman depends on — and a deadman
with two failure modes is not obviously safer than one with a documented gap. On
the order path the gap stays unreachable: `agent/runner.py` records a heartbeat
at the start of every cycle, before `KillSwitch.evaluate` can run. Both branches
are pinned by tests and the limitation is documented in `docs/kill-switch.md`.

## Open items

### 1. CLI startup costs about half a second — `architecture`

Every `atlas` invocation takes ~0.50 s before it does anything: ~346 ms
importing `atlas_agent.cli`, ~75 ms building the argparse tree, ~12 ms of
interpreter startup. `atlas --version` pays all of it.

**The original entry blamed `atlas_agent.backtest` at ~157 ms and proposed
deferring it. That number does not survive checking.** 157 ms is what the
importing-module attribution assigns to whichever import arrives at the shared
infrastructure first, and `backtest` happens to be first in `cli.py`. Its
*marginal* cost — the time that disappears if `cli.py` stops importing it — is
22.7 ms, about 4.5% of startup. The other ~174 ms is pydantic, `config.schema`,
`risk`, `audit`, and `events`, which `cli_commands` pulls in regardless.

Deferring the backtest imports would therefore mean threading local imports
through the dispatch in a 5.9k-line module whose command surface is a pinned
trust contract, to recover 4.5%. It is not worth it at that price, and it is not
the boundary question the original entry described.

Where the time actually goes is pydantic building model classes at import: the
self-time hotspots are ten `*.models` modules totalling ~64 ms, plus
`config.schema` at ~10 ms and pydantic itself at ~27 ms. Reducing that is a
question about pydantic at module scope, not about the `cli_bootstrap.py`
pre-router — which stays narrow for its own reason, that the four configless
commands must run with no config loaded and no third-party import on the path.

### 2. `guard_submit` and `guard_sync` have no callers — `cleanup`

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

## What the audit did change

For context on the boundaries above, the same pass fixed: a risk gate that
stopped rejecting when portfolio equity was non-finite; a review pack that
discarded the evidence it was handed; a reconcile failure that left no trace
while its report claimed otherwise; and `can_submit` reporting ready for brokers
the registry disables. It also added structural tests for the provider/execution
boundary, the set of modules that may reach a broker, and the credential paths
that must stay untracked.
