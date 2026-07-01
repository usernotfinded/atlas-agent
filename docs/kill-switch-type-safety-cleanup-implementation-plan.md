# CAND-011: Kill-Switch `last_heartbeat()` Type-Safety Cleanup Implementation Plan

> I'm using the `writing-plans` skill to create the implementation plan.
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Planning-only note:** This document is planning-only per the task brief. Do not implement code here; implementation requires a separate protected-boundary implementation prompt and review.

**Goal:** Implement a one-line-equivalent type-safety cleanup in `src/atlas_agent/safety/kill_switch.py` that eliminates the pre-existing mypy `union-attr` warning on `last_heartbeat().isoformat()`, plus a minimal regression test covering the `heartbeat_expired` audit payload shape, without changing runtime behavior or any safety boundary.

**Architecture:** Replace the repeated `self.heartbeat_manager.last_heartbeat()` call in the audit payload expression with a single local variable narrowed by an explicit `is not None` check, then use the narrowed ISO string (or `None`) in the unchanged `last_heartbeat` payload key. Add two small tests to `tests/safety/test_kill_switch_v2.py` that capture audit events and assert the payload value is an ISO string for a stale heartbeat and `None` for a corrupt heartbeat.

**Tech Stack:** Python 3.11+, mypy, pytest, ruff (already available in environment). No broker/provider/config imports, no credential loading, no network access.

**Plan location note:** The repository does not have a dedicated implementation-plans directory. The user specified `docs/kill-switch-type-safety-cleanup-implementation-plan.md`, so this plan is saved at that path, mirroring the CAND-010 implementation plan convention.

---

## 1. Title and candidate ID

- **Candidate ID:** CAND-011
- **Title:** Kill-Switch `last_heartbeat()` Type-Safety Cleanup
- **Target release line:** v0.6.19
- **Current public release:** v0.6.19
- **Package version:** 0.6.19
- **Status:** released in `v0.6.19`; plan was accepted into the `v0.6.19`
  candidate chain, implemented, independently reviewed, and released
- **Design document:** `docs/kill-switch-type-safety-cleanup-design.md`
- **Design review verdict:** `PASS`
- **Implementation-plan review verdict:** `PASS`
- **Implementation review verdict:** `PASS`
- **Implementation commit:** `57e1ac85fa5530fa9b78a626dfdc7993cbea4b63`
- **Acceptance commit:** `1131eebc6f795720a6466a388d7459ff05f5fa58`
- **Release date:** 2026-07-01
- **Acceptance date:** 2026-07-01
- **Independent design review recommendation:** Proceed to a separate implementation-plan prompt. The implementation must include or require a minimal regression test for the `heartbeat_expired` audit payload shape, because existing tests cover the decision path but not the audit payload branch.

---

## 2. Baseline state

| Item | Value |
|---|---|
| Repository | `usernotfinded/atlas-agent` |
| Branch | `main` |
| Planning HEAD | `dacf8ec4aae7b03863cc96ac1cabf47f00c44b1c` |
| Design document | `docs/kill-switch-type-safety-cleanup-design.md` |
| Design review verdict | `PASS` |
| Public release | `v0.6.19` |
| Package version | `0.6.19` |
| Candidate line | `v0.6.19` |
| Next planned release | `v0.6.20` |
| Release status | `v0.6.19` is released as a GitHub-only release |
| PyPI published | `false` |
| Live mode | fail-closed (`atlas run --mode live` exits 2) |

### Phase 0 baseline verification (already run during planning)

```bash
git status --short
git rev-parse HEAD
git log --oneline -20
git tag --points-at HEAD
git rev-parse v0.6.18^{}
gh release view v0.6.18
python3.11 - <<'PY'
import atlas_agent
print(atlas_agent.__version__)
PY
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
python3.11 scripts/check_safety_atomic_write.py
atlas validate
atlas run --mode live
git diff --check
```

Observed results during planning:

- Tree is clean (`git status --short` empty).
- HEAD is `dacf8ec4aae7b03863cc96ac1cabf47f00c44b1c` (design-doc commit after v0.6.18 release cutover).
- `v0.6.18` tag dereferences to `f079a8fe05218ce1a8f3d3b64fa270071733782c` (the release commit), not the design-doc HEAD. This is expected because the design doc and this plan are commits on `main` after the annotated release tag.
- GitHub Release `v0.6.18` exists as a GitHub-only release.
- Package version is `0.6.18`.
- `check_version_consistency.py`, `check_release_metadata.py`, `check_forbidden_claims.py`, `check_bounded_autonomy_governance.py`, `check_cli_command_compatibility.py`, and `check_safety_atomic_write.py` all exit 0.
- `atlas validate` reports workspace/config missing but no errors.
- `atlas run --mode live` exits 2 / fail-closed.
- `git diff --check` exits 0.

---

## 3. Design-review summary

The independent protected-boundary design review of `docs/kill-switch-type-safety-cleanup-design.md` returned `PASS` and recommended proceeding to this implementation-plan prompt.

Key findings incorporated into this plan:

1. **Audit payload coverage gap.** Existing tests in `tests/safety/test_kill_switch_v2.py` verify the `heartbeat_expired` decision path (`decision.allowed is False`, reason contains "heartbeat expired"), but none capture the audit event payload. This plan makes the audit-payload regression test **mandatory**, not optional.

2. **Pre-existing lint warnings are out of scope.** `ruff check tests/safety/test_kill_switch_v2.py` reports unused imports (`Path`, `KillSwitchStatus`, `KillSwitchDecision`) that pre-date CAND-011. The implementation must not perform unrelated lint cleanup. Any new test code should reuse existing imports where possible but must not expand scope to fix pre-existing warnings.

3. **Local-variable narrowing is the minimal fix.** The design proposes computing `last_heartbeat` once and converting it to an ISO string only when not `None`. This plan preserves that exact shape.

---

## 4. Exact warning and root cause

### Observed warning

```text
src/atlas_agent/safety/kill_switch.py:46: error: Item "None" of "datetime | None" has no attribute "isoformat"  [union-attr]
Found 1 error in 1 file (checked 1 source file)
```

### Root cause

In `AdvancedKillSwitch.evaluate`, the audit payload is built with:

```python
payload={"last_heartbeat": self.heartbeat_manager.last_heartbeat().isoformat() if self.heartbeat_manager.last_heartbeat() else None}
```

`HeartbeatManager.last_heartbeat()` returns `datetime | None`. The conditional expression calls the method once in the condition and, if truthy, calls it again and invokes `.isoformat()`. mypy treats the two calls as independent nullable evaluations and does not narrow the second call based on the first, so it flags `.isoformat()` as potentially operating on `None`.

### Nature of the issue

- **Static-analysis only.** The warning does not indicate a runtime bug under normal conditions because Python's short-circuit evaluation guarantees the true branch runs only when the condition value is truthy.
- **Minor race condition.** Because `last_heartbeat()` reads the heartbeat file from disk, two successive calls could theoretically observe different values if the file is deleted or corrupted between the condition and the `.isoformat()` call. The cleanup removes this narrow race by reading once.
- **No safety defect.** The kill-switch decision is made before the audit payload is constructed; the warning does not affect fail-closed behavior.

---

## 5. Implementation scope

In scope for CAND-011 implementation:

1. Modify the audit payload construction in `src/atlas_agent/safety/kill_switch.py:46` to narrow `self.heartbeat_manager.last_heartbeat()` to a local variable.
2. Add a minimal regression test in `tests/safety/test_kill_switch_v2.py` covering the `heartbeat_expired` audit payload shape for both the ISO-string branch and the `None` branch.
3. Update `docs/kill-switch-type-safety-cleanup-implementation-plan.md` to mark planning complete and note any deviations.

Out of scope (non-goals) are listed in Section 6.

---

## 6. Non-goals

CAND-011 implementation explicitly does **not**:

