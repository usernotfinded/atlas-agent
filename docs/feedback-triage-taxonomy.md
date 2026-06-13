# Feedback Triage Taxonomy

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This document defines the label taxonomy and triage rules for incoming public reviewer feedback. Use it to classify issues consistently and safely.

## Label categories

### Type (`type:*`)

| Label | When to use |
|---|---|
| `type: bug` | Reproducible defect in local-only paths (install, CLI, checks, docs build). |
| `type: docs` | Documentation clarity, accuracy, or missing coverage. |
| `type: feedback` | General structured reviewer feedback that does not fit a bug or feature. |
| `type: safety` | Safety gate or trust-boundary concern. |
| `type: feature` | Capability suggestion or enhancement request. |
| `type: chore` | Maintenance, hygiene, or release-engineering task. |

### Area (`area:*`)

| Label | When to use |
|---|---|
| `area: cli` | Command-line interface, commands, or help text. |
| `area: install` | Installation, packaging, or dependency issues. |
| `area: docs` | Documentation site, README, or guides. |
| `area: research` | Research workflow, sandbox, or paper-only analysis. |
| `area: release-gate` | Check scripts, test gates, or release automation. |
| `area: safety-model` | Safety gate design, kill switch, or risk controls. |
| `area: feedback-intake` | Issue templates, triage process, or label taxonomy. |
| `area: github-hygiene` | Repository hygiene, CI, templates, or GitHub settings. |

### Priority (`priority:*`)

| Label | When to use |
|---|---|
| `priority: blocker` | Must fix before next release; affects install, safety, or deterministic checks. |
| `priority: high` | Significant impact but does not block release. |
| `priority: normal` | Standard priority; typical docs or UX improvement. |
| `priority: low` | Minor polish or backlog item. |

### Risk (`risk:*`)

Risk labels describe the **topic** of the feedback. They do **not** mean the feature is enabled, recommended, or changed.

| Label | When to use |
|---|---|
| `risk: protected-boundary` | Feedback touches config, brokers, execution, safety, or risk modules. |
| `risk: safety-sensitive` | Feedback may affect safety gates or trust boundaries. |
| `risk: credentials` | Feedback involves credential handling or configuration. |
| `risk: live-trading` | Feedback relates to live trading paths. |
| `risk: provider-execution` | Feedback relates to provider execution paths. |
| `risk: broker-execution` | Feedback relates to broker execution paths. |

### Status (`status:*`)

| Label | When to use |
|---|---|
| `status: needs-triage` | New issue awaiting classification. |
| `status: accepted` | Accepted for work or documentation. |
| `status: needs-info` | Awaiting additional information from reporter. |
| `status: rejected-out-of-scope` | Closed as out of scope per feedback policy. |
| `status: duplicate` | Duplicate of existing issue. |
| `status: wontfix` | Closed without action; does not fit roadmap. |

## How to classify incoming feedback

1. **Read the issue body and template fields.**
2. **Apply one type label** (`type:*`).
3. **Apply one or more area labels** (`area:*`) that best match the scope.
4. **Apply a priority label** based on the blocker rules below.
5. **Apply risk labels** if the topic touches protected boundaries, credentials, live trading, provider execution, or broker execution.
6. **Apply a status label.** New issues start as `status: needs-triage`. Update as the issue progresses.

## Blocker vs non-blocker rules

### Blocker (`priority: blocker`)

An issue is a blocker if it meets **any** of these criteria:

- Breaks the reviewer golden-path smoke test on a clean environment.
- Introduces forbidden claims or overstatements in public docs.
- Weakens safety gates or makes live/provider/broker paths easier to activate.
- Leaks credentials or absolute paths in public artifacts.
- Corrupts the deterministic local check suite (install, version, CLI compatibility, etc.).

### Non-blocker (`priority: high`, `priority: normal`, or `priority: low`)

An issue is a non-blocker if it meets **all** of these criteria:

- Does not break install or deterministic checks.
- Does not weaken safety gates.
- Is a docs clarity issue, UX polish, enhancement idea, or refactoring suggestion.

## How to handle safety-sensitive reports

Safety-sensitive reports are high priority and must be triaged carefully:

- Do not dismiss concerns because "live trading is disabled."
- Evaluate impact on paper/sandbox workflows and docs integrity.
- Label with `risk: safety-sensitive` and `type: safety`.
- Document resolved issues in `SECURITY.md` and the changelog if appropriate.
- For private disclosure, direct the reporter to GitHub Security Advisories.

