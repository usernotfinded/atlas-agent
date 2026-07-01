# CAND-011: Kill-Switch `last_heartbeat()` Type-Safety Cleanup

## Design Specification

**Candidate ID:** CAND-011
**Candidate line:** v0.6.19
**Current public release:** v0.6.18
**Status:** accepted into the `v0.6.19` candidate chain; implementation complete and reviewed
**Date:** 2026-07-01
**Design document path:** `docs/kill-switch-type-safety-cleanup-design.md`

> **Design-only disclaimer.** This document originally specified CAND-011. The
> design was approved, implemented, independently reviewed, and accepted into
> the `v0.6.19` candidate chain with no release cutover. Implementation commit:
> `57e1ac85fa5530fa9b78a626dfdc7993cbea4b63`. This document remains a record of
> the approved design; it does not authorize any new runtime behavior change.
>
> CAND-011 does not enable live trading, live submit, order placement,
> broker/provider execution, credential loading, network access, or approval
> queue mutation.

---

## 1. Title and candidate ID

**CAND-011: Kill-Switch `last_heartbeat()` Type-Safety Cleanup**

Eliminate the pre-existing mypy `union-attr` warning in
`src/atlas_agent/safety/kill_switch.py` by narrowing the nullable return value
of `HeartbeatManager.last_heartbeat()` to a single local variable before calling
`.isoformat()`. The change is strictly type-safety hygiene; no runtime behavior,
safety decision logic, audit payload shape, or fail-closed semantics change.

---

## 2. Baseline state

- Branch: `main`
- Design HEAD: `f079a8fe05218ce1a8f3d3b64fa270071733782c`
- Current public release: `v0.6.18`
- Package version: `0.6.18`
- Candidate line: `v0.6.19`
- Next planned release: `v0.6.19`
- Release status: no v0.6.19 tag, release, or PyPI publication exists
- PyPI: not published
- Live mode: fail-closed (`atlas run --mode live` exits 2)
- Annotated tag `v0.6.18` points at HEAD
- GitHub Release `v0.6.18` exists as a GitHub-only release

The warning was explicitly acknowledged as a known non-blocking item in the
`v0.6.18` release notes and trust status. It is being addressed now as a
separate protected-boundary-approved candidate rather than being folded into a
release cutover.

---

## 3. Problem statement

`src/atlas_agent/safety/kill_switch.py:46` builds an audit payload with:

```python
payload={
    "last_heartbeat": self.heartbeat_manager.last_heartbeat().isoformat()
    if self.heartbeat_manager.last_heartbeat()
    else None
}
```

This triggers a mypy `union-attr` error because the type checker sees each call
to `last_heartbeat()` as an independent `datetime | None` evaluation. Even
though the `if` branch is reached only when the condition is truthy, mypy does
not propagate narrowing across two separate method calls, so the `.isoformat()`
call in the true branch is treated as potentially operating on `None`.

The warning is pre-existing and harmless at runtime under normal conditions
because the condition and the true branch both evaluate to truthy values when
a valid heartbeat file exists. However, the repeated call is a minor race
condition: the file could be removed or corrupted between the condition
evaluation and the `.isoformat()` evaluation, which could raise
`AttributeError`. The cleanup makes the code simpler, type-safe, and slightly
more deterministic.

---

## 4. Protected-boundary classification

| Attribute | Value |
|---|---|
| File touched | `src/atlas_agent/safety/kill_switch.py` |
| Boundary type | Safety runtime boundary |
| Function / method affected | `AdvancedKillSwitch.evaluate` |
| Reason for touching the boundary | Remove a known static-type warning only |
| Intended behavior change | None |
| Safety risk | Low if the diff is a single local-variable narrowing |
| Release impact | v0.6.19 candidate only; not a release cutover |

`kill_switch.py` is part of the kill-switch / dead-man safety runtime boundary.
Any edit to this file must be reviewed as a protected-boundary change even when
it is purely cosmetic, because accidental edits in this area could weaken
fail-closed guarantees.

