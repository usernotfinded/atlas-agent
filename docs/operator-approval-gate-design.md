# CAND-008: Operator Approval Gate & Kill-Switch Observation Fixture Review

## Design Specification

**Candidate ID:** CAND-008  
**Candidate line:** v0.6.16  
**Current public release:** v0.6.15  
**Status:** design-only / planning-only  
**Date:** 2026-06-30

> **Design-only notice.** This document specifies CAND-008. No source code, tests,
> checkers, CLI routes, or release metadata changes are authorized by this design
> document. If implemented later, CAND-008 must remain evidence-only,
> local-first, deterministic, non-submitting, non-live, non-transmitting,
> human-in-the-loop, and fail-closed.

> **Evidence-only disclaimer.** The target status `operator_gate_recorded` is an
> evidence-recording status only. It is not live readiness, not trading safety,
> not profitability evidence, not real human approval to trade, and not
> permission to submit orders.

---

## 1. Candidate purpose

### 1.1 What CAND-008 is

CAND-008 is a local, deterministic, evidence-only operator review gate. It
consumes the artifacts produced by CAND-004, CAND-005, CAND-006, and CAND-007,
plus four CAND-008-owned static local fixtures (operator identity, approval
policy, kill-switch observation, operator acknowledgment) and a shared audit
policy fixture. It answers exactly one question:

> Has a human operator reviewed the CAND-007 runtime-readiness envelope and
> confirmed, via local static fixtures, that the kill-switch observation is
> fail-closed or acceptable for a hypothetical future supervised evaluation only,
> with no execution implied — without enabling any execution?

CAND-008 produces a single operator approval gate artifact that records whether
a notional operator-review step and a kill-switch observation check can be
synthesized from the candidate chain, while still refusing all live execution.

### 1.2 Why it follows CAND-007

CAND-007 proved that the candidate chain forms a coherent, internally
consistent, fail-closed runtime readiness envelope without submitting orders or
calling live systems. CAND-008 steps back one more level and asks whether a
human operator review step and a kill-switch observation check can be
synthesized from that envelope without changing the envelope's non-executable
nature. It does not introduce a new execution stage; it introduces a
meta-evaluation stage about operator review evidence and kill-switch
observation policy.

### 1.3 Why it still does not enable live trading or live submit

CAND-008 consumes only local JSON fixtures and previously recorded artifacts. It
does not call brokers, providers, the runtime kill switch, `RiskManager`,
`OrderRouter`, or any approval queue. It does not instantiate `Order`, create
pending orders, load credentials, or mutate runtime state. Its output is a local
artifact, not a trading command.

### 1.4 Difference between operator review evidence, real trade approval, and live order authorization

| Concept | What CAND-008 produces | What CAND-008 does NOT produce |
|---|---|---|
| **Operator review evidence** | A local artifact recording that a static operator identity fixture, an approval policy fixture, a kill-switch observation fixture, and an operator acknowledgment fixture were validated against a closed schema. | Not a record that a real person reviewed real trading risk. |
| **Real trade approval** | None. The approval policy fixture explicitly sets `live_trading_approval: false` and `live_submit_approval: false`. | Not authorization to trade real money or to submit live orders. |
| **Live order authorization** | None. The CLI rejects every flag that could imply live submit, and the acknowledgment fixture requires `acknowledged_no_live_submit: true`. | Not a broker order, pending order, or execution command. |

---

## 2. Scope

CAND-008 may design:

* A local operator review artifact (`operator-approval-gate.json`) and an
  informational Markdown rendering (`operator-approval-gate-report.md`).
* A local approval-attestation schema for the CAND-008 approval policy fixture.
* A local kill-switch observation schema for the CAND-008 kill-switch
  observation fixture.
* Closed-schema validation for CAND-008-owned fixtures.
* Projection validation for CAND-004, CAND-005, CAND-006, and CAND-007 upstream
  artifacts.
* Local policy validation.
* A static contract checker (`scripts/check_operator_approval_gate_contract.py`).
* A CLI contract for `atlas agent operator-approval-gate`.
* Documentation and governance updates.
* Tests to be implemented later.

CAND-008 must not design:

* Broker integration.
* Provider integration.
* Live submit.
* Approval queue mutation.
* Account state mutation.
* Live kill-switch override.
* Real order routing.
* Unattended operation.

---

## 3. Non-scope

Explicitly excluded:

* Live trading.
* Live submit.
* Actual human approval to trade real money.
* Broker certification.
* Profitability review.
* Financial advice.
* Risk approval for real capital.
* Production deployment.
* Release cutover.

---

## 4. Recommended CLI name

**Recommended:** `atlas agent operator-approval-gate`

### 4.1 Alternative names evaluated

| Name | Evaluation |
|---|---|
| `atlas agent operator-approval-gate` | **Recommended.** Includes "operator" and "approval gate", is clearly evidence-only, and does not imply live readiness or submit. |
| `atlas agent approval-gate` | Too generic; could be confused with a real trading approval gate. |
| `atlas agent operator-review` | Vague; does not convey the gate/artifact nature. |
| `atlas agent approval-attestation` | Accurate but less obvious as a CLI command; "attestation" may sound formal. |
| `atlas agent kill-switch-bridge` | Overemphasizes kill switch and underemphasizes the operator-review evidence purpose. |

### 4.2 Name safety rules

The chosen name must not contain any of:

