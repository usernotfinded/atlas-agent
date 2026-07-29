# Safety Invariant Audit — Follow-ups

An audit walked the ten hard invariants in
[Bounded Live Autonomy Governance](../bounded-live-autonomy-governance.md) and
the defect classes this project has fixed before, asking of each whether the
code enforces what the documentation promises. Later passes asked the same
question of things the governance document does not cover — what the CLI reports
to an operator, and what its error envelopes promise — and those findings are
recorded here too, because they are the same kind: a claim nothing checks.

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

### The approval gate failed without an audit record — `semantics_change`

Hard invariant 8 says the audit hash-chain records "**all** gate failures, risk
rejections, kill-switch transitions, and submit attempts".
`docs/release-checklist.md` enumerated the reason codes for which
`live_submit_blocked` is emitted, and that list started at the HMAC-approval
gate. The code followed the checklist, so every gate before it returned blocked
and wrote nothing:

```
not approved             blocked_reason=not_approved         NO AUDIT RECORD
already submitted        blocked_reason=already_submitted    NO AUDIT RECORD
terminal state           blocked_reason=terminal_state       NO AUDIT RECORD
```

`not_approved` was the one that mattered: invariant 7 makes approval mandatory,
and the failure of that gate — the event an operator searches the chain for when
asking whether anything tried to submit without approval — left no trace.

**Decided: the invariant wins, and all thirteen now emit.** The two documents
disagreed and the earlier note left the choice open. The external gates for
bounded live autonomy settle it: they require "tamper-evident audit logging for
every autonomous decision", so under L3 the checklist reads as an incomplete list
of things to verify rather than a narrower contract. The same probe that found
the gap now shows an audit line for each.

The checklist enumeration is regenerated from the emitters and
`tests/audit/test_live_submit_blocked_event_set.py` holds the two together in
both directions, so the list cannot fall behind the code again.

### A missing heartbeat does not fail closed — `semantics_change`

`safety/heartbeat.py::is_expired` reports a corrupt heartbeat as expired and an
absent one as fresh. The asymmetry is deliberate — a first run has no dead agent
to detect — but `HeartbeatManager` cannot tell "never recorded" from "recorded
and then deleted", so deleting the file has the same effect as never writing
one. The weaker failure is treated more permissively than the stronger one.

**Decided: kept.** Making an absent heartbeat expire needs a marker written at
first start, which adds a second file the deadman depends on — and a deadman
with two failure modes is not obviously safer than one with a documented gap.

The original wording of this entry said the gap stays unreachable because
"`agent/runner.py` records a heartbeat at the start of every cycle, before
`KillSwitch.evaluate` can run". `runner.py` does record, but it never calls
`evaluate` — `agent/loop.py` does, on every tool call, using the switch the
runner hands it. The conclusion holds and the mechanism is a composition across
two modules, which is what
`tests/safety/test_deadman_blocks_a_hung_cycle.py` now pins, including the
wiring that keeps the recorded switch and the evaluated switch the same object.

The consequence worth carrying forward: because an absent heartbeat reads as
fresh, the deadman is inert on any path that evaluates without ever recording —
there is no stale file to age out. Any L3 path that consults the kill switch must
record a heartbeat too, or it inherits a deadman that cannot fire.

## Open items

### Two parallel safety subsystems, with the CLI split across both — `architecture`

This is the root cause behind several findings that looked unrelated. Atlas
carries two implementations of each safety mechanism, holding separate state,
and the commands are split between them with nothing saying so.

| Mechanism | `.atlas/safety/` subsystem | `memory/` subsystem |
|---|---|---|
| Kill switch | `AdvancedKillSwitch`, `kill_switch.json`, modes `soft_pause`/`cancel_all`/`flatten_all`/`locked_down` | `KillSwitchController`, `kill_switch_state.json`, modes `soft`/`cancel`/`flatten` |
| Written by | `atlas kill` | `atlas kill-switch`, `atlas telegram kill` |
| Heartbeat | `HeartbeatManager`, `heartbeat.json` | `deadman_heartbeat_path`, `deadman_heartbeat.json` |
| Written by | `atlas kill heartbeat`, `agent/runner.py` | `atlas heartbeat`, `atlas telegram heartbeat` |
| Consumed by | `AdvancedKillSwitch.evaluate()`, called from `agent/loop.py` on every tool call | `KillSwitchController.status()`; `DeadmanSwitch.tick`, which nothing constructs |