- Enable live trading or live submit.
- Place, cancel, or flatten orders.
- Create pending orders or mutate approval queues.
- Call brokers, providers, or network endpoints.
- Load credentials, secrets, or API keys.
- Change kill-switch mode escalation, decision logic, return values, or fail-closed semantics.
- Change `HeartbeatManager` behavior, file format, or public API.
- Change the audit event type (`heartbeat_expired`) or payload key name (`last_heartbeat`).
- Change the audit payload value shape (must remain `str | None`).
- Add `fsync`, third-party dependencies, or new runtime logic.
- Bump version, tag, release, or publish to PyPI.
- Create a v0.6.19 release cutover or planning file beyond this plan.
- Address unrelated ruff warnings in `tests/test_release_assurance.py`.
- Address unrelated ruff warnings in `tests/safety/test_kill_switch_v2.py` that pre-date CAND-011.
- Address the optional full-check timeout warning.

---

## 7. Protected-boundary controls

| Attribute | Value |
|---|---|
| File touched | `src/atlas_agent/safety/kill_switch.py` |
| Boundary type | Safety runtime boundary |
| Function / method affected | `AdvancedKillSwitch.evaluate` |
| Reason for touching the boundary | Approved CAND-011 type-safety cleanup only |
| Intended behavior change | None |
| Maximum allowed runtime diff | Local-variable narrowing only inside the existing `if mode != "locked_down" and self.heartbeat_manager.is_expired():` block |
| Maximum allowed test diff | Audit payload regression coverage in `tests/safety/test_kill_switch_v2.py` only |
| Required review after implementation | Independent implementation review before merge |
| Release impact | v0.6.19 candidate only; not a release cutover |
| Rollback | Revert single implementation commit |

No release cutover, no tag, no GitHub Release edit, and no PyPI action are authorized by this plan.

---

## 8. Proposed code-change plan

### 8.1 File to modify

- `src/atlas_agent/safety/kill_switch.py`

### 8.2 Exact change

Inside `AdvancedKillSwitch.evaluate`, replace the single-line payload expression with a two-step local narrowing:

**Before:**

```python
        if mode != "locked_down" and self.heartbeat_manager.is_expired():
            if self.audit_writer:
                self.audit_writer.write_event(
                    "heartbeat_expired",
                    run_id=self.run_id,
                    iteration=self.iteration,
                    payload={"last_heartbeat": self.heartbeat_manager.last_heartbeat().isoformat() if self.heartbeat_manager.last_heartbeat() else None}
                )
```

**After:**

```python
        if mode != "locked_down" and self.heartbeat_manager.is_expired():
            last_heartbeat = self.heartbeat_manager.last_heartbeat()
            last_heartbeat_iso = (
                last_heartbeat.isoformat()
                if last_heartbeat is not None
                else None
            )
            if self.audit_writer:
                self.audit_writer.write_event(
                    "heartbeat_expired",
                    run_id=self.run_id,
                    iteration=self.iteration,
                    payload={"last_heartbeat": last_heartbeat_iso},
                )
```

### 8.3 Constraints

- The change is limited to the audit payload construction inside `AdvancedKillSwitch.evaluate`.
- No other method, class, or file is modified.
- No logic around `is_expired()`, mode escalation, kill-switch decisions, or return values changes.
- The `payload` dict retains the same key (`last_heartbeat`) and the same value shape (`str | None`).
- No new imports are required.
- No new dependencies are introduced.

### 8.4 Why this is behavior-preserving

- **Single read, same value.** `last_heartbeat()` reads the heartbeat file and returns either a `datetime` or `None`. The proposed code reads it once and uses that same value for both the narrowing check and the `.isoformat()` call. This is deterministic equivalent or strictly safer than the current code, which may read twice.
- **Same branch outcomes.** When `last_heartbeat` is `None`, `last_heartbeat_iso` is `None`. When it is a `datetime`, `last_heartbeat_iso` is its ISO string. This matches today's payload exactly.
- **Same kill-switch decision.** The decision is constructed on lines 48-54 and is independent of the audit payload value. It remains unchanged.
- **Same fail-closed behavior.** The audit write still occurs only when `is_expired()` is `True`. No execution path is unblocked.