* `live`
* `submit`
* `trade`
* `execute`
* `ready`
* `safe`
* `approve-order`
* `place-order`

---

## 5. Bootstrap routing decision

**Decision:** CAND-008 should use a configless bootstrap route.

### 5.1 Exact route

`src/atlas_agent/cli_bootstrap.py` intercepts when the first two tokens are
exactly:

```text
agent operator-approval-gate
```

This reuses the CAND-006/CAND-007 configless bootstrap pattern.

### 5.2 Tradeoffs evaluated

| Factor | Configless route | Legacy CLI route only |
|---|---|---|
| Prevents config/broker/provider loading on the fast path | Yes | No |
| Prevents accidental import of heavy runtime modules | Yes | No |
| Adds another exact two-token route | Yes (minor) | No |
| Requires import-trace tests | Yes | Not sufficient |
| Keeps `--workspace X` delegation behavior consistent | Yes, by rejecting `--workspace` on the configless route and delegating `atlas --workspace X agent operator-approval-gate` to legacy CLI | Yes |

### 5.3 Mitigations for route sprawl

* Implement exactly one new two-token route.
* Do not add wildcard matching.
* Add import-trace tests that verify the configless route imports no
  `atlas_agent.cli`, broker adapters, provider adapters, `RiskManager`,
  `OrderRouter`, runtime kill switch, or config modules.
* Register a minimal legacy subparser only for `--help` and `--workspace`
  delegation consistency; the legacy subparser must not implement live
  execution paths.

---

## 6. Input schemas

All inputs are local JSON files. Upstream artifacts are validated by projection.
CAND-008-owned fixtures are validated by closed schema.

### 6.1 Upstream projection validation rules

For every upstream artifact (CAND-004, CAND-005, CAND-006, CAND-007):

* Load the full JSON object.
* Scan the full object for secret-like, endpoint-like, and URL/protocol content.
* Extract a closed projection containing only the required fields.
* Validate the projection.
* Allow extra upstream fields.
* Reject missing or wrong-type projected fields.
* Never copy raw upstream artifacts into CAND-008 outputs.

### 6.2 CAND-004 projection (`trading-quality-gate.json`)

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

* `artifact_type` must be exactly `"trading_quality_gate"`.
* `schema_version` must be accepted (`"trading-quality-gate.v1"`, `1`, `"1"`).
* `mode` must be `"paper"`.
* `quality_state` must be exactly `"eligible_for_shadow_live_quality_review"`.
* `blockers` must be an empty list.

### 6.3 CAND-005 projection (`shadow-live-comparison.json`)

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

* `artifact_type` must be exactly `"shadow_live_comparison"`.
* `schema_version` must be exactly `"shadow-live-comparison.v1"`.
* `status` must be exactly `"matched"`.
* `blockers` must be an empty list.

### 6.4 CAND-006 projection (`gated-submit-conformance.json`)

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

* `status` must be exactly `"dry_run_recorded"`.
* `as_of` must be a valid UTC timestamp and must be ≤ CAND-008's `--as-of`.
* CAND-006 evidence age: `(CAND-008 as_of) - (CAND-006 as_of)` must be ≤ 24 hours.
  This is a design choice for freshness, not a security guarantee.
* All `safety_assertions` values must be `true`.
* `dry_run_request.transmission.allowed` must be `false`.
* `dry_run_request.transmission.broker_adapter` and `provider` must both be `null`.
* `blockers` must be an empty list.

### 6.5 CAND-007 projection (`runtime-readiness-envelope.json`)

Required projected keys:

```json
{
  "artifact_type": "runtime_readiness_envelope",
  "schema_version": "runtime-readiness-envelope.v1",
  "candidate": "CAND-007",
  "mode": "simulated_only",
  "status": "readiness_envelope_recorded",
  "exit_code": 0,
  "as_of": "2026-06-24T10:00:00Z",
  "run_id": "<run-id>",
  "symbol": "<SYMBOL>",
  "blockers": [],
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
    "no_account_ids_in_fixtures": true,
    "cand006_transmission_blocked": true
  }
}
```

Validation rules:

* `artifact_type` must be exactly `"runtime_readiness_envelope"`.
* `schema_version` must be exactly `"runtime-readiness-envelope.v1"`.
* `candidate` must be exactly `"CAND-007"`.
* `mode` must be exactly `"simulated_only"`.
* `status` must be exactly `"readiness_envelope_recorded"`.
* `exit_code` must be `0`.
* `blockers` must be an empty list.
* `as_of` must be a valid UTC timestamp and must be ≤ CAND-008's `--as-of`.
* CAND-007 evidence age: `(CAND-008 as_of) - (CAND-007 as_of)` must be ≤ 24 hours.
  This is a design choice for freshness, not a security guarantee.
* All of the following `envelope_assertions` must exist and be `true`:
  * `live_submit_forbidden`
  * `human_approval_required`
  * `kill_switch_required`
  * `risk_gate_required`
  * `audit_recording_required`
  * `broker_manifest_required`
  * `operator_policy_fail_closed`
  * `all_upstream_statuses_accepted`
  * `no_credentials_in_fixtures`
  * `no_endpoints_in_fixtures`
  * `no_account_ids_in_fixtures`
  * `cand006_transmission_blocked`

### 6.6 Audit policy fixture (`audit-policy.json`)

