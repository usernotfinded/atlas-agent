# CAND-009: Safety State Atomic-Write Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four fixed `<target>.tmp` safety-state write patterns with a stdlib-only unique same-directory atomic-write helper, preserving file formats, public APIs, permissions, and fail-closed behavior.

**Architecture:** A new focused helper module `src/atlas_agent/safety/atomic_write.py` exposes `atomic_write_text` and `atomic_write_json`. Each existing safety module (`heartbeat.py`, `deadman.py`, `kill_switch.py`, `state.py`) replaces its inline fixed-temp logic with a single helper call. A one-line CLI contract hygiene fix documents the existing `doctor` command. All new tests live under `tests/safety/`.

**Tech Stack:** Python 3.11+, `pathlib`, `tempfile`, `json`, `os`, `threading` (stdlib only). No third-party dependencies, no broker/provider/execution imports, no network calls.

**Plan location note:** The repository does not have a dedicated implementation-plans directory. The user specified `docs/safety-state-atomic-write-hardening-implementation-plan.md`, so this plan is saved at that path.

---

## 1. Title and candidate ID

- **Candidate ID:** CAND-009
- **Title:** Safety State Atomic-Write Hardening
- **Target release line:** v0.6.17 planning-only
- **Current public release:** v0.6.16
- **Package version:** 0.6.16
- **Status:** implemented on `main`; no version bump, tag, release, or PyPI publication.

---

## 2. Planning baseline

| Item | Value |
|---|---|
| Repository | `usernotfinded/atlas-agent` |
| Branch | `main` |
| Planning HEAD | `4032d122bc2970e1138c54d0353801bc9de2166c` |
| Design document | `docs/safety-state-atomic-write-hardening-design.md` |
| Design review verdict | `PASS_WITH_WARNINGS` |
| Public release | `v0.6.16` |
| Package version | `0.6.16` |
| Next planned release | `v0.6.17` |
| PyPI published | `false` |
| Live mode | fail-closed (`atlas run --mode live` exits 2) |

---

## 3. Design-review findings incorporated

The independent design review produced four non-blocking warnings. This plan accounts for each:

1. **HEAD mismatch in design baseline.** Section 2 of the design doc lists baseline HEAD `28ed17aae895fb65ff917e549d2e50b4a18bf514`; the actual reviewed HEAD is `4032d122bc2970e1138c54d0353801bc9de2166c`. During implementation, update the design doc's section 2 to match the real baseline (or add a planning note). No functional impact.

2. **`state.py` serialization path change.** The design proposes moving from `KillSwitchStatus.model_dump_json(indent=2)` to `status.model_dump()` + `json.dumps(indent=2)`. This plan requires a byte-equivalence or field-equivalence regression test before migration is accepted. See section 11.

3. **Test placement.** New safety tests must live under `tests/safety/` where existing safety tests already reside, not at the repository root of `tests/`. This plan places `test_atomic_write.py`, `test_heartbeat.py`, and `test_safety_state.py` under `tests/safety/`.

4. **Exception handling discipline.** The helper must avoid unnecessary broad `except Exception` except for best-effort cleanup. Explicit expected exception classes (`OSError`, `PermissionError`) are preferred. This plan specifies exact exception clauses.

---

## 4. Scope

In scope for implementation:

- Create `src/atlas_agent/safety/atomic_write.py` with `atomic_write_text` and `atomic_write_json`.
- Migrate the four fixed `.tmp` write sites:
  - `src/atlas_agent/safety/heartbeat.py` (`HeartbeatManager.record`)
  - `src/atlas_agent/safety/deadman.py` (`write_deadman_heartbeat`)
  - `src/atlas_agent/safety/kill_switch.py` (`KillSwitchController._write_state`)
  - `src/atlas_agent/safety/state.py` (`KillSwitchState.save`)
- Preserve existing JSON formatting, key ordering, and best-effort `chmod(0o600)` behavior.
- Add tests under `tests/safety/` for the helper and safety-module regression.
- Add the existing `doctor` command to `tests/fixtures/cli_command_contract.json`.
- Re-run all verification commands and confirm live mode still exits 2.

---

## 5. Non-goals

CAND-009 implementation explicitly does **not**:

- Enable live trading or live submit.
- Place, cancel, or flatten orders.
- Create pending orders or mutate approval queues.
- Call brokers, providers, or network endpoints.
- Load credentials, secrets, or API keys.
- Change safety-state file formats or schemas.
- Change semantics of `HeartbeatManager.is_expired`, corrupt-state handling, kill-switch mode escalation, or dead-man timeout behavior.
- Add `fsync` by default.
- Introduce third-party dependencies.
- Bump version, tag, release, or publish to PyPI.
- Modify release metadata or changelog release dates.