---

## 9. Mandatory test-change plan

### 9.1 File to modify

- `tests/safety/test_kill_switch_v2.py`

### 9.2 Why this file

`tests/safety/test_kill_switch_v2.py` already tests `AdvancedKillSwitch.evaluate` (including heartbeat expiry). It is the natural place to add audit payload coverage. `tests/safety/test_kill_switch_core.py` tests the legacy `KillSwitchController`, not `AdvancedKillSwitch`, so it is not appropriate for this regression test.

### 9.3 Capturing audit writer helper

Use the same lightweight in-memory audit writer pattern already implied by the design doc:

```python
class _CapturingAuditWriter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def write_event(self, event_type: str, *, run_id: str, iteration: int | None, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))
```

Place this class at module level in `tests/safety/test_kill_switch_v2.py` so both new tests can reuse it.

### 9.4 Test 1: stale heartbeat produces ISO string payload

Add:

```python
def test_heartbeat_expired_audit_payload_contains_iso_string(safety_paths):
    state_path, hb_path = safety_paths
    writer = _CapturingAuditWriter()
    ks = AdvancedKillSwitch(
        state_path=state_path,
        heartbeat_path=hb_path,
        audit_writer=writer,
    )

    old_ts = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    hb_path.write_text(json.dumps({"timestamp": old_ts, "source": "test"}))
    ks.heartbeat_manager.timeout_seconds = 300

    decision = ks.evaluate()
    assert decision.allowed is False
    assert "heartbeat expired" in decision.reason.lower()

    heartbeat_events = [event for event_type, event in writer.events if event_type == "heartbeat_expired"]
    assert len(heartbeat_events) == 1
    payload = heartbeat_events[0]
    assert "last_heartbeat" in payload
    assert isinstance(payload["last_heartbeat"], str)
    # Verify it is a parseable ISO datetime.
    datetime.fromisoformat(payload["last_heartbeat"])
```

### 9.5 Test 2: corrupt heartbeat produces `None` payload

Add:

```python
def test_corrupt_heartbeat_expired_audit_payload_last_heartbeat_is_none(safety_paths):
    state_path, hb_path = safety_paths
    hb_path.write_text("not-json", encoding="utf-8")

    writer = _CapturingAuditWriter()
    ks = AdvancedKillSwitch(
        state_path=state_path,
        heartbeat_path=hb_path,
        audit_writer=writer,
    )
    ks.heartbeat_manager.timeout_seconds = 1

    decision = ks.evaluate()
    assert decision.allowed is False
    assert "heartbeat expired" in decision.reason.lower()

    heartbeat_events = [event for event_type, event in writer.events if event_type == "heartbeat_expired"]
    assert len(heartbeat_events) == 1
    payload = heartbeat_events[0]
    assert "last_heartbeat" in payload
    assert payload["last_heartbeat"] is None
```

### 9.6 Test constraints

- Do not add real network, broker, provider, credential, or disk-write behavior beyond the existing test conventions.
- Do not depend on wall-clock timing; use explicit old timestamps and `timeout_seconds`.
- Do not remove or alter existing tests.
- Do not import or introduce new fixtures beyond the existing `safety_paths` fixture.

---

## 10. Behavior-preservation argument

### 10.1 Same audit payload

- **Key name:** `last_heartbeat` (unchanged).
- **Value shape:** ISO-8601 string when heartbeat exists, `None` otherwise (unchanged).

### 10.2 Same kill-switch decisions

The change occurs after `self.heartbeat_manager.is_expired()` has already returned `True` and immediately before the audit write. The kill-switch decision (`allowed=False`, `status="blocked"`, `reason="Dead-man heartbeat expired. Execution blocked for safety."`, `diagnostics={"heartbeat_expired": True}`) is constructed independently of the payload value and is unchanged.

### 10.3 Same fail-closed behavior

`last_heartbeat()` still returns `None` for a missing or corrupt heartbeat file, and the local narrowing still produces `None` in that case. The audit event is still written only when `is_expired()` is `True`. No path is created that would allow execution when the heartbeat is expired.