---

## 5. Current behavior

In `AdvancedKillSwitch.evaluate`, when the kill-switch mode is not
`locked_down` and the heartbeat is expired, the code writes a
`heartbeat_expired` audit event. The payload currently contains:

```python
payload={
    "last_heartbeat": self.heartbeat_manager.last_heartbeat().isoformat()
    if self.heartbeat_manager.last_heartbeat()
    else None
}
```

Semantics today:

1. `last_heartbeat()` is called in the condition.
2. If the condition is falsy (`None` or missing/corrupt heartbeat), the payload
   value is `None`.
3. If the condition is truthy, `last_heartbeat()` is called **a second time**,
   and `.isoformat()` is called on the result.

The audit payload key is `last_heartbeat` and the value is either an ISO-8601
string or `None`.

`HeartbeatManager.last_heartbeat()` reads the heartbeat file from disk each
time it is called and returns `datetime | None`:

```python
def last_heartbeat(self) -> datetime | None:
    if not self.heartbeat_path.exists():
        return None
    try:
        payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(payload["timestamp"])
    except Exception as exc:
        logger.warning(...)
        return None
```

Because the method reads external state, two successive calls may return
different values in rare circumstances (e.g., file deletion or corruption
between calls).

---

## 6. Proposed design

Replace the repeated call with a single local variable and a direct
`None`-check before calling `.isoformat()`:

```python
last_heartbeat = self.heartbeat_manager.last_heartbeat()
last_heartbeat_iso = (
    last_heartbeat.isoformat() if last_heartbeat is not None else None
)

if self.audit_writer:
    self.audit_writer.write_event(
        "heartbeat_expired",
        run_id=self.run_id,
        iteration=self.iteration,
        payload={"last_heartbeat": last_heartbeat_iso},
    )
```

### 6.1 Diff shape (expected)

The implementation change is expected to be a three-to-five-line edit inside
`AdvancedKillSwitch.evaluate`:

```diff
         if mode != "locked_down" and self.heartbeat_manager.is_expired():
+            last_heartbeat = self.heartbeat_manager.last_heartbeat()
+            last_heartbeat_iso = (
+                last_heartbeat.isoformat()
+                if last_heartbeat is not None
+                else None
+            )
             if self.audit_writer:
                 self.audit_writer.write_event(
                     "heartbeat_expired",
                     run_id=self.run_id,
                     iteration=self.iteration,
-                    payload={"last_heartbeat": self.heartbeat_manager.last_heartbeat().isoformat() if self.heartbeat_manager.last_heartbeat() else None}
+                    payload={"last_heartbeat": last_heartbeat_iso},
                 )
```

### 6.2 Constraints on the change

- The change is limited to the audit payload construction inside
  `AdvancedKillSwitch.evaluate`.
- No other method, class, or file is modified.
- No logic around `is_expired()`, mode escalation, kill-switch decisions, or
  return values changes.
- The `payload` dict retains the same key (`last_heartbeat`) and the same value
  shape (`str | None`).
- No new imports are required.
- No new dependencies are introduced.

---

## 7. Behavior-preservation argument

### 7.1 Same audit payload

- Key name: `last_heartbeat` (unchanged).
- Value shape: ISO-8601 string when heartbeat exists, `None` otherwise
  (unchanged).

### 7.2 Same kill-switch decisions

The change occurs **after** `self.heartbeat_manager.is_expired()` has already
returned `True` and immediately before the audit write. The kill-switch
decision (`allowed=False`, `status="blocked"`, `reason="Dead-man heartbeat
expired..."`, `diagnostics={"heartbeat_expired": True}`) is constructed
independently of the payload value and is unchanged.

### 7.3 Same fail-closed behavior

