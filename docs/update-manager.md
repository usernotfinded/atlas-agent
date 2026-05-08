# Atlas Update Manager

## Purpose

Atlas includes a conservative update manager for controlled software updates:

- `atlas update check`: discover whether a newer version is available.
- `atlas update status`: show current update state and safety readiness.
- `atlas update apply`: manually apply an update when safety gates pass.
- `atlas update rollback`: restore the previous version snapshot.
- `atlas update config`: set auto-check and auto-apply policy.

The update manager is designed for trading-system safety, not convenience-first unattended updates.

## Safety model

`atlas update apply` refuses by default when any blocker is present:

- live trading is enabled;
- broker has open positions;
- broker has pending orders;
- kill switch is unavailable;
- working tree has uncommitted changes.

`--force` can bypass blockers, but prints a clear warning and should be used only after explicit human review.

## Why auto-apply is disabled by default

Automatic code changes on a trading system are risky. Atlas defaults to:

- `auto_apply_enabled = false`
- `auto_check_schedule = off`

Even when auto-apply is explicitly enabled, Atlas still enforces safety checks and never auto-applies during live trading conditions.

## State file

Atlas persists updater state in:

`workspace/.atlas_update_state.json`

Tracked fields include:

- `current_version`
- `last_checked_at`
- `latest_version`
- `latest_source`
- `last_update_attempt_at`
- `last_successful_update_at`
- `previous_version`
- `previous_git_commit`
- `rollback_available`
- `auto_apply_enabled`

## Commands

### Check

```bash
atlas update check
```

Checks GitHub and/or PyPI sources when configured, without modifying files.

### Status

```bash
atlas update status
```

Shows stored update state plus current safety blockers/warnings.

### Apply

```bash
atlas update apply
atlas update apply --force
```

Behavior:

1. evaluate safety gates;
2. create a backup snapshot;
3. apply update (`git pull --ff-only` for git installs, pip upgrade for configured non-git installs);
4. run smoke check;
5. rollback automatically on failed apply/smoke-check.

### Rollback

```bash
atlas update rollback --yes
```

Rollback requires explicit confirmation. No rollback is performed if confirmation is missing.

## Configuration examples

```bash
atlas update config --auto-check daily
atlas update config --auto-check weekly
atlas update config --auto-check off
atlas update config --auto-apply on
atlas update config --auto-apply off
atlas update config --auto-check daily --auto-apply off
```

## Operational warning

Live trading systems should not update unattended. Keep updates manual, scheduled, and reviewed.
