# L3 Bounded Live Autonomy — Design

> **Status:** design only. L3 is **not implemented**, not enabled, and not
> authorized by this document. Nothing here permits live trading, live submit,
> broker execution, or unattended operation. `atlas run --mode live` remains
> fail-closed.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss.

## What L3 is, in the ladder's own words

[Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) defines
L3 as "a tightly bounded research concept requiring per-order human approval,
strict RiskManager limits, explicit opt-in, and active operator oversight".

Two things follow that are easy to lose. L3 is **not** unattended trading — it
keeps per-order human approval, so the human is in the loop for every order. And
L3 is **not** L4: broader execution authority requires external legal, security,
operational, risk, broker-adapter, and regulatory review by qualified parties,
"not by self-assessment".

## Where the four requirements stand

| Requirement | State | Evidence |
|---|---|---|
| Per-order human approval | Exists | `execution/approval.py`; `OrderRouter` allowlists exactly `manual_live` and parks unapproved orders as pending |
| Strict RiskManager limits | **Built** | `max_daily_loss` (both units), `max_trades_per_day`, and order leverage now evaluate; previously all three refused nothing |
| Active operator oversight | **Verified and pinned** | The deadman blocks a hung cycle; `tests/safety/test_deadman_blocks_a_hung_cycle.py` pins the composition and its wiring |
| Explicit opt-in | **Missing** | Live submit has one; autonomy does not |

Three of the four hold. This document is about the fourth.

Two supporting properties the external gates also name are already enforced:
autonomous layers cannot write configuration, so a loop cannot raise the limits
it runs under; and reverting to paper closes live submit while keeping the
operator's broker settings.

## The opt-in

The design is not new. `brokers/resolver.py` already carries a live-submit opt-in
worth copying rather than reinventing: a JSONL record holding `opt_in`,
`broker_id`, `created_at`, and a `config_fingerprint`, where the fingerprint is a
digest of the limits the consent was given under. If those limits change, the
fingerprint stops matching and the opt-in is refused as
`opt_in_config_changed`.

That property is the whole point, and it is what makes an opt-in more than a
checkbox: **consent is bound to the bounds**. An operator who agrees to
autonomous proposals capped at $500 has not agreed to $50,000, and raising the
cap must revoke the consent rather than inherit it.

An L3 opt-in should be a second, separate record with its own fingerprint:

- **Separate**, because enabling live submit and enabling autonomy are different
  decisions. Reusing the live-submit record would mean an operator who opted into
  manual live submission had silently opted into autonomy too.
- **Fingerprinted over the autonomy-relevant limits** — the daily loss ceilings,
  trades per day, leverage, max order notional, allowed symbols and sides, and
  the approval mode. Each of those is now enforced, which is what makes
  fingerprinting them meaningful; before, the digest would have covered numbers
  that bounded nothing.
- **Refused when absent**, like the live-submit record: no opt-in file means no
  autonomy, never "assume yes".

## Why this document is not an implementation

The opt-in gate has no caller until the L3 runtime path exists. Landing it alone
would produce a fail-closed guard that nothing invokes — the exact shape this
project has already been bitten by. `brokers/guards.py` held two such guards, and
while nothing called them one of them drifted: `guard_sync` came to admit `paper`
as a live sync broker, and no test noticed because no caller exercised it.

So the opt-in and the path that consults it should land together, as one
reviewable candidate, with the opt-in refused by default and the path fail-closed
without it.

## What L3 must not become

- **Not unattended.** Per-order human approval is part of the definition, not a
  configurable step. A future tier that removes it is L4 and needs the external
  gates.
- **Not self-raising.** The limits are per-deployment and autonomous logic cannot
  write configuration. That boundary is enforced by
  `tests/architecture/test_autonomous_layers_cannot_write_config.py`.
- **Not silent.** Every gate failure on the submit path writes to the audit
  chain, which is what the external gates mean by "tamper-evident audit logging
  for every autonomous decision".
- **Not one-way.** Reverting to paper closes live submit and keeps the
  configuration, so stepping back is a decision rather than a re-setup.

## Open questions for a maintainer

1. **Does the deadman need to bind the L3 path explicitly?** An absent heartbeat
   reads as fresh, so the deadman is inert on any path that evaluates the kill
   switch without recording a heartbeat. The L3 path must record one, or the
   asymmetry recorded in
   [safety-invariant-audit-followups.md](development/safety-invariant-audit-followups.md)
   has to be closed first.
2. **What is the oversight signal?** "Active operator oversight" is stated as a
   requirement but not defined. A deadman proves the agent is alive; it does not
   prove a human is watching.
3. **Scope of the first cut.** One symbol, one side, one broker, paper-validated
   first — the ladder's own language is "tightly bounded", and the narrower the
   first cut, the more the review is worth.