## How to label out-of-scope requests

Close out-of-scope requests with `status: rejected-out-of-scope` and a reference to this policy.

The following are always out of scope:

- Requests to bypass safety gates or approval workflows.
- Requests to enable live trading by default.
- Requests for profit guarantees or trading performance evaluations.
- Requests for trading signal quality assessment.
- Requests for real-money broker setup tutorials.
- Credential sharing or "help me connect my broker" requests.

## How to label requests involving restricted features

| Request topic | Labels to apply |
|---|---|
| Live trading | `risk: live-trading`, `status: rejected-out-of-scope` |
| Broker execution | `risk: broker-execution`, `status: rejected-out-of-scope` |
| Provider execution | `risk: provider-execution`, `status: rejected-out-of-scope` |
| Credentials | `risk: credentials`, `status: rejected-out-of-scope` |
| Safety bypass | `risk: safety-sensitive`, `status: rejected-out-of-scope` |
| Profitability / trading signals | `status: rejected-out-of-scope` |

## How to avoid accepting profit/trading-signal feedback

Maintainers must not:

- Accept feedback that implies Atlas is profitable or "beats the market."
- Create issues from requests to evaluate trading signal quality.
- Respond to "is this safe to trade live?" with anything other than a reference to the safety docs and disclaimer.
- Treat broker setup or credential configuration as a supported use case for public feedback.

## Mapping the taxonomy to current planning work

Feedback that meets blocker criteria is a candidate for the current planning milestone (e.g., `v0.6.10`). Typical planning work includes:

- Post-release CLI refactor regression fixes.
- New check scripts and compatibility contracts.
- Docs honesty and clarity improvements.
- Release engineering automation.

Non-blocker issues are backlog items. Out-of-scope requests are closed as "not planned."

## Triage examples

### Install bug after golden path fails

A reviewer reports that `pip install -e .` fails on a clean Ubuntu 22.04 machine and the golden-path smoke test exits non-zero.

- **Type:** `type: bug`
- **Area:** `area: install`, `area: release-gate`
- **Priority:** `priority: blocker`
- **Risk:** none
- **Status:** `status: accepted`

### CLI UX confusion

A reviewer finds `atlas validate` output hard to read and suggests clearer headings.

- **Type:** `type: feedback`
- **Area:** `area: cli`
- **Priority:** `priority: normal`
- **Risk:** none
- **Status:** `status: accepted`

### Docs wording issue

A reviewer points out that a sentence in the README could be misread as implying Atlas recommends a specific broker.

- **Type:** `type: docs`
- **Area:** `area: docs`
- **Priority:** `priority: high` (could be a forbidden claim)
- **Risk:** `risk: safety-sensitive`
- **Status:** `status: accepted`

### Request to enable live trading by default

A reviewer opens an issue asking for live trading to be enabled without opt-in.

- **Type:** `type: feature`
- **Area:** `area: safety-model`
- **Priority:** `priority: blocker` (would weaken safety gates)
- **Risk:** `risk: live-trading`, `risk: safety-sensitive`
- **Status:** `status: rejected-out-of-scope`
- **Action:** Close with reference to this policy.

### Request to evaluate profitability

A reviewer asks "has anyone made money with this?" or requests a backtest performance report.

- **Type:** `type: feedback`
- **Area:** `area: research`
- **Priority:** `priority: low`
- **Risk:** none
- **Status:** `status: rejected-out-of-scope`
- **Action:** Close with reference to the out-of-scope policy.

### Safety model concern

A reviewer identifies a potential issue in the safety model logic that could affect paper-mode behavior.

- **Type:** `type: safety`
- **Area:** `area: safety-model`
- **Priority:** `priority: blocker`
- **Risk:** `risk: safety-sensitive`
- **Status:** `status: accepted`

### Protected boundary change request

A reviewer requests a change to the broker adapter interface.

- **Type:** `type: feature`
- **Area:** `area: safety-model`
- **Priority:** `priority: normal`
- **Risk:** `risk: protected-boundary`, `risk: broker-execution`
- **Status:** `status: needs-info` (ask for rationale and safety impact)

## Safety summary

- Live trading disabled by default.
- Provider execution remains locked.
- Broker execution remains blocked unless explicit opt-in gates pass.
- No credentials required for default verification.
- Not financial advice. Does not imply profitability or trading correctness.
