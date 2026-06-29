# CAND-007: Runtime Readiness Envelope — No Live Submit

## Design Specification

**Candidate ID:** CAND-007  
**Candidate line:** v0.6.16  
**Current public release:** v0.6.15  
**Status:** implemented (design specification; code and tests have landed)  
**Date:** 2026-06-29

> **Implementation note.** The CAND-007 runtime readiness envelope evaluator is implemented in
> `src/atlas_agent/agent/runtime_readiness_envelope.py` and
> `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`. The command is routed configlessly by
> `src/atlas_agent/cli_bootstrap.py`. See [`docs/runtime-readiness-envelope.md`](runtime-readiness-envelope.md)
> for the user-facing command reference. The implementation does not change the planning-only status
> of the v0.6.16 release line.

---

## 1. Candidate purpose

### 1.1 What CAND-007 is

CAND-007 is a local, deterministic, evidence-only evaluator. It consumes the
artifacts produced by CAND-004, CAND-005, and CAND-006 plus a set of static local
policy fixtures, and answers exactly one question:

> Do the candidate artifacts form a coherent, internally consistent, fail-closed
> runtime readiness envelope for future supervised live-path design work?

CAND-007 produces a single envelope artifact that records whether the candidate
chain is internally coherent enough for future supervised live-path design work,
while still refusing all live execution.

### 1.2 Why it follows CAND-006

CAND-006 proved that a simulated-only gated submit conformance rehearsal can be
constructed from CAND-004 and CAND-005 evidence without submitting an order.
CAND-007 steps back one level and asks whether the *entire chain of evidence*
(CAND-004, CAND-005, CAND-006) plus static local policy fixtures forms a
consistent envelope. It does not introduce a new execution stage; it introduces
a meta-evaluation stage.

### 1.3 Why it is still not live trading

CAND-007 consumes only local JSON fixtures and previously recorded artifacts. It
does not call brokers, providers, the runtime kill switch, `RiskManager`,
`OrderRouter`, or any approval queue. It does not instantiate `Order`, create
pending orders, load credentials, or mutate runtime state. Its output is a local
artifact, not a trading command.

### 1.4 What "readiness envelope" means

A "readiness envelope" is the set of preconditions that would have to be true
before any future supervised live-path design work could even be discussed. It
is an envelope of evidence and static policy, not a clearance to trade. The
phrase is always used with the suffix "No Live Submit" in this candidate to
prevent misreading.

---

## 2. Inputs

All inputs are local JSON files.

### 2.1 Upstream artifact validation (projection validation)

CAND-004, CAND-005, and CAND-006 artifacts may contain extra valid fields
beyond what CAND-007 needs. CAND-007 must:

- Load the full JSON object.
- Extract a closed projection containing only the required fields.
- Validate that projection.
- Ignore unrelated upstream fields.
- Never copy raw upstream artifacts into outputs.

Closed-schema rejection (unknown top-level keys rejected) applies strictly to
CAND-007-owned fixtures:

- runtime envelope fixture
- broker capability manifest fixture
- operator policy fixture
- kill-switch policy fixture
- audit policy fixture

### 2.2 CAND-004 projection (`trading-quality-gate.json`)

Required projected keys:

```json
{
  "artifact_type": "trading_quality_gate",
  "schema_version": "trading-quality-gate.v1",
  "mode": "paper",
  "run_id": "<run-id>",
  "symbol": "<SYMBOL>",
  "quality_state": "eligible_for_shadow_live_quality_review",
  "blockers": []
}
```

Validation rules:

- `artifact_type` must be exactly `"trading_quality_gate"`.
- `schema_version` must be accepted (allow `"trading-quality-gate.v1"`, `1`, `"1"`).
- `mode` must be `"paper"`.
- `quality_state` must be exactly `"eligible_for_shadow_live_quality_review"`.
- `blockers` must be an empty list.

### 2.3 CAND-005 projection (`shadow-live-comparison.json`)

Required projected keys:

```json
{
  "artifact_type": "shadow_live_comparison",
  "schema_version": "shadow-live-comparison.v1",
  "run_id": "<run-id>",
  "symbol": "<SYMBOL>",
  "quality_state": "eligible_for_shadow_live_quality_review",
  "status": "matched",
  "freshness_assessment": {},
  "blockers": []
}
```

Validation rules:

- `artifact_type` must be exactly `"shadow_live_comparison"`.
- `schema_version` must be exactly `"shadow-live-comparison.v1"`.
- `status` must be exactly `"matched"`.
- `blockers` must be an empty list.

### 2.4 CAND-006 projection (`gated-submit-conformance.json`)

Required projected keys:

```json
{
  "artifact_type": "gated_submit_conformance",
  "schema_version": "gated-submit-conformance.v1",
  "candidate": "CAND-006",
  "mode": "simulated_only",
  "run_id": "<run-id>",
  "symbol": "<SYMBOL>",
  "status": "dry_run_recorded",
  "as_of": "2026-06-24T09:00:00Z",
  "safety_assertions": {
    "simulated_only": true,
    "no_live_submit": true,
    "no_broker_called": true,
    "no_provider_called": true,
    "no_credentials_loaded": true,
    "no_runtime_state_mutation": true,
    "no_order_instantiated": true,
    "transmission_blocked": true,
    "json_authoritative": true
  },
  "dry_run_request": {
    "transmission": {
      "allowed": false,
      "broker_adapter": null,
      "provider": null
    }
  },
  "blockers": []
}
```

Validation rules:

- `status` must be exactly `"dry_run_recorded"`.
- `as_of` must be a valid UTC timestamp and must be ≤ CAND-007's `--as-of`.
- CAND-006 evidence age: `(CAND-007 as_of) - (CAND-006 as_of)` must be ≤ 24 hours.
- All `safety_assertions` values must be `true`.
- `dry_run_request.transmission.allowed` must be `false`.
- `dry_run_request.transmission.broker_adapter` and `provider` must both be `null`.
- `blockers` must be an empty list.

No wall-clock reads are used for staleness. The fixed maximum evidence age is
24 hours relative to CAND-006's own `as_of`.

> **Deterministic time note:** CAND-007 intentionally uses only caller-supplied
> `--as-of` and fixture timestamps. It performs no wall-clock reads. Therefore it
> can reject CAND-006 evidence whose `as_of` is later than the CAND-007 `--as-of`
> or older than 24 hours, but it does not compare either timestamp to real
> current time.

### 2.5 Runtime envelope fixture (`runtime-envelope.json`)

Closed-schema fixture.

