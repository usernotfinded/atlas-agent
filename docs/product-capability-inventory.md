# Product Capability Inventory

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What this document is

This is a **complete capability inventory** for Atlas Agent `0.5.8rc1`. It exists so reviewers and maintainers can see, in one place:

- What capabilities exist
- What is partially implemented
- What is experimental
- What is disabled by default
- What is documentation-only
- What is missing
- What safety boundaries apply

This is **not** a marketing document. It does not claim profitability, trading correctness, real-money safety, or production readiness.

## How to read this document

This inventory is organized by capability group (e.g., Core workspace, Paper trading, Safety). Each row in a group table describes one capability and its current state.

- **Status** tells you whether the capability is fully implemented, partial, experimental, missing, etc. See the table below for exact meanings.
- **Public claim** tells you whether it is safe to mention the capability in public docs and outreach. `safe_to_claim` means yes; `do_not_claim` means it exists but should not be highlighted.
- **Notes** provide implementation details, safety boundaries, and caveats.

For the roadmap that turns these capabilities into prioritized work items, see the [v0.5.8 Gap Prioritization Plan](v0.5.8-gap-prioritization.md).

## How to read capability statuses

| Status | Meaning |
|---|---|
| `implemented` | Fully working in the current codebase. |
| `partial` | Works but with known limitations or MVP scope. |
| `experimental` | Early stage; may change or produce template output. |
| `disabled_by_default` | Exists but is off unless explicitly enabled by the user. |
| `docs_only` | Documented or tracked in artifacts, but has no runtime enforcement. |
| `missing` | Not implemented (may have a placeholder stub). |
| `deprecated` | Present but scheduled for removal. |

## How to read public claim levels

| Level | Meaning |
|---|---|
| `safe_to_claim` | Safe to mention in public docs and outreach. |
| `claim_with_limits` | Mention with explicit caveats about scope or readiness. |
| `internal_only` | Exists but should not be marketed or highlighted to reviewers. |
| `do_not_claim` | Do not mention in public docs or outreach. |

## Core workspace and configuration

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Workspace initialization | implemented | safe_to_claim | Template copy into local directory. No network. |
| Configuration management | implemented | safe_to_claim | Atomic TOML writes, secret redaction, env precedence. |
| Interactive setup wizard | implemented | safe_to_claim | Defaults to safe settings. Does not auto-enable live trading. |
| Discipline profile management | implemented | safe_to_claim | Validates forbidden phrases before agent loop starts. |
| Model provider selection | implemented | safe_to_claim | 15+ provider profiles. No provider is privileged. |
| Validation and readiness checks | implemented | safe_to_claim | Read-only local check. No network or broker calls. |

## Paper trading and simulation

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Paper workflow | implemented | safe_to_claim | Always available. No credentials required. Cash/position tracking enforced. |
| Backtest execution | partial | claim_with_limits | CSV-only, deterministic. Only `buy_and_hold` strategy wired. |
| Sample data generation | implemented | safe_to_claim | 15-bar deterministic fixture. No network. |
| Portfolio state and journal | implemented | safe_to_claim | Local Markdown/JSON state. No live broker sync in paper mode. |

## Research and artifacts

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Research session management | implemented | safe_to_claim | Deterministic provider is default. Perplexity implemented but not wired. |
| Research planning and evaluation | implemented | safe_to_claim | 20+ linked artifact types with hash validation. |
| Research artifact timeline and health checks | implemented | safe_to_claim | Local-only inspection. No provider or broker calls. |
| Provider safety dossier | implemented | safe_to_claim | Aggregates safety artifacts for release readiness. |
| Provider mock response workflow | implemented | safe_to_claim | Local mock pipeline. No real provider calls. |
| Provider execution dry-run and preflight | implemented | claim_with_limits | Audit/documentation boundaries, not runtime locks. |
| Release candidate readiness and cutover | implemented | claim_with_limits | Read-only checks. Dry-run does not tag or publish. |

## Safety and risk

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Deterministic risk gates | implemented | safe_to_claim | Every order passes through RiskManager. Decoupled from LLM reasoning. |
| Kill switch | implemented | safe_to_claim | Disabled by default. Corrupt state fails closed. Ranked escalation. |
| Deadman heartbeat | implemented | claim_with_limits | Disabled by default (timeout=0). Corrupt heartbeat fails closed. |
| Approval queue | implemented | claim_with_limits | File-based with hash integrity, TTL, and path-traversal blocking. |
| Submit dry-run and reconcile | implemented | claim_with_limits | Dry-run runs gates without broker contact. Reconcile is read-only GET. |
| Live trading | disabled_by_default | safe_to_claim | Requires explicit config + typed CLI opt-in + audit record. 8+ conditions. |
| Provider execution locked | docs_only | safe_to_claim | No runtime lock; governed by risk manager and artifact policy. |
| Broker execution blocked | disabled_by_default | safe_to_claim | Returns `None` for live unless `can_submit` is True. Paper always ready. |