### 10.4 Strict improvement in robustness

The current code can raise `AttributeError` only in the extremely unlikely event that the second `last_heartbeat()` call returns `None` while the condition call returned a `datetime`. The proposed code cannot raise `AttributeError` because `.isoformat()` is guarded by an explicit `is not None` check. This is a strict improvement; no existing exception type is newly introduced.

### 10.5 Call-count semantics

Current code calls `last_heartbeat()` once or twice depending on the branch. Proposed code calls it exactly once. Because `last_heartbeat()` reads external state, reducing the call count removes a narrow inter-call race and makes the observed value consistent between the narrowing check and the `.isoformat()` call. This is behavior-preserving in the observable audit payload and a strict improvement in determinism.

### 10.6 No side effects added or removed

`last_heartbeat()` has no write side effects; it only reads the heartbeat file and logs a warning on corruption. The proposed change does not add network, broker, provider, credential, or disk-write behavior.

---

## 11. Safety invariants

The implementation must preserve the following invariants. Any implementation that violates these is rejected.

1. No live trading enablement.
2. No live submit enablement.
3. No order placement, cancellation, or flattening.
4. No pending orders created.
5. No approval queue mutation.
6. No broker/provider calls.
7. No credential loading.
8. No network access.
9. No weakening of `RiskManager`.
10. No weakening of kill switch, deadman, heartbeat, or audit hash-chain.
11. No audit hash-chain bypass.
12. `atlas run --mode live` remains exit 2 / fail-closed.
13. Package version is `0.6.19`.
14. Public release is `v0.6.19`.
15. No v0.6.20 tag, GitHub Release, or PyPI publication is created.
16. The `heartbeat_expired` audit payload retains key `last_heartbeat` with value shape `str | None`.
17. `AdvancedKillSwitch.evaluate` returns the same `KillSwitchDecision` for the same inputs.
18. `HeartbeatManager.last_heartbeat()` is not modified.
19. The atomic-write regression guard (`scripts/check_safety_atomic_write.py`) continues to pass.

---

## 12. Verification matrix

### Phase 0 — Baseline verification (already run during planning)

```bash
git status --short
git rev-parse HEAD
git log --oneline -20
git tag --points-at HEAD
git rev-parse v0.6.18^{}
gh release view v0.6.18
python3.11 - <<'PY'
import atlas_agent
print(atlas_agent.__version__)
PY
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
python3.11 scripts/check_safety_atomic_write.py
atlas validate
atlas run --mode live
git diff --check
```

Expected:

- Clean tree.
- HEAD is `dacf8ec4aae7b03863cc96ac1cabf47f00c44b1c` (or later docs-only commit).
- `v0.6.18` tag dereferences to `f079a8fe05218ce1a8f3d3b64fa270071733782c`.
- GitHub Release `v0.6.18` exists as GitHub-only.
- `atlas_agent.__version__` is `0.6.18`.
- `atlas run --mode live` exits 2.
- All other commands exit 0.

### Phase 1 — Implementation-plan-doc-only verification

After writing only this implementation-plan document, run:

```bash
git diff --check
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_safety_atomic_write.py
atlas run --mode live
```

Expected:

- Docs-only diff.
- All commands exit 0 except `atlas run --mode live`, which exits 2.

### Phase 2 — Implementation acceptance

After CAND-011 is implemented, run:

```bash
git diff --check
python3.11 -m compileall src scripts
mypy src/atlas_agent/safety/kill_switch.py
python3.11 -m pytest tests/safety/test_kill_switch_core.py tests/safety/test_kill_switch_v2.py -q
python3.11 -m pytest tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py tests/safety/test_atomic_write.py -q
python3.11 scripts/check_safety_atomic_write.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_cli_command_compatibility.py
atlas validate
atlas run --mode live
bash scripts/release_check.sh --quick
```

If available:

```bash
ruff check src/atlas_agent/safety/kill_switch.py tests/safety/test_kill_switch_core.py tests/safety/test_kill_switch_v2.py
```