`last_heartbeat()` still returns `None` for a missing or corrupt heartbeat file,
and the local narrowing still produces `None` in that case. The audit event is
still written only when `is_expired()` is `True`. No path is created that would
allow execution when the heartbeat is expired.

### 7.4 Same exceptions

The current code can raise `AttributeError` only in the extremely unlikely event
that the second `last_heartbeat()` call returns `None` while the condition call
returned a `datetime`. The proposed code cannot raise `AttributeError` because
`.isoformat()` is guarded by an explicit `is not None` check. This is a strict
improvement in robustness; no existing exception type is newly introduced.

### 7.5 Call-count semantics

Current code calls `last_heartbeat()` once or twice depending on the branch.
Proposed code calls it exactly once. Because `last_heartbeat()` reads external
state, reducing the call count removes a narrow inter-call race and makes the
observed value consistent between the narrowing check and the `.isoformat()`
call. This is behavior-preserving in the observable audit payload and a
strict improvement in determinism.

### 7.6 No side effects added or removed

`last_heartbeat()` has no write side effects; it only reads the heartbeat file
and logs a warning on corruption. The proposed design does not add network,
broker, provider, credential, or disk-write behavior.

---

## 8. Scope

In scope for CAND-011:

- Modify the audit payload construction in
  `src/atlas_agent/safety/kill_switch.py:46` to narrow
  `self.heartbeat_manager.last_heartbeat()` to a local variable.
- Preserve the `last_heartbeat` payload key and `str | None` value shape.
- Add or extend tests only if existing coverage does not already exercise the
  `None` and datetime branches of this payload.
- Update this design document only.

Out of scope (non-goals) are listed in section 9.

---

## 9. Non-goals

CAND-011 explicitly does **not**:

- Enable live trading or live submit.
- Place, cancel, or flatten orders.
- Create pending orders or mutate approval queues.
- Call brokers, providers, or network endpoints.
- Load credentials, secrets, or API keys.
- Change kill-switch mode escalation, decision logic, or fail-closed semantics.
- Change `HeartbeatManager` behavior, file format, or public API.
- Change the audit event type, key names, or value shape.
- Add `fsync`, third-party dependencies, or new runtime logic.
- Bump version, tag, release, or publish to PyPI.
- Create a v0.6.19 release cutover or planning file beyond this design doc.
- Address unrelated ruff warnings in `tests/test_release_assurance.py`.
- Address the optional full-check timeout warning.

---

## 10. Safety invariants

The following invariants must remain true after implementation:

1. `atlas run --mode live` exits `2` / fail-closed.
2. `RiskManager`, approval gates, kill switch, deadman, heartbeat, and audit
   hash-chain are not weakened.
3. No live trading, live submit, broker/provider execution, credential loading,
   order placement, or approval queue mutation is introduced.
4. The `heartbeat_expired` audit payload retains key `last_heartbeat` with value
   shape `str | None`.
5. `AdvancedKillSwitch.evaluate` returns the same `KillSwitchDecision` for the
   same inputs.
6. `HeartbeatManager.last_heartbeat()` is not modified.
7. The atomic-write regression guard (`scripts/check_safety_atomic_write.py`)
   continues to pass.
8. Package version remains `0.6.18`; current public release remains `v0.6.18`;
   next planned release remains `v0.6.19`; PyPI remains unpublished.

---

## 11. Test plan

### 11.1 Existing coverage assessment

The existing safety test suite already exercises kill-switch and heartbeat
behavior:

- `tests/safety/test_kill_switch_core.py` — covers `KillSwitchController` mode
  transitions, persistence, flatten/cancel actions, and audit events. It does
  not directly exercise `AdvancedKillSwitch.evaluate`.
- `tests/safety/test_heartbeat.py` — covers `HeartbeatManager.record` and
  corrupt-file expiration.
- `tests/safety/test_deadman.py` — covers dead-man trigger semantics and
  external heartbeat handling.