## Audit and events

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Audit logs | implemented | safe_to_claim | JSONL with SHA256 hash chain. Secret redaction before writing. |
| Tamper-evident hash-chain | implemented | safe_to_claim | Per-run manifest with root_hash. Detects tampering and tail deletion. |
| Event logs | implemented | safe_to_claim | Daily JSONL with schema validation and secret detection. |
| Replay and read-only inspection | implemented | safe_to_claim | Purely analytical. Never mutates state. |
| Release evidence bundle | implemented | safe_to_claim | Local JSON/Markdown report. No network or credentials. |

## Memory and learning

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Memory ingest and search | implemented | safe_to_claim | SQLite FTS5 with LIKE fallback. Local Markdown only. |
| Markdown memory files | implemented | safe_to_claim | Plaintext in memory_dir. No secrets stored by default. |
| Memory index rebuild | implemented | safe_to_claim | Drops/recreates FTS5 virtual table. |
| Skills lifecycle | partial | claim_with_limits | Plumbing complete. Skill miner is static placeholder (no LLM). |
| Self-improvement learning loop | experimental | claim_with_limits | Orchestration exists. Reflections, nudges, and skill mining are static templates. |

## Automation and operations

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Trading routines | implemented | safe_to_claim | 5 routines with discipline gate and locking. |
| Scheduler and cron runner | implemented | safe_to_claim | GitHub Actions workflow defaults to paper mode. |
| Daily and weekly reports | partial | claim_with_limits | Stubs exist; real content comes from routine engine. |
| Dashboard | implemented | claim_with_limits | Read-only static HTML. Broker sync via audit log tailing. |
| Deployment file generation | implemented | safe_to_claim | Generates Dockerfile, systemd service, READMEs. Does not deploy. |
| Update manager | implemented | claim_with_limits | Safety checks before apply. Auto-rollback. Optional network for version check. |

## Integrations

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| Broker model and protocols | implemented | safe_to_claim | Broker-neutral. Every new broker implements the Broker interface. |
| Alpaca read-only live sync | implemented | claim_with_limits | GET-only via urllib. Fail-closed on critical sync failures. |
| Broker adapters (Binance, CCXT, IBKR) | partial | claim_with_limits | Binance partial; CCXT disabled; IBKR placeholder. |
| Provider catalog and configuration | implemented | safe_to_claim | 15+ profiles with credential resolution via env. |
| ClickUp notifications | implemented | claim_with_limits | urllib POST. Requires CLICKUP_API_TOKEN. |
| Telegram gateway bot | implemented | claim_with_limits | TOTP challenge for money-touching actions. Keyring secret storage. |
| Slack notifications | missing | do_not_claim | No-op stub only. No actual integration. |

## Public review and release engineering

| Capability | Status | Public claim | Notes |
|---|---|---|---|
| CLI command compatibility contract | implemented | safe_to_claim | Parser-only. Guards 174 research commands. |
| Reviewer golden-path smoke test | implemented | safe_to_claim | Temp workspace. No credentials, network, or live trading. |
| Public feedback intake system | implemented | safe_to_claim | 6 issue templates with safety warnings. |
| Feedback label taxonomy | implemented | safe_to_claim | 30 labels across 5 groups. Static local manifest. |
| Controlled reviewer outreach pack | implemented | safe_to_claim | Safe message drafts for 5–10 reviewers. |
| Historical v0.5.7 release record check | implemented | safe_to_claim | Local git show only. No network. |

## What is intentionally out of scope

The following are **not** capabilities of Atlas Agent and should not be requested:

- Autonomous unattended trading
- Profit guarantees or trading signal evaluation
- Real-money broker setup tutorials
- Credential sharing or broker account management
- Safety bypass or approval workflow disablement
- Production-ready live trading without explicit opt-in

## Safety posture summary

- **Live trading** is disabled by default.
- **Provider execution** remains locked (governed by risk manager and artifact policy, not a runtime API block).
- **Broker execution** remains blocked unless explicit opt-in gates pass.
- **No credentials** are required for default verification.
- **Not financial advice.** Does not imply profitability or trading correctness.
- **Not production ready** for unattended or real-money trading.

## Mapping to v0.5.8 work

Capabilities that are `partial` or `experimental` are candidates for v0.5.8 refinement:

- Backtest strategy framework (currently hardcoded `buy_and_hold`)
- Skills lifecycle (skill miner needs LLM integration)
- Self-improvement loop (reflections and nudges need AI-driven extraction)
- Report generators (daily/weekly stubs need real content)
- Broker adapters (Binance completion, CCXT enablement, IBKR implementation)

Capabilities that are `disabled_by_default` remain so unless explicit user opt-in passes all safety gates.