Expected:

- All commands exit 0 except `atlas run --mode live`, which must exit 2.
- `mypy src/atlas_agent/safety/kill_switch.py` reports no errors.
- The new audit payload regression tests pass.
- Existing safety tests pass.
- `ruff check src/atlas_agent/safety/kill_switch.py` reports no new errors. Pre-existing warnings in `tests/safety/test_kill_switch_v2.py` may remain and are not blockers for CAND-011.

Optional if time permits:

```bash
python3.11 -m pytest -q --durations=25
bash scripts/release_check.sh
```

---

## 13. Rollback plan

If CAND-011 causes regressions after implementation:

1. Revert the single edit in `src/atlas_agent/safety/kill_switch.py`.
2. Revert the two new tests added to `tests/safety/test_kill_switch_v2.py`.
3. Re-run the Phase 2 verification matrix.
4. The system returns to the `v0.6.18` state, which remains fail-closed.

---

## 14. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Accidental logic change in `evaluate` | Medium | Keep the edit inside the existing `if` block; do not reorder, remove, or alter any `return` statement or decision field. |
| Audit payload shape change | Low | Preserve the dict literal key `last_heartbeat` and produce `str | None` exactly as today. |
| `last_heartbeat()` semantics change | Low | Do not modify `HeartbeatManager`; only consume its return value. |
| Mypy still reports an error | Low | Use explicit `is not None` narrowing; avoid `bool()`-style checks that mypy may not narrow. |
| Fail-closed behavior weakened | Very low | The change is after the `is_expired()` check and before the audit write; it cannot unblock execution. |
| Release metadata/version drift | Very low | Do not modify `pyproject.toml`, `src/atlas_agent/__init__.py`, or `docs/releases/release-metadata.json`. |
| Unrelated lint cleanup creep | Low | Do not fix pre-existing ruff warnings in `test_kill_switch_v2.py` or `test_release_assurance.py` as part of this change. |
| New test is brittle | Low | Use explicit timestamps and `timeout_seconds`; avoid wall-clock sleeps. |

---

## 15. Acceptance criteria

- [ ] `docs/kill-switch-type-safety-cleanup-implementation-plan.md` exists and contains all sections required by the CAND-011 brief.
- [ ] Implementation modifies only the audit payload construction in `src/atlas_agent/safety/kill_switch.py` and the two companion regression tests in `tests/safety/test_kill_switch_v2.py`.
- [ ] The `last_heartbeat` audit payload key and `str | None` value shape are preserved.
- [ ] No kill-switch decision logic, fail-closed behavior, or public API is changed.
- [ ] `mypy src/atlas_agent/safety/kill_switch.py` reports no errors after implementation.
- [ ] The new audit payload regression tests pass.
- [ ] Existing safety-module tests still pass.
- [ ] `atlas run --mode live` still exits 2.
- [ ] `scripts/check_safety_atomic_write.py` still passes.
- [ ] No live trading, live submit, broker/provider execution, credential loading, or order placement is introduced.
- [ ] Package version is `0.6.19`; current public release is `v0.6.19`; next planned release is `v0.6.20`; PyPI remains unpublished.

---

## 16. Implementation-readiness verdict

**READY_FOR_IMPLEMENTATION**

The plan is complete and no further docs-only fix is needed before implementation. The specification is intentionally minimal: one local-variable narrowing in a single safety-boundary file and two small regression tests, with no runtime behavior change. A separate independent implementation review is still required before the code change is accepted.

---

## 17. Final recommendation

**Approve this implementation plan and proceed to a separate CAND-011 implementation prompt.**

CAND-011 is the safest first v0.6.19 candidate: it removes a known type-check warning in a protected safety file without changing runtime behavior, decisions, audit shape, or any safety boundary. The mandatory audit-payload regression test closes the coverage gap identified during independent design review.

After implementation, an independent implementation review should re-run the Phase 2 verification matrix and confirm `mypy src/atlas_agent/safety/kill_switch.py` reports zero errors while `atlas run --mode live` remains exit 2.
