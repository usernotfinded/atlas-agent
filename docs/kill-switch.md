# Kill Switch Runbook

Atlas Agent supports three kill-switch modes, plus a dead man's switch for automatic protection.

## Modes

- `soft`: blocks new orders. Existing positions remain open.
- `cancel`: `soft` + cancels working/pending broker orders.
- `flatten`: `cancel` + attempts to close all open positions.

`flatten` can use:

- `market` close strategy
- `aggressive_limit` close strategy (configured bps from reference price)

## CLI Commands

Enable:

```bash
atlas kill-switch enable --mode soft --reason "manual pause"
atlas kill-switch enable --mode cancel --reason "news risk"
atlas kill-switch enable --mode flatten --reason "emergency flatten"
```

Disable:

```bash
atlas kill-switch disable
atlas kill-switch disable --require-2fa --totp 123456
```

Rules:

- disabling after `flatten` requires TOTP
- set TOTP secret with `ATLAS_TOTP_SECRET` (base32)

Status:

```bash
atlas kill-switch status
```

Manual heartbeat:

```bash
atlas heartbeat --source cli --actor user:local
```

## Telegram Control Surface

Current command surface (wired through control-plane helpers/CLI integration):

- `/kill`
- `/kill flatten`
- `/resume <totp>`
- `/heartbeat`

## Dead Man's Switch

Environment variables:

```bash
DEADMAN_TIMEOUT_MINUTES=15          # 0 disables deadman
DEADMAN_ACTION=soft                 # soft|cancel|flatten
DEADMAN_AUTO_RESET=true             # reset timer on user interaction
DEADMAN_ACTIVE_OUTSIDE_MARKET=false # if false, only active in market open state
DEADMAN_CHECK_INTERVAL_SECONDS=5
DEADMAN_FLATTEN_STRATEGY=market     # market|aggressive_limit
DEADMAN_FLATTEN_BPS=25
```

Heartbeat sources:

- explicit CLI heartbeat command
- Telegram `/heartbeat`
- auto-reset from user interactions when `DEADMAN_AUTO_RESET=true`

If timeout expires in active window, deadman enables kill switch using configured action and emits notifications through configured gateways.

## Operational Drill (Recommended)

Run this on paper mode before any live rollout:

1. Start with no kill switch active.
2. Trigger `soft` and verify new orders are rejected.
3. Escalate to `cancel` and verify working-order cancellation path executes.
4. Escalate to `flatten` and verify open positions close (or partial-success report is produced).
5. Attempt disable without TOTP after flatten and confirm refusal.
6. Disable with valid TOTP and verify status returns disabled.
7. Simulate deadman timeout and verify configured action triggers automatically.

## Recovery After Accidental Flatten

1. Keep kill switch enabled while assessing exposure.
2. Verify all broker-side fills/cancels and compare with Atlas audit/events.
3. Reconcile portfolio state and journal.
4. Disable kill switch only after explicit operator review (and TOTP when required).
5. Resume with paper mode first, then re-enable live mode only after safety checks.

## Notes

- Kill-switch transitions are idempotent.
- Repeated `flatten` requests do not intentionally duplicate close actions once flat.
- Legacy `memory/kill_switch.enabled` is still respected for backward compatibility.
