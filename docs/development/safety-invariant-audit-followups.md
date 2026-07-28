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

### `guard_submit` and `guard_sync` had no callers — `cleanup`

`brokers/guards.py` holds two fail-closed guards that nothing called. The
original note recorded them as redundant with the resolver and said `guard_sync`
agreed with it anyway: "both allow read-only sync for `alpaca` only. Wiring it in
could only loosen behaviour."

**That claim was wrong, and checking it is what found the defect.** `guard_sync`
asked `is_broker_known`, and `paper` is in the inventory with
`read_only_supported=True` — so the guard admitted `paper` as a *live* sync
broker while `BrokerResolver` refuses it as `live_broker_unsupported`. The same
class of mistake as the two broker literals, in the module written to prevent it.
`guard_submit` survives the identical predicate only because
`live_submit_supported` is false for `paper`; `guard_sync` had no such second
line.

**Decided: fixed, and pinned rather than deleted.** `guard_sync` now asks
`is_live_broker_known`. Deleting the guards would have removed a cross-check to
save lines: the live-submit rule is written twice on purpose, because the
resolver must report a reason code per gate and the guard must raise once, and
neither output can be derived from the other without parsing a message — which
this project does not do. So the duplication stays and the agreement is now
tested: all 2^9 gate combinations assert that `guard_submit` never allows what
the resolver denies for a shared reason, and never refuses what it calls ready.

A guard may be stricter than the live path. It may never be looser. That is the
property the tests state, and it is what nothing checked while these guards sat
uncalled — which is how the resolver came to answer `live_submit_ready` for
brokers the inventory disables.

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

### The approval gate fails without an audit record — `semantics_change`

Hard invariant 8 says the audit hash-chain records "**all** gate failures, risk
rejections, kill-switch transitions, and submit attempts". `docs/release-checklist.md`
enumerates the reason codes for which `live_submit_blocked` is emitted, and that
list starts at the HMAC-approval gate. The code follows the checklist, so the
gates before it return blocked and write nothing:

```
not approved             blocked_reason=not_approved         NO AUDIT RECORD
already submitted        blocked_reason=already_submitted    NO AUDIT RECORD
terminal state           blocked_reason=terminal_state       NO AUDIT RECORD
corrupt file             blocked_reason=invalid_pending_order    1 audit line
```

`not_approved` is the one that matters. Invariant 7 makes approval mandatory, and
the failure of that gate — the event an operator would search the chain for when
asking whether anything tried to submit without approval — leaves no
tamper-evident trace. `already_submitted` and `terminal_state` are repeat submit
attempts, which invariant 8 also names.

The two documents disagree, and which is authoritative decides the fix. Read as
a contract, the checklist defines a deliberate subset and the code is correct.
Read as a verification checklist, it is an incomplete list of things to check
and the governance invariant stands, making this a gap in the submit path.

Deciding it: emitting for the earlier gates is mechanically small —
`_emit_live_submit_blocked` is already called by fifteen neighbouring gates with
established ordering and redaction — but it changes what a live-submit audit log
contains, which release checks read. `tests/audit/test_live_submit_blocked_event_set.py`
now pins the checklist against the emitters, so whichever way this is decided,
the two can no longer drift apart quietly.

### CLI startup costs about half a second — `architecture`

Every `atlas` invocation takes ~0.50 s before it does anything: ~346 ms
importing `atlas_agent.cli`, ~75 ms building the argparse tree, ~12 ms of
interpreter startup. `atlas --version` pays all of it.

**This is mostly not a UX cost. It is the dominant cost of the dev gate.** The
test suite exercises the CLI the way an operator does — by spawning it — from 97
call sites. The gate's single slowest step, `4h. paper strategy evaluation
tests` at 46 s and 31% of accounted gate time, spends 73% of its wall clock in 21
CLI subprocesses at ~0.56 s each, most of that before the command starts.

**The original entry blamed `atlas_agent.backtest` at ~157 ms. That number does
not survive checking.** 157 ms is what importing-module attribution assigns to
whichever import reaches the shared infrastructure first, and `backtest` happens
to be first in `cli.py`. Its *marginal* cost — what disappears if `cli.py` stops
importing it — is 22.7 ms, about 4.5% of startup. The rest is pydantic,
`config.schema`, `risk`, `audit`, and `events`, which `cli_commands` pulls in
regardless.

That trap is worth stating once, because it is easy to fall into twice:
`urllib.request` sits at `cli.py` module scope for one function that makes a
network call, and `-X importtime` bills it 28.6 ms. Moving it into that function
saves **0.0 ms** — the rest of the CLI graph already imports it. A module-scope
import is only worth deferring if its *marginal* cost is measured, not its
attributed one.

Where the time actually goes is pydantic building validation schemas at class
creation: 209 model classes reachable from `cli.py`, with `config.schema`,
`backtest.models`, and `safety.models` the largest. `ConfigDict(defer_build=True)`
measures at 74% off class creation (200 synthetic models: 178 ms → 46.5 ms),
with the deferred work costing 0.29 ms on a model's first validation and nothing
after. On this codebase that is roughly a quarter of startup.

Deciding it: 128 of the 129 model classes inherit `BaseModel` directly, so there
is no shared base to set the option on once. It means either editing 128 class
bodies across every domain including `config`, `safety`, `risk`, `brokers`, and
`execution`, or introducing a base class and rewiring all of them. It also moves
a malformed model from an import-time error to a first-use error, which is the
wrong direction for this project unless the suite is known to construct every
model.

The `cli_bootstrap.py` pre-router is not the lever either way. It stays narrow
for its own reason: the four configless commands must run with no config loaded
and no third-party import on the path.

### `safety/policy.py` claimed an enforcement it did not have — `cleanup`

The module header read: the invariants are "surfaced in the CLI and asserted
against by the trust checkers, so the promises made to users and the promises
made in code cannot silently diverge."

Neither half was true. `HARD_RULES` has no importers anywhere in `src/`,
`tests/`, or `scripts/`; no CLI command reads it — `atlas --help` carries its own
separately worded safety blurb; no checker asserts it; and the module is not
exported from `safety/__init__.py`. The one thing that references it is a comment
in `execution/order_router.py` quoting a rule verbatim.

**Decided: corrected the header, kept the constant.** Quoting a canonical wording
instead of paraphrasing it is worth something, and the six rules are the subset
short enough to quote — the enforced set is the ten invariants in the governance
document. But a safety file that overstates its own enforcement is worse than one
that claims nothing, because it reads like a gate to the next person looking for
one. The header now says outright that nothing reads it, and names where each
rule is actually enforced.

## What the audit did change

For context on the boundaries above, the same pass fixed: a risk gate that
stopped rejecting when portfolio equity was non-finite; a review pack that
discarded the evidence it was handed; a reconcile failure that left no trace
while its report claimed otherwise; and `can_submit` reporting ready for brokers
the registry disables. It also added structural tests for the provider/execution
boundary, the set of modules that may reach a broker, and the credential paths
that must stay untracked.