```json
{
  "artifact_type": "runtime_readiness_envelope_fixture",
  "schema_version": "runtime-readiness-envelope-fixture.v1",
  "fixture_mode": "simulated/static",
  "run_id": "<run-id>",
  "symbol": "<SYMBOL>",
  "allowed_modes": ["paper", "shadow_live_readonly", "simulated"],
  "forbidden_modes": ["live", "live_submit", "unsupervised_live"],
  "live_submit_enabled": false,
  "require_human_approval": true,
  "require_kill_switch_inactive": true,
  "require_risk_gate": true,
  "require_audit_recording": true,
  "require_broker_capability_manifest": true,
  "max_order_notional": "1000.00",
  "max_symbol_exposure": "5000.00",
  "max_daily_orders": 10,
  "max_daily_notional": "10000.00",
  "supported_order_types": ["market", "limit"],
  "supported_time_in_force": ["day"],
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Validation rules:

- `fixture_mode` must be exactly `"simulated/static"`.
- `run_id` must match CAND-004, CAND-005, and CAND-006.
- `symbol` must match CAND-004, CAND-005, and CAND-006.
- `live_submit_enabled` must be `false`.
- `require_human_approval`, `require_kill_switch_inactive`, `require_risk_gate`,
  `require_audit_recording`, and `require_broker_capability_manifest` must all be
  `true`.
- `forbidden_modes` must contain `"live"` and `"live_submit"`.
- Decimal fields must be canonical positive decimal strings.
- `max_daily_orders` must be a positive integer.
- `supported_order_types` must be non-empty and may only contain `"market"` and/or `"limit"`.
- `supported_time_in_force` must be non-empty and may only contain `"day"`.
- `expires_at` must be strictly after `--as-of`.

### 2.6 Broker capability manifest fixture (`broker-capabilities.json`)

Closed-schema fixture.

```json
{
  "artifact_type": "broker_capability_manifest_fixture",
  "schema_version": "broker-capability-manifest-fixture.v1",
  "broker_label": "local-simulated-broker",
  "capabilities": {
    "supports_market_orders": true,
    "supports_limit_orders": true,
    "supports_day_tif": true,
    "supports_fractional_quantity": false,
    "supports_equities": true,
    "supports_crypto": false
  },
  "disabled_capabilities": ["supports_margin", "supports_options"],
  "unsupported_order_types": ["stop", "stop_limit"],
  "sandbox_only": true,
  "live_api_contact_allowed": false,
  "credentials_present": false,
  "endpoint_present": false,
  "captured_at": "2026-06-24T09:00:00Z",
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Validation rules:

- `broker_label` must start with one of: `local-`, `simulated-`, `fixture-`,
  `redacted-`.
- `sandbox_only` must be `true`.
- `live_api_contact_allowed` must be `false`.
- `credentials_present` must be `false`.
- `endpoint_present` must be `false`.

### 2.7 Operator policy fixture (`operator-policy.json`)

Closed-schema fixture.

```json
{
  "artifact_type": "operator_policy_fixture",
  "schema_version": "operator-policy-fixture.v1",
  "requires_manual_review": true,
  "requires_explicit_approval": true,
  "approval_scope": "candidate_only",
  "unattended_operation_allowed": false,
  "max_runtime_window_seconds": 3600,
  "max_actions_per_session": 1,
  "allowed_symbols": ["AAPL"],
  "blocked_symbols": [],
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Validation rules:

- `requires_manual_review` and `requires_explicit_approval` must be `true`.
- `approval_scope` must be `"candidate_only"` or `"simulated_only"`.
- `unattended_operation_allowed` must be `false`.
- `max_runtime_window_seconds` and `max_actions_per_session` must be positive
  integers.
- The evaluated `symbol` must be in `allowed_symbols` (if `allowed_symbols` is
  non-empty) and must not appear in `blocked_symbols`.

### 2.8 Kill-switch policy fixture (`kill-switch-policy.json`)

Closed-schema fixture.

```json
{
  "artifact_type": "kill_switch_policy_fixture",
  "schema_version": "kill-switch-policy-fixture.v1",
  "kill_switch_required": true,
  "default_state_on_missing_runtime": "blocked",
  "default_state_on_unknown_runtime": "blocked",
  "operator_override_allowed": false,
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Validation rules:

- `kill_switch_required` must be `true`.
- `default_state_on_missing_runtime` and `default_state_on_unknown_runtime` must
  both be `"blocked"`.
- `operator_override_allowed` must be `false`.

### 2.9 Audit policy fixture (`audit-policy.json`)

Closed-schema fixture.

```json
{
  "artifact_type": "audit_policy_fixture",
  "schema_version": "audit-policy-fixture.v1",
  "audit_required": true,
  "append_only_required": true,
  "hash_chain_required": true,
  "local_artifact_recording_required": true,
  "live_audit_chain_claimed": false,
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Validation rules:

- `audit_required`, `append_only_required`, `hash_chain_required`, and
  `local_artifact_recording_required` must all be `true`.
- `live_audit_chain_claimed` must be `false`.

### 2.10 Universal rejection rules

Every CAND-007-owned fixture is scanned before schema validation for:

- Secret-like keys: `api_key`, `apikey`, `token`, `password`, `secret`,
  `credential`, `private_key`, `auth_header`, `authorization`.
- Endpoint-like keys: `endpoint`, `url`, `base_url`, `api_url`,
  `websocket_url`, `host`, `headers`, `auth`, `authorization`.
- Secret-like value fragments: `bearer `, `sk-`, `ghp_`, `akia`, `.env`.
- URL/protocol value patterns: `http://`, `https://`, `ws://`, `wss://`.

Unknown top-level fields in any CAND-007-owned fixture are rejected.

---

## 3. Evidence correlation

CAND-007 correlates upstream evidence using these rules:

| Field | Rule |
|---|---|
| `run_id` | Must be identical across CAND-004, CAND-005, CAND-006, and the runtime envelope fixture. |
| `symbol` | Must be identical across CAND-004, CAND-005, CAND-006, runtime envelope, and operator policy. |
| `candidate` | CAND-006 artifact must declare `"candidate": "CAND-006"`. |
| `artifact_type` | Each upstream artifact must declare its expected `artifact_type`. |
| `schema_version` | Each upstream artifact must declare an accepted `schema_version`. Unsupported versions fail closed. |
| `quality_state` | CAND-004 and CAND-005 must both report `"eligible_for_shadow_live_quality_review"`. |
| `status` | CAND-005 must be `"matched"`; CAND-006 must be `"dry_run_recorded"`. |
| `blockers` | Upstream artifact `blockers` arrays must be empty. |
| `as_of` | Caller-supplied UTC timestamp used for expiry and evidence-age checks. No wall-clock time is used. |
| `input_fingerprints` | sha256 canonical JSON fingerprints of each consumed input, recorded in output. |
| `envelope_digest` | sha256 canonical JSON digest over all input fingerprints plus `as_of` and `symbol`. |

Stale evidence:

- Any CAND-007-owned fixture with `expires_at` ≤ `as_of` is rejected as stale.
- CAND-006 `as_of` must be ≤ CAND-007 `--as-of`.
- CAND-006 evidence age must be ≤ 24 hours relative to CAND-006 `as_of`.
- CAND-006 `dry_run_request.transmission.allowed` must be `false`.

Missing fingerprints or malformed artifacts cause immediate `not_evaluated` /
`blocked` exit.

---

## 4. Required upstream states

| Upstream | Required state |
|---|---|
| CAND-004 | `quality_state == "eligible_for_shadow_live_quality_review"` |
| CAND-005 | `status == "matched"` |
| CAND-006 | `status == "dry_run_recorded"` |
| CAND-006 `as_of` | ≤ CAND-007 `--as-of` and not older than 24 hours |
| CAND-006 safety assertions | All `true` |
| CAND-006 dry-run request | `transmission.allowed == false`, `broker_adapter == null`, `provider == null` |
| All upstream artifacts | `blockers` empty, schema accepted |

---

## 5. Runtime envelope fixture

See section 2.5 for the full schema. Key design intent:

- Represents static local runtime constraints, not runtime configuration.
- Explicitly forbids live submit and unsupervised live modes.
- Carries the same `run_id` and `symbol` as the upstream artifacts for
  correlation.
- Requires human approval, kill-switch, risk gate, audit recording, and broker
  capability manifest as preconditions.
- Bounds order notional, symbol exposure, daily order count, and daily notional.
- Restricts supported order types and time-in-force to conservative values.
- Includes `expires_at` so the envelope evaluation is time-bounded.

Must NOT include:

- Broker credentials.
- Provider credentials.
- Account IDs.
- Real endpoints.
- Executable hooks.
- Shell commands.
- Environment variables.
- Free-form metadata.

---

## 6. Broker capability manifest fixture

See section 2.6 for the full schema. Key design intent:

- Strictly static, non-credential, non-network manifest.
- `broker_label` must start with `local-`, `simulated-`, `fixture-`, or
  `redacted-` to make clear it is not a real broker identifier.
- Declares what a simulated broker label could conceptually support without
  implying any real broker certification.
- Explicitly denies live API contact, credentials, and endpoints.
- Captured and expiry timestamps bound the fixture's validity.

Must NOT:

- Import or query broker adapter code.
- Include account IDs, endpoints, keys, OAuth/client IDs, or raw broker responses.
- Imply broker approval.

---

## 7. Operator policy fixture

See section 2.7 for the full schema. Key design intent:

- Local static operator policy.
- Requires manual review and explicit approval.
- Approval scope is limited to `candidate_only` or `simulated_only`.
- Disallows unattended operation.
- Bounds runtime window and actions per session.
- Allows/blocklists symbols.

The evaluated symbol must be in `allowed_symbols` (if non-empty) and absent from
`blocked_symbols`.

Must NOT be treated as real human approval. The fixture is a policy statement,
not an approval record.

---

## 8. Kill-switch policy fixture

See section 2.8 for the full schema. Key design intent:

- Static policy, not runtime switch state.
- Requires kill switch.
- Defaults to `blocked` on missing or unknown runtime state.
- Disallows operator override.

---

## 9. Audit policy fixture

See section 2.9 for the full schema. Key design intent:

- Static policy.
- Requires audit, append-only recording, hash chain, and local artifact recording.
- Explicitly denies any live audit chain claim.

CAND-007 must not write to the real live audit chain. It writes only local
artifacts.

---

## 10. Status model

Exact statuses:

- `not_evaluated`
- `blocked`
- `upstream_quality_blocked`
- `shadow_evidence_blocked`
- `submit_conformance_blocked`
- `runtime_envelope_blocked`
- `broker_capability_blocked`
- `operator_policy_blocked`
- `kill_switch_policy_blocked`
- `audit_policy_blocked`
- `envelope_synthesized`
- `readiness_envelope_recorded`

The status `envelope_synthesized` is an internal pre-recording status. It does
not imply live readiness.

The status `readiness_envelope_recorded` is evidence-recording status only. It
is not live readiness, not trading safety, not profitability evidence, and not
permission to submit orders. This disclaimer must appear wherever the status is
referenced in docs and in the artifact output.

Intentionally avoided:

- `live_ready`
- `approved_for_live`
- `safe_to_trade`
- `ready_to_submit`
- any status implying live readiness or permission to submit orders.

---

## 11. Gate sequence

Strict fail-closed order. Only successful artifact recording may return exit
code 0.

Gate evaluation stops at the first failed gate. The report records the failed
gate with its failure status, records downstream gates as `not_run`, and returns
the failed gate's status. Downstream gates must not be evaluated after a blocker
is found.

| # | Gate ID | Failure status |
|---|---|---|
| 1 | `schema_preflight` | `not_evaluated` |
| 2 | `cand004_evidence_gate` | `upstream_quality_blocked` |
| 3 | `cand005_evidence_gate` | `shadow_evidence_blocked` |
| 4 | `cand006_evidence_gate` | `submit_conformance_blocked` |
| 5 | `runtime_envelope_fixture_gate` | `runtime_envelope_blocked` |
| 6 | `broker_capability_manifest_gate` | `broker_capability_blocked` |
| 7 | `operator_policy_fixture_gate` | `operator_policy_blocked` |
| 8 | `kill_switch_policy_fixture_gate` | `kill_switch_policy_blocked` |
| 9 | `audit_policy_fixture_gate` | `audit_policy_blocked` |
| 10 | `envelope_synthesis_gate` | `blocked` |
| 11 | `artifact_recording_gate` | `blocked` (if JSON write fails) |

After gate 10 passes, the report status becomes `envelope_synthesized`.
After gate 11 succeeds, it is promoted to `readiness_envelope_recorded` and exit
code 0 is returned.

---

## 12. Artifact design

### 12.1 Required artifacts

- `runtime-readiness-envelope.json` (authoritative)
- `runtime-readiness-envelope-report.md` (informational)

### 12.2 `runtime-readiness-envelope.json`

```json
{
  "artifact_type": "runtime_readiness_envelope",
  "schema_version": "runtime-readiness-envelope.v1",
  "candidate": "CAND-007",
  "mode": "simulated_only",
  "status": "readiness_envelope_recorded",
  "exit_code": 0,
  "evaluation_id": "re-<digest-prefix>",
  "as_of": "2026-06-24T10:00:00Z",
  "run_id": "run-123",
  "symbol": "AAPL",
  "candidate_chain": [
    "CAND-001", "CAND-002", "CAND-003", "CAND-004",
    "CAND-005", "CAND-006", "CAND-007"
  ],
  "gate_sequence": [...],
  "gates": [...],
  "input_artifacts": {
    "quality_gate": "trading-quality-gate.json",
    "shadow_comparison": "shadow-live-comparison.json",
    "submit_conformance": "gated-submit-conformance.json",
    "runtime_envelope": "runtime-envelope.json",
    "broker_capabilities": "broker-capabilities.json",
    "operator_policy": "operator-policy.json",
    "kill_switch_policy": "kill-switch-policy.json",
    "audit_policy": "audit-policy.json"
  },
  "input_fingerprints": {
    "quality_gate": "sha256:...",
    "shadow_comparison": "sha256:...",
    "submit_conformance": "sha256:...",
    "runtime_envelope": "sha256:...",
    "broker_capabilities": "sha256:...",
    "operator_policy": "sha256:...",
    "kill_switch_policy": "sha256:...",
    "audit_policy": "sha256:..."
  },
  "input_digest": "sha256:...",
  "envelope_digest": "sha256:...",
  "upstream_summaries": {
    "cand004": {
      "artifact_type": "trading_quality_gate",
      "schema_version": "trading-quality-gate.v1",
      "mode": "paper",
      "quality_state": "eligible_for_shadow_live_quality_review",
      "blockers": []
    },
    "cand005": {
      "artifact_type": "shadow_live_comparison",
      "schema_version": "shadow-live-comparison.v1",
      "status": "matched",
      "blockers": []
    },
    "cand006": {
      "artifact_type": "gated_submit_conformance",
      "schema_version": "gated-submit-conformance.v1",
      "status": "dry_run_recorded",
      "as_of": "2026-06-24T09:00:00Z",
      "transmission_allowed": false,
      "blockers": []
    }
  },
  "fixture_summaries": {
    "runtime_envelope": {
      "fixture_mode": "simulated/static",
      "run_id": "run-123",
      "symbol": "AAPL",
      "live_submit_enabled": false,
      "require_human_approval": true,
      "require_kill_switch_inactive": true,
      "require_risk_gate": true,
      "require_audit_recording": true,
      "require_broker_capability_manifest": true,
      "max_order_notional": "1000.00",
      "max_symbol_exposure": "5000.00",
      "max_daily_orders": 10,
      "max_daily_notional": "10000.00",
      "supported_order_types": ["market", "limit"],
      "supported_time_in_force": ["day"],
      "expires_at": "2026-06-24T12:00:00Z"
    },
    "broker_capability": {
      "broker_label": "local-simulated-broker",
      "sandbox_only": true,
      "live_api_contact_allowed": false,
      "credentials_present": false,
      "endpoint_present": false
    },
    "operator_policy": {
      "requires_manual_review": true,
      "requires_explicit_approval": true,
      "approval_scope": "candidate_only",
      "unattended_operation_allowed": false,
      "max_runtime_window_seconds": 3600,
      "max_actions_per_session": 1,
      "allowed_symbols": ["AAPL"],
      "blocked_symbols": []
    },
    "kill_switch_policy": {
      "kill_switch_required": true,
      "default_state_on_missing_runtime": "blocked",
      "default_state_on_unknown_runtime": "blocked",
      "operator_override_allowed": false
    },
    "audit_policy": {
      "audit_required": true,
      "append_only_required": true,
      "hash_chain_required": true,
      "local_artifact_recording_required": true,
      "live_audit_chain_claimed": false
    }
  },
  "envelope_assertions": {
    "live_submit_forbidden": true,
    "human_approval_required": true,
    "kill_switch_required": true,
    "risk_gate_required": true,
    "audit_recording_required": true,
    "broker_manifest_required": true,
    "operator_policy_fail_closed": true,
    "all_upstream_statuses_accepted": true,
    "no_credentials_in_fixtures": true,
    "no_endpoints_in_fixtures": true,
    "no_account_ids_in_fixtures": true
  },
  "blocked_reasons": [],
  "recording": {
    "json_written": true,
    "markdown_written": true
  },
  "disclaimer": "Runtime readiness envelope evaluation (CAND-007) — simulated only. readiness_envelope_recorded is evidence-recording status only. It is not live readiness, not trading safety, not profitability evidence, and not permission to submit orders."
}
```

### 12.3 `runtime-readiness-envelope-report.md`

Human-readable rendering of the JSON artifact. Sections:

- Header: status, evaluation_id, as_of, symbol, run_id.
- Gate table.
- Upstream evidence summaries.
- Fixture summaries (redacted, no raw fixtures).
- Envelope assertions table.
- Blockers list if any.
- Disclaimer including the exact
  `readiness_envelope_recorded is evidence-recording status only` text.

Must NOT include:

- Raw fixture contents.
- Absolute paths.
- Usernames, environment variables.
- Credentials, account IDs, endpoint URLs.
- Stack traces.
- Raw broker/provider payloads.

---

## 13. CLI design

### 13.1 Command

```bash
atlas agent readiness-envelope \
  --quality-gate reports/autonomous_paper_quality/trading-quality-gate.json \
  --shadow-comparison reports/shadow_live/shadow-live-comparison.json \
  --submit-conformance reports/gated_submit_conformance/gated-submit-conformance.json \
  --runtime-envelope fixtures/runtime-envelope.json \
  --broker-capabilities fixtures/broker-capabilities.json \
  --operator-policy fixtures/operator-policy.json \
  --kill-switch-policy fixtures/kill-switch-policy.json \
  --audit-policy fixtures/audit-policy.json \
  --output-dir reports/runtime_readiness_envelope \
  --as-of 2026-06-24T10:00:00Z \
  [--json]
```

### 13.2 Unsafe flags rejected at parse time

The CLI parser rejects these flags with exit code 2:

- `--live`
- `--submit`
- `--broker`
- `--provider`
- `--api-key`
- `--credentials`
- `--endpoint`
- `--account`
- `--account-id`
- `--client-order-id`
- `--place-order`
- `--order-router`
- `--risk-manager`
- `--mode`
- `--kill-switch-override`

### 13.3 Path aliasing

The CLI rejects `--output-dir` or output artifact paths that resolve to the same
filesystem location as any input file or directory, using `Path.resolve()`
comparison.

### 13.4 Exit codes

| Exit code | Meaning |
|---|---|
| 0 | Every gate passed and artifacts recorded (`readiness_envelope_recorded`). |
| 2 | Any other final status or CLI error. |

---

## 14. Bootstrap routing decision

Reuse and extend the CAND-006 configless bootstrap pattern.

`src/atlas_agent/cli_bootstrap.py` intercepts when the first two tokens are
exactly `agent readiness-envelope`:

```python
args[0] == "agent" and args[1] == "readiness-envelope"
```

This means:

- `atlas agent readiness-envelope ...` is intercepted and handled by the
  configless CAND-007 parser.
- `atlas agent readiness-envelope --workspace X` is also intercepted. The
  `--workspace` flag is rejected by the CAND-007 argparse parser as an
  unsupported/unsafe flag. `atlas_agent.cli` is not imported.
- `atlas --workspace X agent readiness-envelope` delegates to the legacy CLI
  because the first two tokens are `--workspace X`, not `agent readiness-envelope`.

The legacy CLI must still register a subparser for `readiness-envelope` so that
delegated `--help` and unknown-flag behavior are consistent.

---

## 15. Static checker plan

`scripts/check_runtime_readiness_envelope_contract.py`

Checks:

1. Required files exist.
2. Required statuses present in source.
3. Required artifact names present.
4. CLI route wired in bootstrap and legacy CLI.
5. Universal rejection rules are implemented in engine/CLI/bootstrap:
   - Secret-like keys rejected: `api_key`, `apikey`, `token`, `password`,
     `secret`, `credential`, `private_key`, `auth_header`, `authorization`.
   - Secret-like value fragments rejected: `bearer `, `sk-`, `ghp_`, `akia`,
     `.env`.
   - Endpoint-like keys rejected: `endpoint`, `url`, `base_url`, `api_url`,
     `websocket_url`, `host`, `headers`, `auth`, `authorization`.
   - URL/protocol value patterns rejected: `http://`, `https://`, `ws://`,
     `wss://`.
   - Conservative matching: negative safety disclaimers ("not live", "no submit")
     must not trigger false positives.
6. Forbidden imports/calls are absent from engine, CLI, and bootstrap:
   - `Order`, `OrderRouter`, `RiskManager`.
   - Broker adapters, provider adapters, execution modules.
   - Runtime kill switch.
   - Atlas config loading.
   - Credential/env loading.
   - Network libraries (`requests`, `httpx`, `urllib`, `websocket`, etc.).
   - Live submit/place/cancel/flatten calls.
7. CAND-006 freshness rule is present:
   - CAND-006 `as_of` must exist.
   - CAND-006 `as_of` must be ≤ CAND-007 `--as-of`.
   - CAND-006 evidence age must be ≤ 24 hours.
   - Stale CAND-006 evidence blocks with `submit_conformance_blocked`.
8. Broker label prefix rule is present:
   - `broker_label` must start with `local-`, `simulated-`, `fixture-`, or
     `redacted-`.
9. Output-path aliasing protection is present:
   - Input paths must not resolve to either final output artifact
     (`runtime-readiness-envelope.json`, `runtime-readiness-envelope-report.md`).
   - Symlink aliasing is rejected.
   - Output directory must not overwrite inputs.
10. Artifact disclaimer is present:
    - Source constants carry the exact evidence-only disclaimer.
    - JSON artifact includes the disclaimer.
    - Markdown artifact includes the disclaimer.
    - CAND-007 design doc and governance docs include the disclaimer.
11. No live-readiness claims in docs/source.
12. No live submit claims.
13. Policy fixtures do not imply real approval.
14. Docs consistency: required phrases in CAND-007 doc and governance docs.
15. Stale CAND-007 claim prevention after implementation.

---

## 16. Test plan

### 16.1 Engine tests (`tests/test_runtime_readiness_envelope.py`)

1. `test_valid_all_pass_envelope`
2. `test_missing_quality_gate_blocks`
3. `test_blocked_quality_gate_blocks`
4. `test_missing_shadow_comparison_blocks`
5. `test_shadow_comparison_minor_divergence_blocks`
6. `test_missing_submit_conformance_blocks`
7. `test_submit_conformance_not_recorded_blocks`
8. `test_submit_conformance_transmission_enabled_blocks`
9. `test_submit_conformance_stale_evidence_blocks`
10. `test_runtime_envelope_live_submit_enabled_true_blocks`
11. `test_broker_capability_credentials_present_true_blocks`
12. `test_broker_capability_endpoint_present_true_blocks`
13. `test_operator_policy_unattended_allowed_blocks`
14. `test_kill_switch_policy_default_unknown_not_blocked_blocks`
15. `test_audit_policy_hash_chain_not_required_blocks`
16. `test_unknown_fixture_fields_rejected`
17. `test_secret_like_fields_rejected`
18. `test_url_protocol_values_rejected`
19. `test_stale_fixtures_block`
20. `test_run_id_mismatch_blocks`
21. `test_symbol_mismatch_blocks`
22. `test_json_and_markdown_agree`
23. `test_json_write_failure_rolls_back_status`
24. `test_broker_label_prefix_enforced`
25. `test_operator_policy_symbol_allow_and_block`
26. `test_fixture_expiry_blocks`
27. `test_output_path_alias_rejected`
28. `test_disclaimer_present_in_json_and_markdown`

Expected behavior for the added tests:

- `test_broker_label_prefix_enforced`: `broker_label` values not starting with
  `local-`, `simulated-`, `fixture-`, or `redacted-` block.
- `test_operator_policy_symbol_allow_and_block`: the evaluated symbol must be in
  `allowed_symbols` and must not appear in `blocked_symbols`.
- `test_fixture_expiry_blocks`: every CAND-007-owned fixture with
  `expires_at <= as_of` blocks.
- `test_output_path_alias_rejected`: output artifact paths and symlink aliases
  cannot overwrite any input file.
- `test_disclaimer_present_in_json_and_markdown`: the exact evidence-only
  disclaimer appears in both the JSON and Markdown artifacts.

### 16.2 CLI tests (`tests/test_runtime_readiness_envelope_cli.py`)

- Help output contains safety disclaimer.
- JSON output mode works.
- Missing required flag returns exit code 2.
- Unsafe flags return exit code 2.

### 16.3 Import-trace tests (`tests/test_runtime_readiness_envelope_import_trace.py`)

- Positive route imports no forbidden modules.
- Help route imports no `atlas_agent.cli`.
- Valid route imports no `atlas_agent.cli`.
- `atlas agent readiness-envelope --workspace X` is configless and rejected
  without importing `atlas_agent.cli`.
- `atlas --workspace X agent readiness-envelope` delegates to legacy CLI.
- `atlas run --mode live` remains fail-closed.
- `test_forbidden_modules_not_imported_on_any_configless_route`: both the
  CAND-006 and CAND-007 configless routes avoid importing legacy CLI/config,
  broker adapters, provider adapters, risk, execution, and safety modules.
- `test_legacy_cli_delegation_with_workspace`: `atlas --workspace X agent
  readiness-envelope` delegates to the legacy CLI as designed.

---

## 17. Docs/governance/release metadata plan

New/modified files:

- `docs/runtime-readiness-envelope.md`
- `docs/autonomy-roadmap.md`
- `docs/bounded-live-autonomy-governance.md`
- `docs/shadow-live-readiness-contract.md`
- `docs/gated-submit-conformance.md`
- `docs/releases/v0.6.16-plan.md`
- `docs/releases/v0.6.16-candidates.md`
- `docs/releases/v0.6.16-candidate-selection.md`
- `docs/releases/v0.6.16-candidates.json`
- `CHANGELOG.md`

Must preserve:

- `v0.6.15` is current public release.
- `v0.6.16` is candidate/planning work.
- No version bump.
- No tag.
- No GitHub Release.
- No PyPI publication.
- No live readiness claim.

---

## 18. Open design questions

All open questions are answered with conservative defaults:

1. **Should the runtime envelope fixture explicitly list allowed broker labels?**
   - No. The broker manifest is checked independently for being
     credential/endpoint-free.
2. **Should CAND-007 require the operator policy `allowed_symbols` to contain the evaluated symbol?**
   - Yes, if `allowed_symbols` is non-empty. The symbol must also be absent from
     `blocked_symbols`.
3. **Should the envelope include a `candidate_chain` field?**
   - Yes. The JSON artifact includes the full candidate chain from CAND-001 to
     CAND-007.

---

## 19. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| "Readiness envelope" mistaken for live readiness. | Full candidate name includes "No Live Submit". Disclaimer in every artifact and doc. Status `readiness_envelope_recorded` carries the exact evidence-recording-only disclaimer. |
| Broker capability manifest mistaken for broker certification. | `broker_label` must start with `local-`, `simulated-`, `fixture-`, or `redacted-`; `sandbox_only: true`; `live_api_contact_allowed: false`; `credentials_present: false`; `endpoint_present: false`. Docs state it is a static planning fixture. |
| Operator policy fixture mistaken for real approval. | Named `operator_policy_fixture`. `approval_scope` is `candidate_only` or `simulated_only`. Docs state it is not real human approval. |
| Audit policy mistaken for live audit-chain proof. | `live_audit_chain_claimed: false`. CAND-007 writes local artifacts only. |
| Configless bootstrap expansion changes existing CLI behavior. | Add CAND-007 as a second exact two-token route only. `atlas --workspace X agent readiness-envelope` still delegates. Import-trace tests cover both forms. |
| Stale CAND-006 evidence accepted. | Reject unless `status == "dry_run_recorded"`, CAND-006 `as_of` ≤ CAND-007 `--as-of`, age ≤ 24 hours, and fixtures not expired relative to `--as-of`. |
| Fixtures becoming too close to runtime config. | Keep fields static/declarative: no hooks, env vars, shell commands, free-form metadata. |
| Unsafe CLI flags sneaking in. | Explicit deny-list at parse time with exit code 2. |

---

## 20. Recommended implementation approach

1. Scaffold modules:
   - `src/atlas_agent/agent/runtime_readiness_envelope.py`
   - `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`
2. Implement closed-schema validators for all 5 CAND-007-owned fixtures and
   projection validators for the 3 upstream artifacts.
3. Implement gate sequence in `build_runtime_readiness_envelope_report()`.
4. Implement artifact writers for JSON + Markdown.
5. Update `src/atlas_agent/cli_bootstrap.py` to route `atlas agent readiness-envelope`.
6. Update legacy CLI subparser registration.
7. Add `scripts/check_runtime_readiness_envelope_contract.py`.
8. Add engine, CLI, and import-trace tests.
9. Add docs and update release metadata.
10. Run required checks: `pytest`, `atlas validate`, contract checker, CLI help,
    and verify `atlas run --mode live` still fails safely.

---

## 21. Final spec draft

The core engine is a single deterministic function:

```python
def build_runtime_readiness_envelope_report(
    inputs: ReadinessEnvelopeInputs,
) -> ReadinessEnvelopeReport: ...
```

and a separate writer:

```python
def write_runtime_readiness_envelope_artifacts(
    report: ReadinessEnvelopeReport,
    output_dir: Path,
) -> ReadinessEnvelopeReport: ...
```

The CLI delegates to these, emits JSON or text, and returns
`report.exit_code`. All safety boundaries from sections 2–14 must be enforced.

---

## 22. Reviewer checklist

- [ ] CLI name is `atlas agent readiness-envelope` and implies no live submit.
- [ ] Bootstrap routing intercepts `agent readiness-envelope` as first two tokens and rejects `--workspace` after that form without importing `atlas_agent.cli`.
- [ ] `atlas --workspace X agent readiness-envelope` delegates to legacy CLI.
- [ ] Upstream artifacts use projection validation; CAND-007-owned fixtures use closed-schema validation.
- [ ] Runtime envelope fixture includes `run_id` and `symbol` matching upstream.
- [ ] Operator policy requires evaluated symbol in `allowed_symbols` (if non-empty) and absent from `blocked_symbols`.
- [ ] Broker `broker_label` starts with `local-`, `simulated-`, `fixture-`, or `redacted-`.
- [ ] URL/protocol patterns `http://`, `https://`, `ws://`, `wss://` and endpoint-like keys are rejected; `.com`/`.net`/`.org` are not globally rejected.
- [ ] CAND-006 evidence age is bounded by 24 hours relative to CAND-006 `as_of`.
- [ ] Status model uses `envelope_synthesized` pre-recording and `readiness_envelope_recorded` post-recording with the exact evidence-recording-only disclaimer.
- [ ] All other safety boundaries from the original design are preserved.
- [ ] Docs and release metadata are updated without version bump, tag, release, or PyPI claim.
- [ ] `atlas run --mode live` remains fail-closed.