Closed-schema fixture, reused from CAND-007's audit policy fixture pattern.

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

* `artifact_type` must be exactly `"audit_policy_fixture"`.
* `schema_version` must be exactly `"audit-policy-fixture.v1"`.
* `audit_required`, `append_only_required`, `hash_chain_required`, and
  `local_artifact_recording_required` must all be `true`.
* `live_audit_chain_claimed` must be `false`.
* `expires_at` must be strictly later than `--as-of`.

---

## 7. Operator identity fixture design

Closed-schema fixture.

```json
{
  "artifact_type": "operator_identity_fixture",
  "schema_version": "operator-identity-fixture.v1",
  "operator_id": "operator-local-001",
  "operator_role": "local_evidence_reviewer",
  "operator_attestation_scope": "evidence_only",
  "created_at": "2026-06-24T09:00:00Z",
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Allowed keys exactly:

* `artifact_type`
* `schema_version`
* `operator_id`
* `operator_role`
* `operator_attestation_scope`
* `created_at`
* `expires_at`

Validation rules:

* `artifact_type` must be `"operator_identity_fixture"`.
* `schema_version` must be `"operator-identity-fixture.v1"`.
* `operator_id` must be a non-empty string and should use a pseudonymous local
  identifier such as `operator-local-001` or `operator-redacted-reviewer`.
* `operator_role` must be a non-empty string; recommended values are
  `local_evidence_reviewer`, `local_operator_fixture`, or `redacted_reviewer`.
* `operator_attestation_scope` must be `"evidence_only"`.
* `created_at` and `expires_at` must be valid ISO-8601 UTC timestamps.
* `expires_at` must be strictly later than `--as-of`.

Must NOT include:

* Legal identity documents.
* Credentials.
* Account IDs.
* API keys.
* Broker usernames.
* Emails unless explicitly redacted.
* Phone numbers.
* Biometric data.
* Signatures with legal effect.

---

## 8. Approval policy fixture design

Closed-schema fixture.

```json
{
  "artifact_type": "approval_policy_fixture",
  "schema_version": "approval-policy-fixture.v1",
  "requires_manual_review": true,
  "requires_explicit_acknowledgment": true,
  "approval_scope": "evidence_only",
  "live_trading_approval": false,
  "live_submit_approval": false,
  "unattended_operation_allowed": false,
  "max_review_age_seconds": 3600,
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Allowed keys exactly:

* `artifact_type`
* `schema_version`
* `requires_manual_review`
* `requires_explicit_acknowledgment`
* `approval_scope`
* `live_trading_approval`
* `live_submit_approval`
* `unattended_operation_allowed`
* `max_review_age_seconds`
* `expires_at`

Validation rules:

* `artifact_type` must be `"approval_policy_fixture"`.
* `schema_version` must be `"approval-policy-fixture.v1"`.
* `requires_manual_review` must be `true`.
* `requires_explicit_acknowledgment` must be `true`.
* `approval_scope` must be `"evidence_only"`.
* `live_trading_approval` must be `false`.
* `live_submit_approval` must be `false`.
* `unattended_operation_allowed` must be `false`.
* `max_review_age_seconds` must be a positive integer.
* `expires_at` must be strictly later than `--as-of`.

This fixture is a policy statement, not real trade approval.

---

## 9. Kill-switch observation fixture design

Closed-schema fixture.

```json
{
  "artifact_type": "kill_switch_observation_fixture",
  "schema_version": "kill-switch-observation-fixture.v1",
  "kill_switch_required": true,
  "observed_state": "blocked",
  "observed_at": "2026-06-24T10:00:00Z",
  "observation_source": "local_fixture",
  "override_attempted": false,
  "override_allowed": false,
  "default_on_missing": "blocked",
  "default_on_unknown": "blocked",
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Allowed keys exactly:

* `artifact_type`
* `schema_version`
* `kill_switch_required`
* `observed_state`
* `observed_at`
* `observation_source`
* `override_attempted`
* `override_allowed`
* `default_on_missing`
* `default_on_unknown`
* `expires_at`

Validation rules:

* `artifact_type` must be `"kill_switch_observation_fixture"`.
* `schema_version` must be `"kill-switch-observation-fixture.v1"`.
* `kill_switch_required` must be `true`.
* `observed_state` must be one of `"blocked"`, `"inactive"`, `"unknown"`.
* `observed_at` must be a valid ISO-8601 UTC timestamp.
* `observation_source` must be `"local_fixture"`.
* `override_attempted` must be `false`.
* `override_allowed` must be `false`.
* `default_on_missing` must be `"blocked"`.
* `default_on_unknown` must be `"blocked"`.
* `expires_at` must be strictly later than `--as-of`.

Conservative gate rule:

`kill_switch_observation_gate` fails if any of the following are true:

* `observed_state != "blocked"`
* `override_attempted != false`
* `override_allowed != false`
* `default_on_missing != "blocked"`
* `default_on_unknown != "blocked"`

Therefore:

* `observed_state == "blocked"` passes as fail-closed evidence.
* `observed_state == "inactive"` fails the gate in this design. It may be
  recorded as an observation, but it is not treated as permission to trade.
* `observed_state == "unknown"` fails the gate.

This is static fixture validation only. CAND-008 must not call or mutate the
runtime kill switch directly in this design.

---

## 10. Operator acknowledgment fixture design

Closed-schema fixture.

```json
{
  "artifact_type": "operator_acknowledgment_fixture",
  "schema_version": "operator-acknowledgment-fixture.v1",
  "acknowledged_no_live_submit": true,
  "acknowledged_no_trading_authorization": true,
  "acknowledged_no_profitability_claim": true,
  "acknowledged_no_broker_certification": true,
  "acknowledged_review_is_evidence_only": true,
  "acknowledged_unattended_live_forbidden": true,
  "acknowledgment_text_digest": "sha256:...",
  "acknowledged_at": "2026-06-24T10:00:00Z",
  "expires_at": "2026-06-24T12:00:00Z"
}
```

Allowed keys exactly:

* `artifact_type`
* `schema_version`
* `acknowledged_no_live_submit`
* `acknowledged_no_trading_authorization`
* `acknowledged_no_profitability_claim`
* `acknowledged_no_broker_certification`
* `acknowledged_review_is_evidence_only`
* `acknowledged_unattended_live_forbidden`
* `acknowledgment_text_digest`
* `acknowledged_at`
* `expires_at`

Validation rules:

* `artifact_type` must be `"operator_acknowledgment_fixture"`.
* `schema_version` must be `"operator-acknowledgment-fixture.v1"`.
* All `acknowledged_*` boolean fields must be `true`.
* `acknowledgment_text_digest` must be a string starting with `sha256:` and must
  equal the SHA-256 digest of the canonical acknowledgment text defined below.
* `acknowledged_at` and `expires_at` must be valid ISO-8601 UTC timestamps.
* `expires_at` must be strictly later than `--as-of`.

Canonical acknowledgment text (to be digested):

```text
I acknowledge that this operator approval gate (CAND-008) is evidence-only,
simulated-only, and non-executing. It does not authorize live trading, live
submit, real order submission, or unattended operation. It does not certify any
broker, guarantee profitability, or eliminate trading risk. The review is a
local artifact for a hypothetical future supervised evaluation only, with no
execution implied.
```

The digest is computed as `sha256:` + hex(SHA-256 of the canonical text encoded
as UTF-8, with no trailing newline). The canonical text must be present in the
CAND-008 engine source and design documentation. The fixture stores only the
digest, not the full text.

The `operator-approval-gate.json` output artifact must store only the digest,
`acknowledgment_text_digest`, not the literal canonical acknowledgment text.

Must NOT include a legal signature or trade authorization.

---

## 11. Gate sequence

Gates are evaluated in strict fail-closed order. Evaluation stops at the first
failed gate; downstream gates are recorded as `not_run`.

| # | Gate ID | Failure status |
|---|---|---|
| 1 | `schema_preflight` | `not_evaluated` |
| 2 | `cand004_projection_gate` | `upstream_evidence_blocked` |
| 3 | `cand005_projection_gate` | `upstream_evidence_blocked` |
| 4 | `cand006_projection_gate` | `upstream_evidence_blocked` |
| 5 | `cand007_projection_gate` | `runtime_envelope_blocked` |
| 6 | `cross_artifact_correlation_gate` | `blocked` |
| 7 | `operator_identity_gate` | `operator_identity_blocked` |
| 8 | `approval_policy_gate` | `approval_policy_blocked` |
| 9 | `kill_switch_observation_gate` | `kill_switch_observation_blocked` |
| 10 | `operator_acknowledgment_gate` | `operator_acknowledgment_blocked` |
| 11 | `audit_policy_gate` | `audit_policy_blocked` |
| 12 | `approval_gate_synthesis` | `blocked` (pass-only synthesis gate) |
| 13 | `artifact_recording_gate` | `blocked` (if JSON write fails) |

`approval_gate_synthesis` is a pass-only synthesis gate. It sets the temporary
pre-recording status `operator_gate_synthesized` only after all prior gates pass
and the output artifact can be synthesized in memory. If synthesis unexpectedly
fails, the report status is `blocked`, the gate result is `failed`, downstream
`artifact_recording_gate` is `not_run`, and `exit_code` is `2`.

Only successful completion of gate 13 returns exit code `0` and status
`operator_gate_recorded`.

---

## 12. Status model

Exact statuses:

* `not_evaluated`
* `blocked`
* `upstream_evidence_blocked`
* `runtime_envelope_blocked`
* `operator_identity_blocked`
* `approval_policy_blocked`
* `kill_switch_observation_blocked`
* `operator_acknowledgment_blocked`
* `audit_policy_blocked`
* `operator_gate_synthesized`
* `operator_gate_recorded`

The status `operator_gate_synthesized` is an internal pre-recording status. It
is set only after all prior gates pass and the output artifact has been
synthesized in memory. It must not be returned as a final successful CLI status;
only `operator_gate_recorded` may exit with code `0`. It does not imply live
readiness.

The status `operator_gate_recorded` is **evidence-recording status only**. It is
not live readiness, not trading safety, not profitability evidence, not real
human approval to trade, and not permission to submit orders.

Intentionally avoided:

* `approved_for_live`
* `live_ready`
* `safe_to_trade`
* `ready_to_submit`
* `operator_approved_trade`
* any wording that implies live authorization.

---

## 13. Artifact schema

### 13.1 Required artifacts

* `operator-approval-gate.json` (authoritative)
* `operator-approval-gate-report.md` (informational)

### 13.2 `operator-approval-gate.json`

```json
{
  "artifact_type": "operator_approval_gate",
  "schema_version": "operator-approval-gate.v1",
  "candidate": "CAND-008",
  "mode": "evidence_only",
  "status": "operator_gate_recorded",
  "exit_code": 0,
  "evaluation_id": "oag-<digest-prefix>",
  "as_of": "2026-06-24T10:00:00Z",
  "run_id": "run-123",
  "symbol": "AAPL",
  "candidate_chain": [
    "CAND-001", "CAND-002", "CAND-003", "CAND-004",
    "CAND-005", "CAND-006", "CAND-007", "CAND-008"
  ],
  "gate_sequence": [...],
  "gates": [...],
  "input_artifacts": {
    "quality_gate": "trading-quality-gate.json",
    "shadow_comparison": "shadow-live-comparison.json",
    "submit_conformance": "gated-submit-conformance.json",
    "readiness_envelope": "runtime-readiness-envelope.json",
    "operator_identity": "operator-identity.json",
    "approval_policy": "approval-policy.json",
    "kill_switch_observation": "kill-switch-observation.json",
    "operator_acknowledgment": "operator-acknowledgment.json",
    "audit_policy": "audit-policy.json"
  },
  "input_fingerprints": {
    "quality_gate": "sha256:...",
    "shadow_comparison": "sha256:...",
    "submit_conformance": "sha256:...",
    "readiness_envelope": "sha256:...",
    "operator_identity": "sha256:...",
    "approval_policy": "sha256:...",
    "kill_switch_observation": "sha256:...",
    "operator_acknowledgment": "sha256:...",
    "audit_policy": "sha256:..."
  },
  "input_digest": "sha256:...",
  "approval_gate_digest": "sha256:...",
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
    },
    "cand007": {
      "artifact_type": "runtime_readiness_envelope",
      "schema_version": "runtime-readiness-envelope.v1",
      "candidate": "CAND-007",
      "mode": "simulated_only",
      "status": "readiness_envelope_recorded",
      "exit_code": 0,
      "as_of": "2026-06-24T10:00:00Z",
      "blockers": []
    }
  },
  "operator_summary": {
    "operator_id": "operator-local-001",
    "operator_role": "local_evidence_reviewer",
    "operator_attestation_scope": "evidence_only",
    "fixture_status": "valid"
  },
  "approval_policy_summary": {
    "requires_manual_review": true,
    "requires_explicit_acknowledgment": true,
    "approval_scope": "evidence_only",
    "live_trading_approval": false,
    "live_submit_approval": false,
    "unattended_operation_allowed": false,
    "max_review_age_seconds": 3600
  },
  "kill_switch_observation_summary": {
    "kill_switch_required": true,
    "observed_state": "blocked",
    "observed_at": "2026-06-24T10:00:00Z",
    "observation_source": "local_fixture",
    "override_attempted": false,
    "override_allowed": false,
    "default_on_missing": "blocked",
    "default_on_unknown": "blocked"
  },
  "acknowledgment_summary": {
    "acknowledged_no_live_submit": true,
    "acknowledged_no_trading_authorization": true,
    "acknowledged_no_profitability_claim": true,
    "acknowledged_no_broker_certification": true,
    "acknowledged_review_is_evidence_only": true,
    "acknowledged_unattended_live_forbidden": true,
    "acknowledgment_text_digest": "sha256:...",
    "acknowledged_at": "2026-06-24T10:00:00Z"
  },
  "audit_policy_summary": {
    "audit_required": true,
    "append_only_required": true,
    "hash_chain_required": true,
    "local_artifact_recording_required": true,
    "live_audit_chain_claimed": false
  },
  "approval_gate_assertions": {
    "cand007_status_accepted": true,
    "cand007_mode_simulated_only": true,
    "cand007_blockers_empty": true,
    "cand007_safety_assertions_accepted": true,
    "operator_identity_valid": true,
    "approval_policy_fail_closed": true,
    "kill_switch_observed_blocked": true,
    "operator_acknowledgments_all_true": true,
    "audit_policy_fail_closed": true,
    "no_credentials_in_fixtures": true,
    "no_endpoints_in_fixtures": true,
    "no_account_ids_in_fixtures": true,
    "no_raw_upstream_leakage": true
  },
  "blockers": [],
  "recording": {
    "json_written": true,
    "markdown_written": true
  },
  "disclaimer": "Operator approval gate evaluation (CAND-008) — evidence-only and simulated-only. operator_gate_recorded is evidence-recording status only. It is not live readiness, not trading safety, not profitability evidence, not real human approval to trade, and not permission to submit orders."
}
```

### 13.3 `operator-approval-gate-report.md`

Human-readable rendering of the JSON artifact. Sections:

* Header: status, evaluation_id, as_of, symbol, run_id.
* Gate table.
* Upstream evidence summaries.
* Operator summary.
* Kill-switch observation summary.
* Acknowledgment summary.
* Approval policy summary.
* Audit policy summary.
* Approval gate assertions table.
* Blockers list if any.
* Disclaimer including the exact `operator_gate_recorded is evidence-recording
  status only` text.

Must NOT include:

* Raw upstream artifacts.
* Credentials.
* Account IDs.
* Endpoint URLs.
* Broker payloads.
* Provider payloads.
* Legal identity documents.
* Phone numbers.
* Unredacted emails.
* Absolute paths.
* Environment variables.
* Stack traces.

---

## 14. CLI design

### 14.1 Command

```bash
atlas agent operator-approval-gate \
  --quality-gate reports/autonomous_paper_quality/trading-quality-gate.json \
  --shadow-comparison reports/shadow_live/shadow-live-comparison.json \
  --submit-conformance reports/gated_submit_conformance/gated-submit-conformance.json \
  --readiness-envelope reports/runtime_readiness_envelope/runtime-readiness-envelope.json \
  --operator-identity fixtures/operator-identity.json \
  --approval-policy fixtures/approval-policy.json \
  --kill-switch-observation fixtures/kill-switch-observation.json \
  --operator-acknowledgment fixtures/operator-acknowledgment.json \
  --audit-policy fixtures/audit-policy.json \
  --output-dir reports/operator_approval_gate \
  --as-of 2026-06-24T10:00:00Z \
  [--json]
