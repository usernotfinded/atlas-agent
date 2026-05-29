# CLI Command Compatibility Contract

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Purpose

This document defines the CLI command compatibility contract for Atlas Agent after the post-v0.5.7 CLI refactor. Its goal is to guard public command families against accidental parser removal or public docs drift during future refactors. It does **not** guarantee a stable API forever, and it does **not** prove trading safety.

The contract is enforced by a local, parser-only check script (`scripts/check_cli_command_compatibility.py`) that introspects `argparse` structures without executing command handlers, calling providers, or loading credentials.

## What this contract is

- A parser-level inventory of expected top-level commands and subcommands.
- A regression guard: if a refactor removes or renames a command listed here, the check fails.
- A documentation anchor so that public docs, release checklists, and research workflows stay synchronized with the actual CLI surface.

## What this contract is not

- A guarantee that every command works correctly at runtime.
- A proof that live trading, provider execution, or broker execution are safe.
- A runtime safety test; it does not exercise handlers, risk gates, or approval flows.

## Command classifications

### Public / stable enough to protect

These command families are used in public docs, demos, and release checklists. They are guarded against accidental removal:

- `init`, `setup`, `validate`, `configure`
- `config` (show, get, set, unset, migrate, doctor, paths, edit, check)
- `model` (list, providers, current, set, configure)
- `workspace` (show, set, clear, doctor)
- `status`, `plan`
- `run`, `run-once`
- `update` (check, status, apply, rollback, config)
- `providers` (list)
- `broker` (list, sync, opt-in, opt-out)
- `backtest` (run)
- `agent` (run, status, plan, learn, reflect)
- `skills` (list, propose, create-from-journal, improve, approve, archive, show, diff)
- `memory` (ingest, search, rebuild-index, summarize, nudge, doctor)
- `user` (show, remember, forget, update-from-reflection)
- `discipline` (show, validate, set, generate, reset, setup, doctor)
- `telegram` (run, test, kill, resume, heartbeat)
- `deploy` (vps, systemd, docker, serverless)
- `routine` (run, unlock, status)
- `scheduler` (run)
- `report` (daily)
- `portfolio` (show)
- `risk` (check, status)
- `kill` (status, soft-pause, cancel-all, flatten-all, lock, reset, heartbeat, plan, execute-plan)
- `kill-switch` (enable, disable, status)
- `heartbeat`
- `approve-order`
- `submit-approved-order`
- `research` — see the dedicated Research section below
- `notify`, `git-sync`, `schedule`, `events`, `replay`, `demo`, `audit`, `dashboard`

### Experimental / internal / research-only

Research commands are configless by default and do not call providers, load credentials, or authorize live trading. They are part of the supervised research workflow and are protected so that release-checklist commands and sandbox workflows do not break silently.

Research commands include:

- Core: `run`, `list`, `show`, `plan`, `summary`, `verify`, `evaluate`, `check-artifacts`, `timeline`, `providers`
- Prompt / sandbox: `prompt`, `sandbox`, `sandbox-list`, `sandbox-show`, `sandbox-validate`, `sandbox-replay`
- Provider response chain: `import-provider-response`, `provider-targets`
- Standard families (auto-generated from `command_specs.py`): `provider-plan`, `provider-execution-dry-run`, `provider-execution-state`, `provider-execution-audit`, `provider-execution-readiness`, `provider-preflight-freeze`, `provider-opt-in-policy`, `provider-credential-boundary`, `provider-payload-preview`
- Extended chain: `provider-response-intake-policy`, `provider-request-response-pairing`, `provider-response-schema-contract`, `provider-response-review-result`, `provider-execution-unlock-state`, `provider-adapter-interface-contract`, `provider-adapter-disabled-smoke`
- Mock response chain: `provider-mock-response-simulate`, `provider-mock-response-import-candidate`, `provider-mock-response-review-sandbox`, `provider-mock-response-trust-decision-blocker`, `provider-mock-response-final-safety-seal`
- Safety dossier: `provider-safety-dossier`
- Release readiness: `release-candidate-readiness`, `release-candidate-cutover-dry-run`
- Legacy / shims: `simulate-provider`, `review-response`, `dossier`, `mock-response-final-safety-seal`

These commands are local-only artifacts. They may evolve, but their parser names must remain present unless explicitly deprecated in a minor/major release.

### Configless commands

Configless research commands skip full `AtlasConfig` loading and do not read secrets. They are defined in `src/atlas_agent/research/command_specs.py` via `CONFIGLESS_RESEARCH_COMMANDS`.

Other configless or lightweight commands include:

- `validate`
- `status`
- `plan`
- `setup`
- `configure`
- `config check`
- `workspace doctor`
- `model list`
- `broker list`
- `providers list`
- `risk check`
- `risk status`
- `kill status`
- `kill-switch status`
- `portfolio show`
- `backtest run` (when given `--data`)

### Safety-sensitive commands

These commands can affect trading state, broker opt-in, or kill-switch posture. They require explicit user action and are never enabled by default:

- `run` (accepts `--mode live`)
- `run-once` (accepts `--mode live`)
- `broker opt-in`
- `approve-order`
- `submit-approved-order`
- `kill execute-plan`
- `kill-switch enable`
- `kill-switch disable`

### Commands that must remain disabled / safe by default

- `run --mode live` requires explicit live trading enablement and risk checks.
- `run-once --mode live` requires explicit live trading enablement.
- `broker opt-in` requires explicit user confirmation.
- `submit-approved-order` without `--dry-run` requires an approved order and still fails closed at `can_submit=false`.
- Provider execution remains locked by default; no provider call is made without manual unlock steps.
- Broker execution remains blocked unless explicit opt-in gates pass.

## Machine-readable contract

The canonical contract lives at:

```
tests/fixtures/cli_command_contract.json
```

It contains:

- `version`: schema version
- `package_series`: the development series this contract tracks
- `top_level_commands`: expected top-level parser names
- `subcommands`: expected subcommands for major families
- `configless_research_commands`: documentary list of configless research commands
- `safety_sensitive_commands`: commands that can affect trading or safety posture
- `forbidden_default_behaviors`: behaviors that must not be present in the check or in defaults

## Check script

Run the check locally:

```bash
python3.11 scripts/check_cli_command_compatibility.py
python3.11 scripts/check_cli_command_compatibility.py --json
```

The check script:

- Imports `atlas_agent.cli.build_parser` and inspects argparse structures.
- Compares actual parser commands against the JSON contract.
- Verifies that every configless research command from `command_specs.py` exists in the parser.
- Fails closed (exit code `2`) if any expected public command is missing.
- Never calls providers, brokers, or network endpoints.
- Never reads `.env` or live credentials.
- Never modifies workspace files.
- Does not use `shell=True`.

## Safety assertions

- **Live trading remains disabled by default.** No refactor may change this without an explicit release decision.
- **Provider execution remains locked.** The compatibility check is parser-only and does not exercise provider paths.
- **Broker execution remains blocked unless explicit opt-in gates pass.** The check does not invoke brokers.
- **No credentials are loaded by the compatibility check.** The script only inspects `argparse` objects.

## Versioning

This contract is versioned independently of the package version. Update the contract when:

- A new public command is added.
- An existing public command is renamed or removed (requires a minor/major release).
- The research command spec layer changes.

Current contract version: `1`  
Package series: `0.5.8rc1`