---

## 6. Safety invariants

The implementation must preserve the following invariants. Any implementation that violates these is rejected.

- No live trading enablement.
- No live submit enablement.
- No order placement, cancellation, or flattening.
- No pending orders created.
- No approval queue mutation.
- No broker/provider calls.
- No credential loading.
- No network access.
- No weakening of `RiskManager`.
- No weakening of kill switch, deadman, or heartbeat.
- No audit hash-chain bypass.
- `atlas run --mode live` remains exit 2 / fail-closed.
- Package version remains `0.6.16`.
- Public release remains `v0.6.16`.
- No tag, release, or PyPI publication.

---

## 7. File-by-file implementation plan

| # | File | Action | Responsibility |
|---|---|---|---|
| 1 | `src/atlas_agent/safety/atomic_write.py` | Create | Shared stdlib-only atomic-write helper. |
| 2 | `src/atlas_agent/safety/heartbeat.py` | Modify | Replace fixed `.tmp` with helper call; keep `chmod=0o600`. |
| 3 | `src/atlas_agent/safety/deadman.py` | Modify | Replace fixed `.tmp` with helper call; no chmod. |
| 4 | `src/atlas_agent/safety/kill_switch.py` | Modify | Replace fixed `.tmp` with helper call inside existing lock. |
| 5 | `src/atlas_agent/safety/state.py` | Modify | Replace fixed `.tmp` with helper call; migrate serialization carefully. |
| 6 | `tests/safety/test_atomic_write.py` | Create | Helper unit and concurrency tests. |
| 7 | `tests/safety/test_heartbeat.py` | Create | Heartbeat regression tests. |
| 8 | `tests/safety/test_safety_state.py` | Create | Advanced kill-switch state regression tests. |
| 9 | `tests/safety/test_deadman.py` | Extend | Add atomic-write regression test. |
| 10 | `tests/safety/test_kill_switch_core.py` | Extend | Add no-fixed-tmp regression test. |
| 11 | `tests/fixtures/cli_command_contract.json` | Modify | Add `"doctor"` to `top_level_commands`. |
| 12 | `docs/safety-state-atomic-write-hardening-design.md` | Modify (minor) | Correct baseline HEAD or add planning note per warning #1. |

---

## 8. Proposed helper API and exact behavior

### 8.1 Module

`src/atlas_agent/safety/atomic_write.py`

### 8.2 Exports

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]
```

### 8.3 Function signatures

```python
def atomic_write_text(
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    ...


def atomic_write_json(
    target: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    ...
```

### 8.4 Exact behavior

1. Convert `target` to `Path`.
2. If `ensure_parent` is `True`, call `target.parent.mkdir(parents=True, exist_ok=True)`. If this fails, raise the original `OSError`; target must remain untouched.
3. Generate a unique temp file in `target.parent` using `tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=".tmp")`. Close the returned fd immediately.
4. Write `content` to the temp file with `temp_path.write_text(content, encoding=encoding)`.
5. Atomically move the temp file over the target with `temp_path.replace(target)` (or `os.replace` on the resolved strings).
6. If `chmod` is not `None`, best-effort apply the mode with `target.chmod(chmod)`. Catch only `OSError` and `PermissionError`; ignore silently.
7. Best-effort remove the temp file in both success and failure paths. Catch only `OSError`; ignore silently.
8. Return the resolved `target` path.

### 8.5 Failure behavior

| Scenario | Expected behavior |
|---|---|
| Parent directory cannot be created | Raise `OSError`; target unchanged. |
| Temp write fails | Raise exception; target unchanged; temp removed best-effort. |
| Replace fails | Raise exception; target unchanged; temp removed best-effort. |
| Chmod fails | Ignore; target already contains new content. |
| Cleanup fails | Ignore; safety relies on replace-before-cleanup. |

### 8.6 Constraints

- Stdlib only.
- No network imports or calls.
- No credential handling.
- No imports from `atlas_agent.brokers`, `atlas_agent.execution`, `atlas_agent.providers`, `atlas_agent.risk`, or `atlas_agent.config`.
- No runtime trading logic.
- No broad exception swallowing except for best-effort chmod and cleanup.

---

## 9. Migration details per safety module

### 9.1 `src/atlas_agent/safety/heartbeat.py`

**Current lines 16-29:**

```python
def record(self, source: str = "agent"):
    self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "source": source
    }
    tmp_path = self.heartbeat_path.with_suffix(self.heartbeat_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(self.heartbeat_path)

    try:
        self.heartbeat_path.chmod(0o600)
    except (OSError, PermissionError):
        pass
```

**Planned replacement:**

```python
from atlas_agent.safety.atomic_write import atomic_write_json


def record(self, source: str = "agent"):
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "source": source,
    }
    atomic_write_json(
        self.heartbeat_path,
        payload,
        chmod=0o600,
    )