- `tests/safety/test_safety_state.py` — covers `KillSwitchState` load/save.
- `tests/safety/test_atomic_write.py` — covers CAND-009 atomic-write helper
  behavior.

A search of the repository should be performed during implementation to locate
any existing tests that instantiate `AdvancedKillSwitch` and assert on the
`heartbeat_expired` audit payload. If such tests exist, they must be cited and
rerun. If none exist, the implementation should include the smallest possible
new regression test.

### 11.2 Required verification during implementation

| # | Verification | Expected result |
|---|---|---|
| 1 | `python3.11 -m pytest tests/safety/test_kill_switch_core.py -q` | Pass |
| 2 | `python3.11 -m pytest tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py tests/safety/test_atomic_write.py -q` | Pass |
| 3 | `python3.11 scripts/check_safety_atomic_write.py` | Pass |
| 4 | `python3.11 scripts/check_forbidden_claims.py` | Pass |
| 5 | `python3.11 scripts/check_bounded_autonomy_governance.py` | Pass |
| 6 | `atlas run --mode live` | Exit 2 |
| 7 | `mypy src/atlas_agent/safety/kill_switch.py` | No errors |
| 8 | `git diff --check` | No whitespace errors |

### 11.3 Optional new regression test

If no existing test covers the `heartbeat_expired` payload, add a minimal test
to `tests/safety/test_kill_switch_core.py` or a new `tests/safety/test_advanced_kill_switch.py`:

```python
def test_advanced_kill_switch_heartbeat_expired_payload_shape(tmp_path):
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch
    from atlas_agent.safety.heartbeat import HeartbeatManager

    state_path = tmp_path / "state.json"
    heartbeat_path = tmp_path / "heartbeat.json"
    audit_events = []

    class CapturingAuditWriter:
        def write_event(self, event_type, *, run_id, iteration, payload):
            audit_events.append((event_type, payload))

    # Missing heartbeat → last_heartbeat should be None.
    ks = AdvancedKillSwitch(
        state_path=state_path,
        heartbeat_path=heartbeat_path,
        audit_writer=CapturingAuditWriter(),
    )
    decision = ks.evaluate()
    assert decision.allowed is True  # no heartbeat means not expired

    # Stale heartbeat → last_heartbeat should be an ISO string.
    mgr = HeartbeatManager(heartbeat_path, timeout_seconds=0)
    mgr.record(source="test")
    decision = ks.evaluate()
    assert decision.allowed is False
    assert decision.status == "blocked"
    assert any(e[0] == "heartbeat_expired" for e in audit_events)
    heartbeat_payload = next(
        e[1] for e in audit_events if e[0] == "heartbeat_expired"
    )
    assert "last_heartbeat" in heartbeat_payload
    assert isinstance(heartbeat_payload["last_heartbeat"], str)
```

This test is optional if equivalent coverage already exists; it should be added
only if an audit of existing tests shows a gap.

---

## 12. Verification matrix

### Phase 0 — Baseline (already verified at design time)

```bash
git status --short
git rev-parse HEAD
git tag --points-at HEAD
git rev-parse v0.6.18^{}
gh release view v0.6.18
python3.11 -c 'import atlas_agent; print(atlas_agent.__version__)'
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
- HEAD is `f079a8fe05218ce1a8f3d3b64fa270071733782c`.
- `v0.6.18` tag points at HEAD.
- GitHub Release `v0.6.18` exists as GitHub-only.
- `atlas_agent.__version__` is `0.6.18`.
- `atlas run --mode live` exits 2.
- All other commands exit 0.

### Phase 1 — Design-doc-only verification

After writing only this design document, run:

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

### Phase 2 — Implementation acceptance (to be run after future implementation)

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 -m pytest tests/safety/test_kill_switch_core.py -q
python3.11 -m pytest tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py tests/safety/test_atomic_write.py -q
python3.11 scripts/check_safety_atomic_write.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_cli_command_compatibility.py
atlas validate
atlas run --mode live
mypy src/atlas_agent/safety/kill_switch.py
```