Four consumers were found reading one of the two kill switches. Each was wired
to whichever subsystem was nearest when it was written, and none of them was
findable from any of the others:

| Consumer | Read | Consequence | State |
|---|---|---|---|
| `_resolve_can_submit` | `memory/` only | `atlas kill flatten-all` left `can_submit` true | Fixed |
| `AdvancedKillSwitch.evaluate` (the agent loop) | `.atlas/safety/` only | `atlas kill-switch enable --mode flatten` did not stop the loop | Fixed |
| `_cmd_broker_opt_in` | `memory/` only | live-submit authority granted while `atlas kill` armed | Fixed |
| `_display_live_status` | `memory/` only | reported "live submit possible" against the resolver's own answer | Fixed |

The state read is now `advanced_kill_switch_mode` in `safety/kill_switch.py`,
shared by all of them. That placement is the lesson rather than a tidy-up: every
copy that grew next to its own caller grew against a single switch.

The heartbeat mechanism has the same split and one open defect from it. The live
deadman reads only the `.atlas/safety/` heartbeat, so `atlas heartbeat` and
`atlas telegram heartbeat` feed nothing that runs: `DeadmanSwitch`, the only
reader of the file they write, is never constructed anywhere in `src/`. It is
pinned by `tests/safety/test_heartbeat_commands_feed_the_live_deadman.py` with
two strict xfails.

Only one of the five left a live path open. `_resolve_can_submit` is the gate
the submit funnel consults, so its blind spot was the real fail-open: `atlas
kill flatten-all` and live submission stayed possible. The other three
kill-switch consumers failed to refuse while a downstream gate still held — the
loop kept iterating but could not have placed a live order, the opt-in granted
authority unusable while the stop held, and the status display only misreported.
That ordering is worth keeping straight, because "four consumers were wrong" and
"four ways to trade through a kill switch" are very different claims and only
the first is true.

The heartbeat defect points the other way entirely. It is **fail-closed**: the
agent stops when it should keep running, costing false confidence and
availability rather than opening anything.

Both heartbeat commands print their path and exit 0, which is why neither
surfaced:

```
$ atlas heartbeat
Heartbeat recorded: memory/deadman_heartbeat.json     # deadman still blocked
$ atlas kill heartbeat
Heartbeat recorded.                                   # deadman cleared
```

The heartbeat half is deliberately not fixed by "write both files". A remote
`/heartbeat` from a phone that silences an agent-liveness deadman lets a human
mask a hung agent, and the deadman exists to catch the agent simply stopping —
which is not something an operator is in a position to vouch for. `atlas kill
heartbeat` already writes the live file, so the precedent cuts both ways. It is
a decision about who may assert liveness, not a wiring bug, and it wants a
maintainer.

Unifying the two subsystems is the larger question underneath. What the split
costs beyond these five is the part worth weighing: every future safety
mechanism has two places to be wired, and a reviewer checking one has no signal
that the other exists.

### The emergency flatten cannot be reached by escalating — `semantics_change`

`atlas kill-switch enable --mode flatten` is the only command that closes live
positions through a broker. It works as a first action and fails as a second
one, which is the order an operator actually uses it in.

`_broker_for_kill_switch` obtains its broker from `_broker_for_mode`, which for
live mode requires `resolution.status.can_submit`. That predicate includes "kill
switch is normal". So arming the switch at all removes the broker from the only
path that can flatten with it. Measured on a workspace with every other gate
satisfied:

```
step 1, switch normal      AlpacaBroker
step 2, after --mode soft  (None, 'live Alpaca sync is ready; submit kill switch is soft')
```

The documented ladder walks straight into it. `docs/kill-switch.md` lists
`soft-pause`, `cancel-all`, `flatten-all` in that order under "Manual triggers",
and `DEADMAN_ACTION` defaults to `soft` — so an operator arriving at a tripped
deadman and asking to be flat is already in step 2.

Gating a flatten behind a *submit* predicate is backwards, and this codebase has
already ruled on it twice. `RiskManager.should_check_limits` exempts
risk-reducing orders so a breached limit cannot trap a position open, and
`safety/executor.py` says it outright:

> Only locked_down blocks: the milder modes are the very reason this plan exists
> (a cancel_all plan is *supposed* to run while the switch says cancel_all).

The same rule applied here gives the fix: the kill switch's broker should be
resolved on "is a broker configured and are its credentials present", not on
"may we submit new orders", and refuse at `locked_down` as the executor does.

It is recorded rather than done because the change is to what the resolver hands
out while its own guard is armed, and `bounded-live-autonomy-governance.md`
reserves exactly that question — "confirm every adapter implements fail-closed
behavior and cannot bypass resolver guards" — for external broker-adapter
review. `resolve_execution_broker` currently returns `execution_broker=None`
alongside `can_submit=False`, so the fix means a second resolution path, and a
second way to obtain a live broker handle is not something to add by
self-assessment.

One honest note on scope. Making `atlas kill` close the live path widened this:
its modes now also refuse the broker, so `atlas kill soft-pause` followed by
`atlas kill-switch enable --mode flatten` is newly affected. The exposure is the
cross-surface sequence only — `atlas kill` never flattened through a broker
itself, it sets a mode the agent loop consumes — and it buys the runbook's own
commands actually closing live submit. Net positive, but both halves belong on
the record.

### Four config fields keep their valid values in a comment — `contract_change`

`config/schema.py` declares these as plain strings:

```python
order_approval_mode: str = "manual_live"  # auto_paper, manual_live, disabled_live
auto_check: str = "daily"                 # daily, weekly, never
transport: str = "disabled"               # disabled, dry_run, slack
trading_mode: str = "paper"               # backtest, paper, live
```

Three of the four have already taken a value from the wrong domain, each found
and fixed separately before the pattern was visible:

- `order_approval_mode` received `"telegram"` from config migration, because
  `messaging` was mapped to it.
- `auto_check` received `"stable"` from the setup wizard, because
  `update_channel` was written to it.
- `trading_mode` accepts `"banana"` from `atlas config set` today. The
  per-field validation added with that fix cannot catch it: the field's type is
  `str`, and `"banana"` is a string.

`Literal[...]` would have caught all three at the point of writing, and would
make `validate_raw_value` reject them with no further work.

Deciding it: tightening these types is not only a schema change, it needs a plan
for data already in the wild. Every workspace configured by the wizard before the
`update_channel` fix has `auto_check = "stable"` in its `config.toml`, so a
`Literal` on that field would refuse to load exactly the configs the earlier bug
produced — turning a harmless stale value into a workspace that will not start.
Whoever takes this needs a coercion or repair step first, not just the type.

Nothing is currently at risk from the stale values: `auto_check` is read by
nothing, and an unrecognised `trading_mode` fails closed at the resolver, which
answers `unknown_mode`.

### Two CLI refusal-code conventions are live at once — `contract_change`

`cli_io.emit_cli_error` returns exit 2 and explains why in a comment: "exit 1 is
what an uncaught Python traceback produces. Reserving a distinct code lets
callers and CI tell 'the command ran and said no' apart from 'the command
crashed'."

The research command group does not follow it. `research dossier`,
`research show`, `research backtest-proposal`, and the whole
`release-candidate-*` and `provider-safety-dossier-*` surface answer a clean,
structured refusal with exit **1** — the code the comment reserves for a crash.
Each emits a well-formed `{"ok": false, "status": ...}` envelope while doing so.

So a caller following the documented rule reads every research refusal as a
crash, and cannot tell a missing artifact from a traceback. Both conventions are
long-standing and internally consistent within their own halves.

Deciding it: the exit codes are part of the CLI surface that
`scripts/check_cli_command_compatibility.py` and the trust contracts pin, so
moving the research group to 2 is a contract change affecting roughly 170
subcommands. Leaving it means the comment in `cli_io.py` describes one half of
the CLI. `tests/research/test_research_command_envelopes.py` deliberately
asserts only the property that holds under either — that the exit status agrees
with the envelope's `ok` — rather than settling this in a test written for
something else.

### Four commands exit 0 while reporting failure — `contract_change`

Running all 175 `atlas research` subcommands against a missing artifact, 171
agree with their own envelope and four do not:

| command | envelope | exit |
|---|---|---|
| `provider-credential-boundary-summary` | `ok: false` | 0 |
| `provider-execution-chain-doctor` | `ok: false` | 0 |
| `provider-opt-in-policy-summary` | `ok: false` | 0 |
| `provider-preflight-freeze-summary` | `ok: false` | 0 |

Each reports the artifact is missing — `provider-execution-chain-doctor` says
`blocking_reasons: ["research_artifact_not_found"]` — and returns success. A
caller reading the exit code sees success; a caller parsing the JSON sees
failure. Shell pipelines and CI read the exit code.

This is an inconsistency inside a command family rather than a convention:
`provider-opt-in-policy-show` reports the same missing artifact with exit 1
while `provider-opt-in-policy-summary` reports it with exit 0.

Deciding it: there is a defensible reading for `-doctor` and `-summary`, that
`ok` describes the subject's health rather than the command's success — the
doctor ran fine, the patient is sick. It is weaker here because
`research_artifact_not_found` means there is no patient, and because the
`-show` siblings disagree. Either way, changing four exit codes is a change to
the pinned CLI surface. The four are strict `xfail` in
`tests/research/test_research_command_envelopes.py`, so whichever way it is
decided, the marker has to be removed deliberately.

### `atlas risk check` shows the operator a limit that does not exist — `semantics_change`

The command prints exactly three lines:

```
kill_switch=False
max_position_size=100.0
max_trades_per_day=5
```

The first two are enforced. `max_trades_per_day` is configured, defaults to 5,
and `RiskLimits` has no such field — 100 trades in a day evaluate `allowed=True`
with zero violations. An operator running the command that reports their risk
posture is told a limit exists that nothing applies.

It is the readiest of the unenforced limits to fix: `trades_today` is already
incremented by the paper broker and already reaches every evaluation, so a rule
is all that is missing. It is also the only one with a second option — stop
printing it, which removes the false claim without touching the gate.

Deciding it: `CAND-033`. Pinned as a strict `xfail` in
`tests/risk/test_declared_limits_are_wired.py`.

### Two of invariant 5's six limits are not enforced — `semantics_change`

Hard invariant 5 states that `RiskManager` enforces "hard-coded limits on
position size, notional, daily loss, exposure, symbols, and leverage". Four of
those six have rules in `risk/manager.py`. Two do not:

```
baseline, healthy portfolio          allowed=True  violations=[]
realized_pnl_today = -50% of equity  allowed=True  violations=[]
order leverage = 10x                 allowed=True  violations=[]
```

`max_daily_loss_pct` is declared in `RiskLimits` with a 2% default and read by no
rule. `OrderRiskInput.leverage` is populated from the order on both the paper and
the live-submit paths and read by no rule.

The daily-loss chain is a stub at both ends: `realized_pnl_today` travels from
`PortfolioState` through `PortfolioSnapshot` into every evaluation, and nothing
in `src/` ever increments it, so it is always zero. The plumbing was built for a
limit that was never written — `tests/test_risk_manager.py`'s helper still takes
`realized_pnl_today` and `leverage` parameters no assertion uses.

Leverage is narrower than it looks: no broker adapter forwards the field, and the
resolver's leverage gate checks the `allow_leverage` config flag rather than the
order, so with the safe default an order carrying `leverage=10.0` satisfies that
gate. Nothing acts on the value today.

Deciding it: `CAND-033` proposes the work.  Adding the daily-loss rule alone
would be a limit on a number nobody writes, so closing it means first deciding
where realized daily P&L is accounted — the paper broker's fills, the trade
journal, or a session boundary the caller resets. That is a portfolio-accounting
decision, not a risk-rule one. For leverage the question is whether to reject
leveraged orders at the gate or to stop carrying a field the system does not use.
`tests/risk/test_declared_limits_are_wired.py` states both as strict `xfail`
cases, so whichever way this goes, implementing it turns the marker into a
failing XPASS that has to be removed.

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

## What the audit did change

For context on the boundaries above, the same pass fixed: a risk gate that
stopped rejecting when portfolio equity was non-finite; a review pack that
discarded the evidence it was handed; a reconcile failure that left no trace
while its report claimed otherwise; and `can_submit` reporting ready for brokers
the registry disables. It also added structural tests for the provider/execution
boundary, the set of modules that may reach a broker, and the credential paths
that must stay untracked.