```

### 14.2 Required inputs

| Flag | Description |
|---|---|
| `--quality-gate` | Path to CAND-004 `trading-quality-gate.json`. |
| `--shadow-comparison` | Path to CAND-005 `shadow-live-comparison.json`. |
| `--submit-conformance` | Path to CAND-006 `gated-submit-conformance.json`. |
| `--readiness-envelope` | Path to CAND-007 `runtime-readiness-envelope.json`. |
| `--operator-identity` | Path to CAND-008 operator identity fixture. |
| `--approval-policy` | Path to CAND-008 approval policy fixture. |
| `--kill-switch-observation` | Path to CAND-008 kill-switch observation fixture. |
| `--operator-acknowledgment` | Path to CAND-008 operator acknowledgment fixture. |
| `--audit-policy` | Path to audit policy fixture. |
| `--output-dir` | Output directory for artifacts. |
| `--as-of` | ISO-8601 UTC timestamp used for expiry and evidence-age checks. |

### 14.3 Optional inputs

| Flag | Description |
|---|---|
| `--json` | Emit the report as JSON on stdout. |

### 14.4 Unsafe flags rejected at parse time

The CLI parser rejects these flags with exit code 2:

* `--live`
* `--submit`
* `--broker`
* `--provider`
* `--api-key`
* `--credentials`
* `--endpoint`
* `--account`
* `--account-id`
* `--client-order-id`
* `--place-order`
* `--order-router`
* `--risk-manager`
* `--mode`
* `--kill-switch-override`
* `--approve-live`
* `--approve-submit`
* `--trade`
* `--execute`

Additional live/trade/override-like tokens discovered during implementation are
added to the deny list.

### 14.5 `--workspace` handling

* `atlas agent operator-approval-gate --workspace X` is rejected by the
  configless parser without importing `atlas_agent.cli`.
* `atlas --workspace X agent operator-approval-gate` delegates to the legacy CLI,
  which then dispatches to the CAND-008 subparser. The legacy subparser must not
  implement live execution paths.

### 14.6 Path aliasing

The CLI rejects `--output-dir` or output artifact paths that resolve to the same
filesystem location as any input file or directory, using `Path.resolve()`
comparison and device/inode identity checks.

### 14.7 Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Every gate passed and artifacts recorded (`operator_gate_recorded`). |
| `2` | Any other final status or CLI error. |

---

## 15. Static checker plan

`scripts/check_operator_approval_gate_contract.py`

Checks:

1. Required files exist:
   * `src/atlas_agent/agent/operator_approval_gate.py`
   * `src/atlas_agent/agent/operator_approval_gate_cli.py`
   * `src/atlas_agent/cli_bootstrap.py`
   * `src/atlas_agent/cli.py`
   * `tests/test_operator_approval_gate.py`
   * `tests/test_operator_approval_gate_cli.py`
   * `tests/test_operator_approval_gate_contract.py`
   * `tests/test_operator_approval_gate_import_trace.py`
   * `docs/operator-approval-gate.md`
   * `docs/operator-approval-gate-design.md`
2. Required statuses present in source, in order.
3. Required gate sequence present in source, in order.
4. Required artifact names present: `operator-approval-gate.json`,
   `operator-approval-gate-report.md`.
5. CLI name is `operator-approval-gate` and is wired in bootstrap and legacy CLI.
6. Bootstrap route `agent operator-approval-gate` is present and configless.
7. Unsafe flag deny list is present and covers the required flags.
8. No forbidden imports/calls:
   * `Order`, `OrderRouter`, `RiskManager`.
   * Broker adapters, provider adapters, execution modules.
   * Runtime kill switch.
   * Atlas config loading.
   * Credential/env loading.
   * Network libraries (`requests`, `httpx`, `urllib`, `websocket`, etc.).
   * Live submit/place/cancel/flatten calls.
9. No credentials/env/network loading in engine, CLI, or bootstrap.
10. No live-readiness or trade-approval claims in source or docs.
11. No raw artifact leakage:
    * Output JSON does not contain raw upstream artifacts.
    * Markdown does not contain raw upstream artifacts.
12. No active docs claiming approval to trade.
13. No forbidden statuses (`approved_for_live`, `safe_to_trade`,
    `ready_to_submit`) in source or docs.
14. `operator_gate_synthesized` is not returned as a final CLI success status;
    only `operator_gate_recorded` may produce exit code `0`.
15. Disclaimer present in source, docs, JSON artifact schema, and Markdown
    rendering.
16. Stale-doc prevention: fail if docs regress to claiming CAND-008 is not
    designed or that it authorizes live trading.
17. CAND-007 projection rules are present:
    * `status == "readiness_envelope_recorded"`
    * `mode == "simulated_only"`
    * `candidate == "CAND-007"`
    * `blockers == []`
    * required safety assertions are checked.
18. Operator identity, approval policy, kill-switch observation, and operator
    acknowledgment fixture schemas are present.
19. Acknowledgment canonical text and digest computation are present.

---

## 16. Test plan

### 16.1 Engine tests (`tests/test_operator_approval_gate.py`)

1. `test_valid_all_pass_operator_gate`
2. `test_missing_cand004_blocks`
3. `test_cand004_wrong_quality_state_blocks`
4. `test_missing_cand005_blocks`
5. `test_cand005_not_matched_blocks`
6. `test_missing_cand006_blocks`
7. `test_cand006_status_not_dry_run_recorded_blocks`
8. `test_cand006_blockers_non_empty_blocks`
9. `test_missing_cand007_blocks`
10. `test_cand007_status_not_readiness_envelope_recorded_blocks`
11. `test_cand007_blockers_non_empty_blocks`
12. `test_cand007_mode_not_simulated_only_blocks`
13. `test_cand007_candidate_not_cand007_blocks`
14. `test_cand007_safety_assertion_false_blocks`
15. `test_cand007_operator_policy_fail_closed_false_blocks`
16. `test_cand007_all_upstream_statuses_accepted_false_blocks`
17. `test_cand007_cand006_transmission_blocked_false_blocks`
18. `test_run_id_mismatch_blocks`
16. `test_symbol_mismatch_blocks`
17. `test_missing_operator_identity_blocks`
18. `test_expired_operator_identity_blocks`
19. `test_operator_identity_unknown_field_blocks`
20. `test_approval_policy_live_trading_approval_true_blocks`
21. `test_approval_policy_live_submit_approval_true_blocks`
22. `test_approval_policy_unattended_allowed_blocks`
23. `test_approval_policy_unknown_field_blocks`
24. `test_kill_switch_observation_unknown_blocks`
25. `test_kill_switch_observation_inactive_blocks`
26. `test_kill_switch_override_attempted_blocks`
27. `test_kill_switch_override_allowed_true_blocks`
28. `test_kill_switch_default_on_missing_not_blocked_blocks`
29. `test_kill_switch_default_on_unknown_not_blocked_blocks`
30. `test_operator_acknowledgment_missing_no_live_submit_blocks`
31. `test_operator_acknowledgment_missing_no_trading_authorization_blocks`
32. `test_operator_acknowledgment_digest_mismatch_blocks`
33. `test_audit_policy_invalid_blocks`
34. `test_secret_like_fields_rejected`
35. `test_endpoint_like_fields_rejected`
36. `test_url_protocol_values_rejected`
37. `test_raw_artifact_leakage_rejected`
38. `test_output_path_aliasing_rejected`
39. `test_json_and_markdown_agree`
40. `test_json_write_failure_rolls_back_status`
41. `test_synthesis_failure_returns_blocked`
42. `test_operator_gate_synthesized_is_not_final_success`
43. `test_only_operator_gate_recorded_exits_zero`
44. `test_disclaimer_present_in_json_and_markdown`
42. `test_disclaimer_present_in_json_and_markdown`

### 16.2 CLI tests (`tests/test_operator_approval_gate_cli.py`)

* Help output contains safety disclaimer.
* JSON output mode works.
* Missing required flag returns exit code 2.
* Each unsafe flag returns exit code 2.

### 16.3 Import-trace tests (`tests/test_operator_approval_gate_import_trace.py`)

* Configless route imports no forbidden modules.
* Help route imports no `atlas_agent.cli`.
* Valid route imports no `atlas_agent.cli`.
* `atlas agent operator-approval-gate --workspace X` is configless and rejected
  without importing `atlas_agent.cli`.
* `atlas --workspace X agent operator-approval-gate` delegates to legacy CLI.
* `atlas run --mode live` remains fail-closed.
* `test_forbidden_modules_not_imported_on_any_configless_route`: all
  configless routes (CAND-006, CAND-007, CAND-008) avoid importing legacy
  CLI/config, broker adapters, provider adapters, risk, execution, and safety
  modules.

---

## 17. Docs/governance/release metadata plan

### 17.1 New/modified files

* `docs/operator-approval-gate-design.md` (this document).
* `docs/operator-approval-gate.md` — user-facing command documentation.
* `docs/autonomy-roadmap.md` — add CAND-008 as a planning-only operator review
  stage.
* `docs/bounded-live-autonomy-governance.md` — add CAND-008 to the staged
  autonomy ladder as a planning-only, evidence-only operator review stage.
* `docs/runtime-readiness-envelope.md` — add forward reference to CAND-008 as
  the next operator review stage.
* `docs/releases/v0.6.16-plan.md` — add CAND-008 as a proposed candidate.
* `docs/releases/v0.6.16-candidates.md` — add CAND-008 as a proposed candidate.
* `docs/releases/v0.6.16-candidate-selection.md` — add "Why CAND-008 is
  eligible" section as a proposed candidate.
* `docs/releases/v0.6.16-candidates.json` — add CAND-008 candidate object with
  `status: "proposed"`.
* `CHANGELOG.md` — add CAND-008 planning-only entry under `[Unreleased]`.

### 17.2 Must preserve

* `v0.6.15` is the current public release.
* Source/package version remains `0.6.15`.
* `v0.6.16` remains candidate/planning-only.
* No tag.
* No GitHub Release.
* No PyPI publication.
* No live-readiness claim.

---

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Operator approval artifact mistaken for real trading approval. | Status is `operator_gate_recorded`, not `approved_for_live`. Approval policy fixture has `live_trading_approval: false` and `live_submit_approval: false`. Every doc and artifact carries the evidence-only disclaimer. |
| Kill-switch observation mistaken for override. | Fixture has `override_attempted: false` and `override_allowed: false`. CAND-008 does not call the runtime kill switch. Gate only passes for `observed_state == "blocked"`. |
| Evidence-only acknowledgment mistaken for legal signature. | Fixture is named `operator_acknowledgment_fixture`, not "signature". It stores a digest of canonical disclaimer text, not a legal signature. Docs explicitly state it is not a trade authorization. |
| Approval policy fixture mistaken for production policy. | Fixture is named `approval_policy_fixture`. Scope is `"evidence_only"`. All live/unattended flags are `false`. |
| Configless route sprawl. | Only one new exact two-token route. Import-trace tests cover all configless routes. |
| CAND-008 moving too close to live submit. | CLI rejects all live/submit/trade/execute flags. No runtime trading objects are instantiated. Output is a local artifact only. |
| Docs accidentally implying live readiness. | Static checker enforces disclaimer presence and forbids live-readiness phrases. All status names are evidence-only. |
| Stale or replayed `operator-approval-gate.json` mistaken for current evidence. | Artifacts include `as_of`, fixture `expires_at`, and `evaluation_id`. Evidence-age checks bound freshness. Consumers must validate age and digest before relying on any artifact. |
| Fixture substitution with a permissive operator identity or approval policy. | Closed schemas reject unknown keys and require conservative flag values. Fixtures live in a controlled directory. Input fingerprints detect tampering. |
| Path traversal or output/input aliasing. | CLI rejects `--output-dir` or output paths that resolve to the same filesystem location as any input. |
| The 24-hour evidence-age window is mistaken for a real-time safety guarantee. | The window is a design choice, not a security guarantee. It bounds stale evidence but does not prove current market or system safety. |

---

## 19. Recommended implementation approach

If CAND-008 is implemented later, the recommended order is:

1. Scaffold the engine module `src/atlas_agent/agent/operator_approval_gate.py`
   with constants, dataclasses, and helpers.
2. Implement projection validators for CAND-004, CAND-005, CAND-006, and
   CAND-007.
3. Implement closed-schema validators for CAND-008-owned fixtures and the audit
   policy fixture.
4. Implement the universal rejection scanner for secret/endpoint/URL content.
5. Implement the fail-closed gate sequence.
6. Implement artifact writers for JSON and Markdown.
7. Implement the configless CLI handler
   `src/atlas_agent/agent/operator_approval_gate_cli.py`.
8. Add the exact two-token bootstrap route in `src/atlas_agent/cli_bootstrap.py`
   and a minimal legacy subparser in `src/atlas_agent/cli.py`.
9. Add engine, CLI, contract, and import-trace tests.
10. Implement `scripts/check_operator_approval_gate_contract.py`.
11. Update documentation and release metadata.
12. Run full validation: `pytest`, `atlas validate`, `scripts/dev_check.sh`,
    `scripts/release_check.sh --quick`.

No implementation is authorized by this design document.

---

## 20. Reviewer checklist

* [ ] The design does not authorize live trading, live submit, or real order
      submission.
* [ ] The design does not instantiate `Order`, `OrderRouter`, `RiskManager`,
      `ApprovalManager`, or runtime kill-switch objects.
* [ ] The design does not load credentials, API keys, account IDs, or broker
      endpoints.
* [ ] The design does not mutate approval queues, account state, or broker
      state.
* [ ] The design uses projection validation for upstream artifacts and never
      copies raw upstream artifacts into outputs.
* [ ] The CAND-007 projection requires `status == "readiness_envelope_recorded"`,
      `mode == "simulated_only"`, `candidate == "CAND-007"`, and `blockers == []`.
* [ ] The operator identity fixture uses a pseudonymous local identifier and
      excludes legal identity documents, credentials, and signatures.
* [ ] The approval policy fixture sets `live_trading_approval: false`,
      `live_submit_approval: false`, and `unattended_operation_allowed: false`.
* [ ] The kill-switch observation fixture only passes for `observed_state ==
      "blocked"` and does not represent an override.
* [ ] The operator acknowledgment fixture requires all six acknowledgments and
      stores a digest of canonical disclaimer text, not a legal signature.
* [ ] The CLI name does not imply live readiness or order submission.
* [ ] The unsafe-flag deny list covers all flags in the design.
* [ ] The bootstrap route is configless and import-trace tested.
* [ ] The artifact schema excludes raw upstream artifacts, credentials, account
      IDs, endpoints, and absolute paths.
* [ ] The status model contains no live-readiness or trade-approval statuses.
* [ ] The disclaimer appears in source, docs, JSON, and Markdown.
* [ ] Release metadata remains planning-only: no version bump, tag, GitHub
      Release, or PyPI publication.
* [ ] `atlas run --mode live` remains fail-closed.
