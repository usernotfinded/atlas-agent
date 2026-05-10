# Atlas Agent Security Policy

This document defines vulnerability reporting, trust boundaries, and hardening guidance for **Atlas Agent**.

Atlas is a real AI trading framework with backtesting, paper trading, and gated live trading. Security-critical invariants are:

- live trading is not default
- no direct AI-to-broker execution
- `RiskManager` is mandatory
- live approvals are mandatory by default
- kill-switch gating must be respected
- rejected orders must be auditable
- secrets must not be logged or committed

## 1. Vulnerability Reporting

Atlas Agent does **not** run a bug bounty program.

Report security issues privately through:

- GitHub Security Advisories (private): <https://github.com/usernotfinded/atlas-agent/security/advisories/new>
- If GHSA is unavailable, contact the maintainer privately on GitHub: <https://github.com/usernotfinded>

Do **not** open public issues for vulnerabilities. Do **not** post real credentials, account identifiers, or sensitive strategy data.

### Required report details

- **Title and severity:** concise issue title plus CVSS rating (if available).
- **Affected component:** exact file path and line range (example: `src/atlas_agent/execution/order_router.py:47-146`).
- **Environment:** commit SHA, OS, Python version, and relevant runtime mode (`paper` or `live`).
- **Reproduction:** step-by-step PoC against `main` or latest release.
- **Impact:** which trust boundary was crossed (for example, `RiskManager` bypass, approval bypass, kill-switch bypass, or secret leakage in logs/artifacts).

## 2. Trust Model and Security Boundaries

### 2.1 Operator model

- Atlas is designed for a trusted operator workflow, not multi-tenant isolation.
- If multiple users/systems share a host, isolation must be enforced at OS/container/network level.
- Exposing control surfaces publicly without external auth and network controls is a deployment risk, not an in-app auth boundary.

### 2.2 Untrusted AI output

- Provider output is advisory and untrusted (`src/atlas_agent/providers/base.py`, `docs/providers.md`).
- AI decisions are parsed and validated before execution (`src/atlas_agent/ai/decision_schema.py`, `src/atlas_agent/ai/signal_parser.py`).
- AI providers do not execute broker calls directly. Broker execution is routed through deterministic execution modules.

### 2.3 Mandatory order execution path

All order flow is expected to pass through:

1. Decision proposal (strategy/provider output)
2. `RiskManager.validate_order(...)` (`src/atlas_agent/risk/manager.py`)
3. live-mode gate checks (`AtlasConfig.live_disabled_reasons()` in `src/atlas_agent/config.py`)
4. manual live approval via `ApprovalManager` (`src/atlas_agent/execution/approval.py`) when mode is `live`
5. `Broker.place_order(...)` via `OrderRouter` (`src/atlas_agent/execution/order_router.py`)
6. audit/event logging (`src/atlas_agent/execution/audit.py`, `src/atlas_agent/events/log.py`)

If any gate fails, orders must be rejected or moved to pending approval instead of being sent to a live broker.

### 2.4 Risk, approval, and kill-switch controls

`RiskManager` enforces deterministic checks, including:

- daily loss, trade frequency, order notional, position size, and portfolio exposure limits
- confidence threshold checks
- symbol allowlist/blocklist checks
- duplicate-order protection
- live stop-loss requirement (when enabled)
- market-hours enforcement (when enabled)
- leverage blocking by default policy
- kill-switch rejection through config (`KILL_SWITCH_ENABLED`)

Live execution requires explicit safe state, including:

- `TRADING_MODE=live`
- `ENABLE_LIVE_TRADING=true`
- valid `LIVE_BROKER`
- `ORDER_APPROVAL_MODE` compatible with live approvals (`manual_live` default)
- kill switch not enabled

Pending live approvals are written as JSON files with expiry (`pending_orders/*.json`) and must be explicitly approved before live placement.

### 2.5 Auditability and secret redaction

- Audit records are written to `audit/audit.jsonl` (`AuditLogger`).
- Event records are written to `events/YYYY-MM-DD.jsonl` (`EventLogger`) and schema-validated.
- Redaction strips secret-like keys and token-like strings before persistence.
- Event doctor and memory doctor commands detect schema drift and likely secret leaks (`atlas events doctor`, `atlas memory doctor`).

### 2.6 Adapter boundaries

- Every broker integration must implement `Broker` (`src/atlas_agent/brokers/base.py`).
- Every AI provider integration must implement `AIProvider` (`src/atlas_agent/providers/base.py`).
- New adapters must preserve risk/approval/kill-switch/audit boundaries and must not create direct side channels that bypass `OrderRouter`.

## 3. Out of Scope / Non-Vulnerabilities

The following are generally not treated as security vulnerabilities by themselves:

- strategy or model quality issues that do not cross a security boundary
- expected live rejection when gates are not fully enabled
- running with intentionally restrictive or intentionally permissive operator configuration, when behavior matches documentation
- public deployment without external network/auth hardening
- reports requiring existing trusted write access to local operator files or environment
- claims about a single tool-level control that do not bypass the actual execution boundary (`RiskManager` + live gates + approval + broker adapter path)

## 4. Deployment Hardening Best Practices

### Secrets and credentials

- Keep provider keys, broker keys, Telegram token, and notification tokens in environment variables or a secret manager.
- Never commit secrets to git.
- Never place secrets in memory files, reports, or routine artifacts.
- Use guarded git sync flow (`src/atlas_agent/routines/git_sync.py`) when automating commits.

### Runtime hardening

- Prefer dedicated runtime users and least privilege on VPS/container hosts.
- Use network controls (VPN, firewall, private ingress) for remote control planes.
- Keep `paper` mode as default and promote to `live` only after explicit risk review.
- Validate workspace and safety gates before continuous runs:
  - `atlas validate`
  - `atlas risk check`
  - `atlas status`

### Telegram/control plane

- Treat Telegram as operator control input, not as an execution bypass.
- Require `TELEGRAM_ALLOWED_USER_IDS`.
- Never print bot tokens or broker/provider credentials.

## 5. Disclosure Process

- Coordinated disclosure target: up to 90 days, or until a fix is released.
- Progress updates happen in the private GHSA thread (or agreed private channel).
- Reporter credit is optional and provided only with consent.

## 6. Security Regression Checks

Run these checks for security-sensitive releases and execution-path changes:

```bash
pytest
python -m atlas_agent.cli --help
atlas --help
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol BTC-USD
atlas run-once --mode paper
atlas run-once --mode live
```

Expected safety behavior: `atlas run-once --mode live` must fail safely unless explicit live configuration, credentials, risk checks, and approval preconditions are satisfied.