```

**Changes:**
- Remove explicit `mkdir` (helper handles it).
- Remove fixed `.tmp` logic.
- Keep `chmod=0o600` via helper parameter.

### 9.2 `src/atlas_agent/safety/deadman.py`

**Current lines 101-118:**

```python
def write_deadman_heartbeat(
    path: str | Path,
    *,
    source: str,
    actor: str,
    now: datetime | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    effective_now = now or datetime.now(UTC)
    payload = {
        "timestamp": effective_now.isoformat(),
        "source": source,
        "actor": actor,
    }
    temp_path = target.with_suffix(target.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(target)
```

**Planned replacement:**

```python
from atlas_agent.safety.atomic_write import atomic_write_json


def write_deadman_heartbeat(
    path: str | Path,
    *,
    source: str,
    actor: str,
    now: datetime | None = None,
) -> None:
    target = Path(path)
    effective_now = now or datetime.now(UTC)
    payload = {
        "timestamp": effective_now.isoformat(),
        "source": source,
        "actor": actor,
    }
    atomic_write_json(
        target,
        payload,
        sort_keys=True,
    )
```

**Changes:**
- Public signature unchanged.
- Remove fixed `.tmp` logic.
- No chmod (deadman does not currently set permissions).

### 9.3 `src/atlas_agent/safety/kill_switch.py`

**Current lines 442-454:**

```python
def _write_state(self, state: KillSwitchState) -> None:
    payload = {
        "enabled": state.enabled,
        "mode": state.mode,
        "reason": state.reason,
        "actor": state.actor,
        "updated_at": state.updated_at,
        "activated_at": state.activated_at,
        "deactivated_at": state.deactivated_at,
    }
    tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(self.state_path)
```

**Planned replacement:**

```python
from atlas_agent.safety.atomic_write import atomic_write_json


def _write_state(self, state: KillSwitchState) -> None:
    payload = {
        "enabled": state.enabled,
        "mode": state.mode,
        "reason": state.reason,
        "actor": state.actor,
        "updated_at": state.updated_at,
        "activated_at": state.activated_at,
        "deactivated_at": state.deactivated_at,
    }
    atomic_write_json(
        self.state_path,
        payload,
        indent=2,
        sort_keys=True,
    )
```

**Changes:**
- Private method; external callers unchanged.
- Existing `threading.RLock` + advisory file lock in `_locked()` remains the primary guard.

### 9.4 `src/atlas_agent/safety/state.py`

**Current lines 38-55:**

```python
def save(self, mode, reason, actor="system"):
    self.state_path.parent.mkdir(parents=True, exist_ok=True)

    status = KillSwitchStatus(
        mode=mode,
        reason=reason,
        actor=actor,
        updated_at=datetime.now(UTC).isoformat()
    )

    tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
    tmp_path.write_text(status.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.replace(self.state_path)

    try:
        self.state_path.chmod(0o600)
    except (OSError, PermissionError):
        pass

    return status
```

**Planned replacement:**

```python
from atlas_agent.safety.atomic_write import atomic_write_json


def save(self, mode, reason, actor="system"):
    status = KillSwitchStatus(
        mode=mode,
        reason=reason,
        actor=actor,
        updated_at=datetime.now(UTC).isoformat(),
    )

    atomic_write_json(
        self.state_path,
        status.model_dump(),
        indent=2,
        chmod=0o600,
    )

    return status
```

**Changes:**
- Move from `KillSwitchStatus.model_dump_json(indent=2)` to `status.model_dump()` + helper's `json.dumps(indent=2)`.
- Keep `chmod=0o600`.
- This requires a serialization-equivalence test before acceptance.

---

## 10. Serialization compatibility plan (especially for `state.py`)

`state.py` currently uses Pydantic's `model_dump_json(indent=2)`. The helper uses `json.dumps(payload, indent=indent, sort_keys=sort_keys)`. To ensure byte-equivalence:

1. **Before migrating `state.py`**, add a regression test that:
   - Constructs a `KillSwitchStatus` with all fields populated.
   - Compares `status.model_dump_json(indent=2)` with `json.dumps(status.model_dump(), indent=2)`.
   - Asserts they are identical, or at minimum field-equivalent when parsed.

2. **If not byte-identical**, adjust the helper call options or helper internals until the output matches. Options include:
   - Passing `sort_keys=False` (default) if Pydantic does not sort keys.
   - Ensuring `ensure_ascii=True` (Python `json.dumps` default) matches Pydantic default.
   - Preserving newline-at-end behavior if Pydantic includes one.

3. **Required test** (to be added in `tests/safety/test_safety_state.py`):

```python
def test_state_serialization_matches_pydantic_model_dump_json() -> None:
    from atlas_agent.safety.models import KillSwitchStatus
    import json

    status = KillSwitchStatus(
        mode="soft_pause",
        reason="test",
        actor="user:1",
        updated_at="2026-06-30T08:47:12+00:00",
    )
    pydantic_output = status.model_dump_json(indent=2)
    helper_output = json.dumps(status.model_dump(), indent=2)
    assert json.loads(pydantic_output) == json.loads(helper_output)
    assert pydantic_output == helper_output
```

4. If the strict equality assertion fails, the implementer must document the difference and decide whether to adjust serialization options or accept field-equivalence only, with explicit reviewer sign-off.

---

## 11. Concurrency and atomicity test plan

All concurrency tests go in `tests/safety/test_atomic_write.py`.

### 11.1 Unit behavior tests

| Test | What it verifies |
|---|---|
| `test_atomic_write_text_creates_target` | Target file contains exact content. |
| `test_atomic_write_json_serializes_payload` | Target file contains valid JSON matching payload. |
| `test_temp_file_is_in_same_directory` | Temp file is created in target parent. |
| `test_temp_file_name_is_unique` | Repeated calls use different temp names. |
| `test_no_fixed_target_tmp_name` | No file named exactly `<target>.tmp` is created. |
| `test_old_file_preserved_on_write_failure` | Old target content survives injected write failure. |
| `test_old_file_preserved_on_replace_failure` | Old target content survives injected replace failure. |
| `test_temp_file_cleaned_up_on_success` | No leftover temp after successful write. |
| `test_temp_file_cleaned_up_on_failure` | Temp removed best-effort after failure. |
| `test_chmod_best_effort` | Requested mode applied when platform allows. |
| `test_invalid_parent_raises` | Helper raises `OSError` when parent cannot be created. |
| `test_invalid_payload_raises_without_touching_target` | Non-serializable payload raises before target mutation. |

### 11.2 Concurrency tests

| Test | What it verifies |
|---|---|
| `test_repeated_rapid_writes_do_not_collide` | 100 rapid sequential writes to the same target succeed. |
| `test_parallel_writes_do_not_raise_file_not_found` | Multiple threads write concurrently; no `FileNotFoundError`; final file valid. |
| `test_no_partial_file_observed` | Reader thread polls during writers; every observation is old valid content or new valid content. |
| `test_concurrent_writers_old_file_preserved_on_failure` | If one writer fails, target remains a valid previously-written file. |

### 11.3 Safety-module regression tests

| Module | Test file | New test |
|---|---|---|
| Heartbeat | `tests/safety/test_heartbeat.py` | `test_heartbeat_record_repeated`, `test_heartbeat_corrupt_file_still_expired` |
| Deadman | `tests/safety/test_deadman.py` | `test_deadman_heartbeat_write_is_atomic` |
| Kill switch | `tests/safety/test_kill_switch_core.py` | `test_kill_switch_no_fixed_tmp_after_write` |
| Safety state | `tests/safety/test_safety_state.py` | `test_state_save_load_roundtrip`, `test_state_save_repeated`, `test_state_corrupt_load_fails_closed`, `test_state_serialization_matches_pydantic_model_dump_json` |

### 11.4 CLI hygiene tests

| Test file | New test |
|---|---|
| `tests/test_cli_command_compatibility.py` | `test_doctor_is_in_contract` |

---

## 12. CLI doctor contract hygiene plan

The top-level `doctor` command is intentional and read-only. It is already registered in `src/atlas_agent/cli.py` but missing from the contract fixture.

### 12.1 Change

Add `"doctor"` to `top_level_commands` in `tests/fixtures/cli_command_contract.json`.

Place it alphabetically between `"discipline"` and `"events"`.

### 12.2 Boundaries

- Do not change CLI behavior.
- Do not remove `doctor`.
- Do not add new commands.
- Do not expand beyond the one-line contract update.

### 12.3 Verification

After the change:

```bash
python3.11 scripts/check_cli_command_compatibility.py
```

Must exit 0 and print no `doctor` warning.

---

## 13. Static / checker plan

After implementation, run:

| Check | Command | Expected |
|---|---|---|
| Formatting / lint | `ruff check src/atlas_agent/safety/atomic_write.py src/atlas_agent/safety/heartbeat.py src/atlas_agent/safety/deadman.py src/atlas_agent/safety/kill_switch.py src/atlas_agent/safety/state.py` | Clean or pre-existing issues only. |
| Type check | `mypy src/atlas_agent/safety/atomic_write.py` | Pass. |
| Forbidden claims | `python3.11 scripts/check_forbidden_claims.py` | Pass. |
| Bounded autonomy | `python3.11 scripts/check_bounded_autonomy_governance.py` | Pass. |
| CLI contract | `python3.11 scripts/check_cli_command_compatibility.py` | Pass with no `doctor` warning. |
| Old-pattern grep | `grep -R "with_suffix(.*\"\\.tmp\")" src/atlas_agent/safety/` | No matches in migrated modules. |

---

## 14. Verification matrix

### Phase 0 — Baseline verification (before any implementation)

```bash
git status --short
git rev-parse HEAD
git tag --points-at HEAD
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
atlas validate
atlas run --mode live
```

Expected:
- `git status --short` empty.
- `atlas run --mode live` exits 2.
- All other commands exit 0.
- CLI compatibility check shows `doctor` warning only.

### Phase 5 — Post-implementation verification

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 -m pytest tests/safety/test_atomic_write.py -q
python3.11 -m pytest tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py -q
python3.11 -m pytest tests/safety/test_kill_switch*.py -q
python3.11 -m pytest tests/test_cli_command_compatibility.py -q
python3.11 scripts/check_cli_command_compatibility.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
atlas validate
atlas run --mode live
bash scripts/release_check.sh --quick
```

If feasible:

```bash
bash scripts/release_check.sh
python3.11 -m pytest -q --durations=25
```

Expected:
- All commands exit 0 except `atlas run --mode live`, which must exit 2.
- `scripts/check_cli_command_compatibility.py` reports zero warnings.
- No `live` readiness claim appears in output.

---

## 15. Rollback plan

If CAND-009 causes regressions:

1. Revert the four source-file edits to restore inline fixed `.tmp` logic.
2. Delete `src/atlas_agent/safety/atomic_write.py`.
3. Delete `tests/safety/test_atomic_write.py`, `tests/safety/test_heartbeat.py`, `tests/safety/test_safety_state.py`, and revert additions to `tests/safety/test_deadman.py` and `tests/safety/test_kill_switch_core.py`.
4. Revert the one-line `"doctor"` addition to `tests/fixtures/cli_command_contract.json` if it causes issues.
5. Re-run the verification matrix.
6. The system returns to v0.6.16 safety-state write behavior, which is already fail-closed for readers.

---

## 16. Commit plan

For the planning task only, commit the implementation plan document:

```bash
git add docs/safety-state-atomic-write-hardening-implementation-plan.md
git commit -m "docs(cand-009): add safety atomic-write implementation plan"
git push origin main
```

For the future implementation phase, suggest these small commits:

```text
feat(cand-009): add safety atomic write helper
fix(cand-009): migrate heartbeat writes to unique temp files
fix(cand-009): migrate deadman writes to unique temp files
fix(cand-009): migrate kill_switch writes to unique temp files
fix(cand-009): migrate safety state writes to unique temp files
test(cand-009): cover safety atomic write concurrency and regressions
test(cli): include doctor in command contract
docs(cand-009): correct design baseline HEAD note
```

---

## 17. Acceptance criteria

- [ ] `docs/safety-state-atomic-write-hardening-implementation-plan.md` exists and contains all required sections.
- [ ] `src/atlas_agent/safety/atomic_write.py` is implemented with the API in section 8 and uses stdlib only.
- [ ] All four fixed `.tmp` patterns are replaced with helper calls.
- [ ] No public API signature changes.
- [ ] File formats, JSON indentation/sorting, and `chmod(0o600)` behavior are preserved.
- [ ] New tests cover helper behavior, concurrency, and safety-module regression.
- [ ] Existing safety-module tests still pass.
- [ ] `atlas run --mode live` still exits 2.
- [ ] `scripts/check_cli_command_compatibility.py` passes with no `doctor` warning after the contract update.
- [ ] All verification matrix commands pass (with the expected live-mode failure).
- [ ] No live trading, live submit, broker/provider execution, credential loading, or order placement is introduced.
- [ ] Only the design doc, the new helper, the four source files, the new tests, and the one-line CLI contract JSON are modified. No release metadata, version, tag, or changelog release-date changes are made.

---

## 18. Implementation prompt readiness

This plan is ready for an implementer agent. Each task below contains:

- Exact file paths.
- Complete code or diff snippets.
- Exact test commands and expected outcomes.
- Exact commit commands and messages.

The implementer must not deviate from the safety invariants in section 6.

---

## 19. Task-by-task execution plan

### Task 1: Create the atomic-write helper

**Files:**
- Create: `src/atlas_agent/safety/atomic_write.py`
- Test: `tests/safety/test_atomic_write.py` (created in Task 7)

- [ ] **Step 1: Write the helper module**

Create `src/atlas_agent/safety/atomic_write.py`:

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]


def _unique_temp_path(target: Path) -> Path:
    fd, temp_str = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    return Path(temp_str)


def _try_remove(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


def atomic_write_text(
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    target = Path(target)
    if ensure_parent:
        target.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        temp_path = _unique_temp_path(target)
        temp_path.write_text(content, encoding=encoding)
        temp_path.replace(target)
        if chmod is not None:
            try:
                target.chmod(chmod)
            except (OSError, PermissionError):
                pass
    finally:
        # Best-effort cleanup in both success and failure paths. A leftover temp
        # file does not affect target safety because replace happens only after a
        # successful write.
        _try_remove(temp_path)

    return target


def atomic_write_json(
    target: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    content = json.dumps(payload, indent=indent, sort_keys=sort_keys)
    return atomic_write_text(
        target,
        content,
        encoding=encoding,
        chmod=chmod,
        ensure_parent=ensure_parent,
    )
```

- [ ] **Step 2: Verify it compiles**

Run:

```bash
python3.11 -m compileall src/atlas_agent/safety/atomic_write.py
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/safety/atomic_write.py
git commit -m "feat(cand-009): add safety atomic write helper"
```

---

### Task 2: Migrate heartbeat writes

**Files:**
- Modify: `src/atlas_agent/safety/heartbeat.py`
- Test: `tests/safety/test_heartbeat.py` (created in Task 7)

- [ ] **Step 1: Apply the migration**

Replace the `record` method with:

```python
from atlas_agent.safety.atomic_write import atomic_write_json


class HeartbeatManager:
    def __init__(self, heartbeat_path: str | Path, timeout_seconds: int = 300):
        self.heartbeat_path = Path(heartbeat_path)
        self.timeout_seconds = timeout_seconds

    def record(self, source: str = "agent"):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": source,
        }
        atomic_write_json(
            self.heartbeat_path,
            payload,
            chmod=0o600,
        )
```

Remove the now-unused `json` import if no longer needed elsewhere in the file.

- [ ] **Step 2: Run heartbeat tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_heartbeat.py -q
```

Expected: tests pass (new tests will be added in Task 7).

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/safety/heartbeat.py
git commit -m "fix(cand-009): migrate heartbeat writes to unique temp files"
```

---

### Task 3: Migrate deadman writes

**Files:**
- Modify: `src/atlas_agent/safety/deadman.py`
- Test: `tests/safety/test_deadman.py`

- [ ] **Step 1: Apply the migration**

Replace `write_deadman_heartbeat` with:

```python
from atlas_agent.safety.atomic_write import atomic_write_json


def write_deadman_heartbeat(
    path: str | Path,
    *,
    source: str,
    actor: str,
    now: datetime | None = None,
) -> None:
    target = Path(path)
    effective_now = now or datetime.now(UTC)
    payload = {
        "timestamp": effective_now.isoformat(),
        "source": source,
        "actor": actor,
    }
    atomic_write_json(
        target,
        payload,
        sort_keys=True,
    )
```

- [ ] **Step 2: Run deadman tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_deadman.py -q
```

Expected: tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/safety/deadman.py
git commit -m "fix(cand-009): migrate deadman writes to unique temp files"
```

---

### Task 4: Migrate kill_switch writes

**Files:**
- Modify: `src/atlas_agent/safety/kill_switch.py`
- Test: `tests/safety/test_kill_switch_core.py`

- [ ] **Step 1: Apply the migration**

Replace `_write_state` with:

```python
from atlas_agent.safety.atomic_write import atomic_write_json


class KillSwitchController:
    # ... existing methods unchanged ...

    def _write_state(self, state: KillSwitchState) -> None:
        payload = {
            "enabled": state.enabled,
            "mode": state.mode,
            "reason": state.reason,
            "actor": state.actor,
            "updated_at": state.updated_at,
            "activated_at": state.activated_at,
            "deactivated_at": state.deactivated_at,
        }
        atomic_write_json(
            self.state_path,
            payload,
            indent=2,
            sort_keys=True,
        )
```

- [ ] **Step 2: Run kill switch tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_kill_switch_core.py tests/safety/test_kill_switch_v2.py tests/safety/test_kill_switch_action_plan.py -q
```

Expected: tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/safety/kill_switch.py
git commit -m "fix(cand-009): migrate kill_switch writes to unique temp files"
```

---

### Task 5: Migrate safety state writes

**Files:**
- Modify: `src/atlas_agent/safety/state.py`
- Test: `tests/safety/test_safety_state.py`

- [ ] **Step 1: Apply the migration**

Replace `save` with:

```python
from atlas_agent.safety.atomic_write import atomic_write_json


class KillSwitchState:
    # ... existing methods unchanged ...

    def save(self, mode, reason, actor="system"):
        status = KillSwitchStatus(
            mode=mode,
            reason=reason,
            actor=actor,
            updated_at=datetime.now(UTC).isoformat(),
        )

        atomic_write_json(
            self.state_path,
            status.model_dump(),
            indent=2,
            chmod=0o600,
        )

        return status
```

- [ ] **Step 2: Run serialization-equivalence test first**

Run:

```bash
python3.11 -m pytest tests/safety/test_safety_state.py::test_state_serialization_matches_pydantic_model_dump_json -v
```

Expected: PASS.

- [ ] **Step 3: Run all safety state tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_safety_state.py -q
```

Expected: tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/safety/state.py
git commit -m "fix(cand-009): migrate safety state writes to unique temp files"
```

---

### Task 6: CLI doctor contract hygiene

**Files:**
- Modify: `tests/fixtures/cli_command_contract.json`
- Test: `tests/test_cli_command_compatibility.py`

- [ ] **Step 1: Add doctor to the contract**

In `tests/fixtures/cli_command_contract.json`, insert `"doctor"` alphabetically between `"discipline"` and `"events"` in `top_level_commands`.

- [ ] **Step 2: Add a test**

Append to `tests/test_cli_command_compatibility.py`:

```python
def test_doctor_is_in_contract(contract: dict) -> None:
    assert "doctor" in contract["top_level_commands"]
```

- [ ] **Step 3: Run CLI compatibility check**

Run:

```bash
python3.11 scripts/check_cli_command_compatibility.py
python3.11 -m pytest tests/test_cli_command_compatibility.py -q
```

Expected: both exit 0, no `doctor` warning.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/cli_command_contract.json tests/test_cli_command_compatibility.py
git commit -m "test(cli): include doctor in command contract"
```

---

### Task 7: Add helper and safety regression tests

**Files:**
- Create: `tests/safety/test_atomic_write.py`
- Create: `tests/safety/test_heartbeat.py`
- Create: `tests/safety/test_safety_state.py`
- Modify: `tests/safety/test_deadman.py`
- Modify: `tests/safety/test_kill_switch_core.py`

- [ ] **Step 1: Write helper tests**

Create `tests/safety/test_atomic_write.py` with at least the tests listed in section 11. Representative snippets:

```python
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from atlas_agent.safety.atomic_write import atomic_write_json, atomic_write_text


def test_atomic_write_text_creates_target(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_json_serializes_payload(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    payload = {"a": 1, "b": [2, 3]}
    atomic_write_json(target, payload, sort_keys=True)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_no_fixed_target_tmp_name(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"x": 1})
    assert not (tmp_path / "target.json.tmp").exists()


def test_old_file_preserved_on_write_failure(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("old", encoding="utf-8")

    class Boom:
        def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        atomic_write_text(target, Boom())  # type: ignore[arg-type]

    assert target.read_text(encoding="utf-8") == "old"


def test_parallel_writes_do_not_raise_file_not_found(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    errors: list[BaseException] = []

    def writer(value: int) -> None:
        try:
            atomic_write_json(target, {"value": value})
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert json.loads(target.read_text(encoding="utf-8"))["value"] in range(20)
```

- [ ] **Step 2: Write heartbeat regression tests**

Create `tests/safety/test_heartbeat.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from atlas_agent.safety.heartbeat import HeartbeatManager


def test_heartbeat_record_repeated(tmp_path: Path) -> None:
    mgr = HeartbeatManager(tmp_path / "heartbeat.json")
    mgr.record(source="test")
    mgr.record(source="test")
    payload = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert payload["source"] == "test"
    assert "timestamp" in payload


def test_heartbeat_corrupt_file_still_expired(tmp_path: Path) -> None:
    target = tmp_path / "heartbeat.json"
    target.write_text("not-json", encoding="utf-8")
    mgr = HeartbeatManager(target, timeout_seconds=1)
    assert mgr.is_expired() is True
```

- [ ] **Step 3: Write safety state regression tests**

Create `tests/safety/test_safety_state.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.safety.models import KillSwitchStatus
from atlas_agent.safety.state import KillSwitchState


def test_state_save_load_roundtrip(tmp_path: Path) -> None:
    mgr = KillSwitchState(tmp_path / "state.json")
    mgr.save("soft_pause", "test reason", actor="user:1")
    status = mgr.load()
    assert status.mode == "soft_pause"
    assert status.reason == "test reason"
    assert status.actor == "user:1"


def test_state_save_repeated(tmp_path: Path) -> None:
    mgr = KillSwitchState(tmp_path / "state.json")
    mgr.save("normal", "first")
    mgr.save("locked_down", "second")
    payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "locked_down"
    assert payload["reason"] == "second"


def test_state_corrupt_load_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("not-json", encoding="utf-8")
    mgr = KillSwitchState(target)
    status = mgr.load()
    assert status.mode == "locked_down"


def test_state_serialization_matches_pydantic_model_dump_json() -> None:
    status = KillSwitchStatus(
        mode="soft_pause",
        reason="test",
        actor="user:1",
        updated_at="2026-06-30T08:47:12+00:00",
    )
    pydantic_output = status.model_dump_json(indent=2)
    helper_output = json.dumps(status.model_dump(), indent=2)
    assert json.loads(pydantic_output) == json.loads(helper_output)
    assert pydantic_output == helper_output
```

- [ ] **Step 4: Extend deadman tests**

Append to `tests/safety/test_deadman.py`:

```python
from pathlib import Path

from atlas_agent.safety.deadman import write_deadman_heartbeat


def test_deadman_heartbeat_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "deadman_heartbeat.json"
    write_deadman_heartbeat(target, source="test", actor="user:1")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == "test"
    assert payload["actor"] == "user:1"
    assert not (tmp_path / "deadman_heartbeat.json.tmp").exists()
```

- [ ] **Step 5: Extend kill switch tests**

Append to `tests/safety/test_kill_switch_core.py`:

```python
from pathlib import Path


def test_kill_switch_no_fixed_tmp_after_write(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.enable(mode="soft", reason="test", actor="user:1")
    assert (tmp_path / "kill-switch-state.json").exists()
    assert not (tmp_path / "kill-switch-state.json.tmp").exists()
```

- [ ] **Step 6: Run all new tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_atomic_write.py tests/safety/test_heartbeat.py tests/safety/test_safety_state.py -q
python3.11 -m pytest tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py -q
```

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/safety/test_atomic_write.py tests/safety/test_heartbeat.py tests/safety/test_safety_state.py tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py
git commit -m "test(cand-009): cover safety atomic write concurrency and regressions"
```

---

### Task 8: Minor design doc correction

**Files:**
- Modify: `docs/safety-state-atomic-write-hardening-design.md`

- [ ] **Step 1: Correct the baseline HEAD**

In section 2 of the design doc, replace:

```text
- HEAD: `28ed17aae895fb65ff917e549d2e50b4a18bf514`
```

with:

```text
- HEAD: `4032d122bc2970e1138c54d0353801bc9de2166c`
```

- [ ] **Step 2: Commit**

```bash
git add docs/safety-state-atomic-write-hardening-design.md
git commit -m "docs(cand-009): correct design baseline HEAD note"
```

---

### Task 9: Final verification

**Files:**
- All modified files.

- [ ] **Step 1: Run the full verification matrix**

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 -m pytest tests/safety/test_atomic_write.py -q
python3.11 -m pytest tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py -q
python3.11 -m pytest tests/safety/test_kill_switch*.py -q
python3.11 -m pytest tests/test_cli_command_compatibility.py -q
python3.11 scripts/check_cli_command_compatibility.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
atlas validate
atlas run --mode live
bash scripts/release_check.sh --quick
```

Expected:
- All commands exit 0 except `atlas run --mode live`, which exits 2.
- CLI compatibility check reports zero warnings.

- [ ] **Step 2: Confirm no implementation changes beyond scope**

Run:

```bash
git status --short
```

Expected: only the planned files are modified/added.

- [ ] **Step 3: No commit required for verification**

This is a checkpoint. If any command fails, fix the underlying task and rerun.

---

## 20. Self-review

Before considering this plan complete, verify:

1. **Spec coverage:** Every section of the CAND-009 design document has a corresponding task or section in this plan.
2. **Placeholder scan:** No `TBD`, `TODO`, `implement later`, or vague "add appropriate error handling" statements remain.
3. **Type consistency:** `atomic_write_text` and `atomic_write_json` signatures match their usage in all four migration tasks.
4. **Test placement:** New safety tests are under `tests/safety/`.
5. **Safety invariants:** No task enables live trading, live submit, broker/provider execution, credential loading, or order placement.
6. **Verification matrix:** All required commands from the user prompt are present.

---

## 21. Execution handoff

**Plan complete and saved to `docs/safety-state-atomic-write-hardening-implementation-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
2. **Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**Important:** The current task is planning only. Do not begin implementation until explicitly authorized.