If a new regression test is added:

```bash
python3.11 -m pytest tests/safety/test_kill_switch_core.py -q
# or, if placed in a new file:
python3.11 -m pytest tests/safety/test_advanced_kill_switch.py -q
```

Expected:

- All commands exit 0 except `atlas run --mode live`, which must exit 2.
- `mypy src/atlas_agent/safety/kill_switch.py` reports no errors.

If feasible:

```bash
bash scripts/release_check.sh --quick
```

---

## 13. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Accidental logic change in `evaluate` | Medium | Keep the edit inside the existing `if` block; do not reorder, remove, or alter any `return` statement or decision field. |
| Audit payload shape change | Low | Preserve the dict literal key `last_heartbeat` and produce `str | None` exactly as today. |
| `last_heartbeat()` semantics change | Low | Do not modify `HeartbeatManager`; only consume its return value. |
| Mypy still reports an error | Low | Use explicit `is not None` narrowing; avoid `bool()`-style checks that mypy may not narrow. |
| Fail-closed behavior weakened | Very low | The change is after the `is_expired()` check and before the audit write; it cannot unblock execution. |
| Release metadata/version drift | Very low | Do not modify `pyproject.toml`, `src/atlas_agent/__init__.py`, or `docs/releases/release-metadata.json`. |

---

## 14. Rollback plan

If CAND-011 causes regressions after implementation:

1. Revert the single edit in `src/atlas_agent/safety/kill_switch.py`.
2. Revert any new test file or test addition made solely for CAND-011.
3. Re-run the Phase 2 verification matrix.
4. The system returns to the `v0.6.18` state, which remains fail-closed.

---

## 15. Acceptance criteria

- [ ] `docs/kill-switch-type-safety-cleanup-design.md` exists and contains all
      sections required by the CAND-011 brief.
- [ ] The design is reviewed and approved as a protected-boundary change before
      any source code is modified.
- [ ] Implementation modifies only the audit payload construction in
      `src/atlas_agent/safety/kill_switch.py` and, only if necessary, the
      smallest companion regression test.
- [ ] The `last_heartbeat` audit payload key and `str | None` value shape are
      preserved.
- [ ] No kill-switch decision logic, fail-closed behavior, or public API is
      changed.
- [ ] `mypy src/atlas_agent/safety/kill_switch.py` reports no errors after
      implementation.
- [ ] Existing safety-module tests still pass.
- [ ] `atlas run --mode live` still exits 2.
- [ ] `scripts/check_safety_atomic_write.py` still passes.
- [ ] No live trading, live submit, broker/provider execution, credential
      loading, or order placement is introduced.
- [ ] Package version remains `0.6.18`; current public release remains
      `v0.6.18`; next planned release remains `v0.6.19`; PyPI remains
      unpublished.

---

## 16. Implementation-plan readiness

This design is **ready for independent protected-boundary review**.

The specification is intentionally minimal: one local-variable narrowing in a
single safety-boundary file, with no runtime behavior change. After design
approval, implementation should be a single small commit that:

1. Edits `src/atlas_agent/safety/kill_switch.py` as shown in section 6.
2. Optionally adds the smallest regression test if coverage is missing.
3. Does not modify any other file.

A separate implementation approval is required before the code change is made.

---

## 17. Final recommendation

**Approve CAND-011 as the first v0.6.19 candidate.**

It is the smallest safe next step after `v0.6.18`: it removes a known type-check
warning in a protected safety file without changing runtime behavior,
decisions, audit shape, or any safety boundary. It keeps the candidate chain
focused on safety/governance hardening and avoids expanding scope into
unrelated lint cleanup or release planning.

After independent design review, the next action should be an implementation
prompt that explicitly re-affirms the protected-boundary approval and includes
the Phase 2 verification matrix.
