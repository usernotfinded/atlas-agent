# CAND-009: Safety State Atomic-Write Hardening

## Design Specification

**Candidate ID:** CAND-009  
**Candidate line:** v0.6.17  
**Current public release:** v0.6.16  
**Status:** design-only (no implementation code in this change)  
**Date:** 2026-06-30  
**Design document path:** `docs/safety-state-atomic-write-hardening-design.md`

> **Design-only disclaimer.** This document is a specification. It does not modify
> source code, tests, release metadata, or CLI behavior. No version bump, tag,
> release, PyPI publication, or live-trading enablement is part of this candidate.

---

## 1. Title and candidate ID

**CAND-009: Safety State Atomic-Write Hardening**

Replace fixed `<target>.tmp` patterns in safety-state persistence with unique
same-directory atomic temporary files, preserving atomic `replace` semantics and
fail-closed behavior.

---

## 2. Current baseline

- Branch: `main`
- HEAD: `28ed17aae895fb65ff917e549d2e50b4a18bf514`
- Current public release: `v0.6.16`
- Package version: `0.6.16`
- Next planned release: `v0.6.17`
- PyPI: not published
- Live mode: fail-closed (`atlas run --mode live` exits 2)

All safety-state persistence modules currently use a fixed temporary-file
pattern: `target.with_suffix(target.suffix + ".tmp")`. The temp file is written
and then atomically moved into place with `Path.replace(target)`. This is already
atomic on POSIX and Windows for same-filesystem replacements, but the fixed name
creates collision and partial-state risks when multiple writers, rapid retries,
or stale temp files are present.

---

## 3. Problem statement

Fixed `<target>.tmp` names have the following weaknesses:

1. **Collision under concurrency.** Two threads or processes writing the same
   target concurrently use the same temp path. On some platforms a second writer
   can overwrite the temp file while the first writer is still flushing, or the
   first `replace` can race with the second `write_text`.
2. **Stale temp file reuse.** A crash after `write_text` but before `replace`
   leaves a `<target>.tmp` file that the next writer reuses, making it harder to
   diagnose whether the current operation failed or a previous operation failed.
3. **Observability.** Fixed temp names make it impossible to distinguish
   concurrent writers in logs or filesystem listings.
4. **Reader safety is preserved today, but fragile.** Readers either see the old
   file or the new file because `replace` is atomic. However, a writer crash that
   leaves a temp file can confuse operators and complicate recovery.

CAND-009 hardens the pattern without changing file formats, public APIs, or
fail-closed semantics.

---

## 4. Files and current fixed-temp patterns found

| File | Function / method | Current fixed-temp pattern | Post-write action |
|---|---|---|---|
| `src/atlas_agent/safety/heartbeat.py` | `HeartbeatManager.record` | `self.heartbeat_path.with_suffix(self.heartbeat_path.suffix + ".tmp")` | `tmp.replace(self.heartbeat_path)`, then best-effort `chmod(0o600)` |
| `src/atlas_agent/safety/deadman.py` | `write_deadman_heartbeat` | `target.with_suffix(target.suffix + ".tmp")` | `temp.replace(target)` |
| `src/atlas_agent/safety/kill_switch.py` | `KillSwitchController._write_state` | `self.state_path.with_suffix(self.state_path.suffix + ".tmp")` | `tmp_path.replace(self.state_path)` |
| `src/atlas_agent/safety/state.py` | `KillSwitchState.save` | `self.state_path.with_suffix(self.state_path.suffix + ".tmp")` | `tmp_path.replace(self.state_path)`, then best-effort `chmod(0o600)` |

All four sites:
- create the target parent directory with `mkdir(parents=True, exist_ok=True)`
- write UTF-8 JSON text
- rely on `Path.replace` for atomic overwrite
- do not explicitly `fsync` before replace (consistent with existing style)

---

## 5. Safety impact of fixed temp paths

| Risk | Severity | Current mitigation | Why it is not enough |
|---|---|---|---|
| Concurrent writers collide on temp file | Medium | Thread locks in `KillSwitchController` | Does not protect cross-process writers or rapid retries outside the lock scope |
| Leftover temp file masks a prior crash | Low | Best-effort replace | Operator cannot tell whether the leftover file is from the current or a previous operation |
| Temp file overwritten while another writer is mid-flush | Low-Medium | `write_text` writes whole content at once | On some platforms concurrent openers can interleave or truncate |
| Reader sees partial file | Very Low | `replace` is atomic | A crash or bug that writes directly to the target path would expose partial data; this design does not change that, but it does remove one path that encourages direct-target writes during debugging |

The current behavior is **already fail-closed** for readers. CAND-009 makes the
writer side more robust and more auditable.

---

## 6. Non-goals

CAND-009 explicitly does **not**:

- Enable live trading or live submit.
- Place, cancel, or flatten orders.
- Create pending orders or mutate approval queues.
- Call brokers, providers, or network endpoints.
- Load credentials, secrets, or API keys.
- Change safety-state file formats or schemas.
- Change the semantics of `HeartbeatManager.is_expired`, corrupt-state handling,
  kill-switch mode escalation, or dead-man timeout behavior.
- Add `fsync` by default (remains opt-in to match current style).
- Introduce third-party dependencies (stdlib only).
- Bump version, tag, release, or publish to PyPI.

---

## 7. Proposed design

1. Introduce a small stdlib-only helper module:
   `src/atlas_agent/safety/atomic_write.py`.
2. Replace the four fixed `<target>.tmp` writes with calls to the helper.
3. The helper generates a **unique** temp file in the **same directory** as the
   target, writes the payload, performs an atomic `replace`, and attempts to
   clean up the temp file on failure.
4. Public function and class signatures remain unchanged.
5. Existing `chmod(0o600)` best-effort behavior is moved into the helper as an
   optional parameter so callers retain their current permission behavior.
6. The helper rejects a target whose parent is not a directory (or cannot be
   created) by raising `OSError`, matching the existing behavior of
   `mkdir(parents=True, exist_ok=True)` followed by `write_text`.
7. JSON serialization uses `json.dumps` with the same options each caller
   currently passes (`sort_keys`, `indent`).
8. A companion CLI hygiene fix adds the intentional top-level `doctor` command to
   `tests/fixtures/cli_command_contract.json`. No CLI code changes.

---

## 8. Atomic-write helper API proposal

### 8.1 Module

`src/atlas_agent/safety/atomic_write.py`

### 8.2 Exports

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]
```

### 8.3 Functions

```python
def atomic_write_text(
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    """Write `content` to `target` atomically using a unique same-directory temp file.

    The function never leaves a partially-written file at `target`; readers
    either see the previous file or the fully-written new file. The temp file
    is created with a unique name and is removed best-effort on failure.
    """


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
    """Serialize `payload` to JSON and atomically write it to `target`.

    Uses `atomic_write_text` internally. `payload` must be JSON-serializable.
    """
```

### 8.4 Unique temp-path generation

Use `tempfile.mkstemp` in the target's parent directory:

```python
import os
import tempfile
from pathlib import Path


def _unique_temp_path(target: Path) -> Path:
    fd, temp_str = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    return Path(temp_str)
```

- `mkstemp` guarantees a unique name and creates the file with `O_CREAT | O_EXCL`
  behavior where supported.
- The temp file lives in the same directory as the target, so `Path.replace`
  is atomic and does not cross filesystems.
- The returned fd is closed immediately; `atomic_write_text` opens the path with
  `open(..., "w", encoding=encoding)`.

### 8.5 Write / replace / cleanup algorithm

```python
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

    temp_path = _unique_temp_path(target)
    try:
        temp_path.write_text(content, encoding=encoding)
        temp_path.replace(target)
        if chmod is not None:
            try:
                target.chmod(chmod)
            except (OSError, PermissionError):
                pass
    except Exception:
        _try_remove(temp_path)
        raise
    finally:
        _try_remove(temp_path)

    return target
```

Notes:
- `temp_path.replace(target)` is atomic on CPython / POSIX / Windows for
  same-filesystem paths.
- `chmod` is best-effort, preserving the existing behavior in `heartbeat.py`
  and `state.py`.
- Cleanup is best-effort in both the success and failure paths; a leftover temp
  file does not affect safety because the target is only replaced after a
  successful write.
- No `fsync` is performed by default to remain consistent with the current
  `Path.write_text` style. An optional `fsync: bool = False` parameter may be
  added for future callers but must not be enabled by CAND-009.

### 8.6 Constraints on the helper

- Stdlib only (`json`, `os`, `pathlib`, `tempfile`, `typing`).
- No network imports or calls.
- No credential handling.
- No imports from `atlas_agent.brokers`, `atlas_agent.execution`,
  `atlas_agent.providers`, `atlas_agent.risk`, or `atlas_agent.config`.
- No runtime trading logic.
- No broad exception swallowing except for best-effort chmod and cleanup.

---

## 9. Migration plan per file

### 9.1 `src/atlas_agent/safety/heartbeat.py`

**Current (lines 16-29):**

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

**Proposed change:**

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

- Remove explicit `mkdir` (helper handles it via `ensure_parent=True` default).
- Remove fixed `.tmp` logic.
- Keep `chmod(0o600)` behavior via helper parameter.

### 9.2 `src/atlas_agent/safety/deadman.py`

**Current (lines 101-118):**

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

**Proposed change:**

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

- Public signature unchanged.
- Remove fixed `.tmp` logic.
- No chmod needed (deadman heartbeat does not currently set permissions).

### 9.3 `src/atlas_agent/safety/kill_switch.py`

**Current (`_write_state`, lines 442-454):**

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

**Proposed change:**

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

- This method is private; external callers use `enable` / `disable` / `status`.
- The existing `threading.RLock` + file lock in `_locked()` remains the primary
  cross-thread/cross-process guard; CAND-009 removes the temp-name collision
  risk under that guard.

### 9.4 `src/atlas_agent/safety/state.py`

**Current (`save`, lines 38-55):**

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

**Proposed change:**

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

- `KillSwitchStatus.model_dump()` returns a JSON-serializable dict.
- `indent=2` preserves formatting.
- `chmod=0o600` preserves existing permission behavior.

### 9.5 New helper module

`src/atlas_agent/safety/atomic_write.py` as specified in section 8.

---

## 10. Failure-mode matrix

| Failure mode | Expected behavior | Fail-closed preserved? | Old file preserved? | Temp cleanup attempted? | Test coverage required |
|---|---|---|---|---|---|
| **Temp file collision** | Unique name from `mkstemp` prevents collision; two writers get distinct temp paths | Yes | Yes | Best-effort on each writer's own temp | Yes: concurrent writers test |
| **Target parent missing** | Helper calls `mkdir(parents=True, exist_ok=True)`; if that fails, raises `OSError` and target is untouched | Yes | Yes | Yes, if temp was created before mkdir failure | Yes: missing parent test |
| **Permission denied** | Write or replace raises `PermissionError`; target remains old file | Yes | Yes | Yes | Yes: permission denied test |
| **Disk full** | `write_text` or `replace` raises `OSError`; target remains old file | Yes | Yes | Yes | Yes: simulated disk-full test (inject write failure) |
| **Partial write** | Partial content is written only to the temp file; `replace` happens only after `write_text` returns successfully | Yes | Yes | Yes | Yes: inject exception before replace |
| **Replace failure** | Exception is raised; target remains old file | Yes | Yes | Yes | Yes: inject replace failure |
| **Concurrent writers** | Each writer has a unique temp path; last successful `replace` wins; readers see old or new, never mixed | Yes | Yes | Best-effort | Yes: threaded writers test |
| **Reader sees old file** | Before `replace`, reader sees old file; this is expected and safe | Yes | N/A | N/A | Yes: read-during-write test |
| **Reader sees new file** | After successful `replace`, reader sees new file | Yes | N/A | N/A | Yes: read-after-write test |
| **Reader never sees partial file** | `replace` is atomic for same-filesystem paths; target path always points to a fully-written file | Yes | Yes | N/A | Yes: partial-read regression test |
| **Temp cleanup failure** | Cleanup is best-effort; a leftover temp file does not affect target safety | Yes | Yes | Best-effort (logged at debug) | Yes: assert no fixed `.tmp` remains |
| **Corrupt existing file** | Caller-side corrupt-state logic (`KillSwitchState.load`, `HeartbeatManager.is_expired`) continues to fail closed as today; helper only rewrites valid payloads | Yes | N/A (corrupt file is preserved until a successful write) | N/A | Yes: corrupt-state fail-closed regression test |
| **Corrupt incoming payload** | Helper does not validate payload semantics; it writes whatever the caller provides. Invalid JSON serialization raises before any temp write, leaving target untouched | Yes | Yes | Yes if temp was created | Yes: invalid payload raises without touching target |

---

## 11. Concurrency / race-condition analysis

### 11.1 Within a single process

- `KillSwitchController` already uses `threading.RLock` plus an advisory file
  lock (`_lock_file` / `_unlock_file`). CAND-009 does not change this. The
  helper is called inside the lock, so only one thread writes at a time.
- `HeartbeatManager`, `DeadmanSwitch`, and `AdvancedKillSwitchState` are not
  heavily contended in current usage, but the helper makes them safe against
  concurrent writes by independent callers.

### 11.2 Across processes

- Same-file advisory locks (where `fcntl` is available) protect
  `KillSwitchController`. Other modules rely on filesystem atomicity.
- Unique temp names mean two processes writing the same target will not
  corrupt each other's temp files. The last successful `replace` wins.
- Readers always see a consistent old or new file because `replace` renames the
  directory entry.

### 11.3 Rapid retries

- A retry after a failed write receives a new unique temp path, so a stale
  temp file from the previous attempt is never reused.

### 11.4 Reader / writer race

- Readers open the target path. If the writer has not yet called `replace`,
  the reader sees the old file. If `replace` has completed, the reader sees the
  new file. There is no window in which the reader sees a partially-written
  target file.

---

## 12. Backward compatibility

- **File format:** unchanged. JSON payloads, indentation, key ordering, and
  optional `chmod(0o600)` behavior are preserved.
- **Public API:** unchanged. `HeartbeatManager.record`, `write_deadman_heartbeat`,
  `KillSwitchController.enable/disable/status`, and `KillSwitchState.load/save`
  keep the same signatures.
- **On-disk paths:** unchanged. Only the temp-file name changes.
- **Fail-closed behavior:** unchanged. Corrupt/missing state still fails closed
  in callers.
- **Permissions:** unchanged where callers currently request `0o600`.
- **CLI contract:** the only behavioral change outside the helper is adding
  `"doctor"` to `tests/fixtures/cli_command_contract.json`, which documents an
  already-existing command. No CLI behavior changes.

---

## 13. Security / safety boundaries

CAND-009 preserves all existing safety boundaries and adds no new execution
surface:

- No live trading, live submit, order placement, order cancellation, position
  flattening, or pending-order creation.
- No broker/provider calls, credential loading, or network access.
- No weakening of `RiskManager`, kill switch, deadman, heartbeat, or audit
  hash-chain.
- No changes to approval gates or kill-switch mode semantics.
- The helper module is stdlib-only and isolated from trading logic.
- No secrets or file paths are logged.

---

## 14. Test plan

### 14.1 New helper tests (`tests/test_atomic_write.py`)

1. `test_atomic_write_text_creates_target` — target file contains exact content.
2. `test_atomic_write_json_serializes_payload` — target file contains valid JSON.
3. `test_temp_file_is_in_same_directory` — temp file is created in target parent.
4. `test_temp_file_name_is_unique` — repeated calls use different temp names.
5. `test_no_fixed_target_tmp_name` — no file named `<target>.tmp` is created.
6. `test_replace_is_atomic` — simulate a reader during write; reader sees old or
   new, never a partial file.
7. `test_temp_file_cleaned_up_on_success` — best-effort cleanup leaves no temp.
8. `test_temp_file_cleaned_up_on_failure` — on injected write/replace failure,
   temp is removed.
9. `test_old_file_preserved_on_failure` — if write or replace fails, target old
   content is unchanged.
10. `test_chmod_best_effort` — when `chmod` is requested and platform allows,
    target has the requested mode.
11. `test_invalid_parent_raises` — helper raises `OSError` when parent cannot be
    created.
12. `test_invalid_payload_raises_without_touching_target` — non-serializable
    payload raises before temp creation or target mutation.

### 14.2 Concurrency tests (`tests/test_atomic_write.py`)

1. `test_repeated_rapid_writes_do_not_collide` — 100 rapid sequential writes to
   the same target succeed.
2. `test_parallel_writes_do_not_raise_file_not_found` — multiple threads write
   concurrently; no `FileNotFoundError` and final file is valid JSON/text.
3. `test_no_partial_file_observed` — a reader thread polls during writer
   threads; every observation is either old valid content or new valid content.

### 14.3 Safety module regression tests

Extend existing test files; do not change existing test semantics.

- `tests/test_heartbeat.py` (new file, or add to existing safety test directory):
  - `test_heartbeat_record_repeated` — repeated records produce monotonic
    timestamps and valid JSON.
  - `test_heartbeat_corrupt_file_still_expired` — corrupt file fails closed.
- `tests/test_deadman.py` (existing `tests/safety/test_deadman.py`):
  - Add `test_deadman_heartbeat_write_is_atomic` — after
    `write_deadman_heartbeat`, target exists, is valid JSON, and no fixed
    `<target>.tmp` exists.
- `tests/test_safety_state.py` (new file):
  - `test_state_save_load_roundtrip` — save then load returns same mode/reason.
  - `test_state_save_repeated` — repeated saves produce valid JSON.
  - `test_state_corrupt_load_fails_closed` — corrupt file loads as
    `locked_down`.
- `tests/test_kill_switch*.py` (extend existing):
  - `test_kill_switch_state_persists_across_instances` already exists; add
    `test_kill_switch_no_fixed_tmp_after_write`.

### 14.4 Live-mode regression tests

- Existing tests already verify `atlas run --mode live` exits 2. CAND-009 does
  not change this. Add a design note requiring the verification matrix command
  to be rerun after implementation.

### 14.5 CLI compatibility hygiene tests

- `tests/test_cli_command_compatibility.py`:
  - Add `test_doctor_is_in_contract` asserting `"doctor"` is in
    `top_level_commands`.
- Run `python3.11 scripts/check_cli_command_compatibility.py` and confirm no
  `doctor` warning.

---

## 15. Static / checker plan

1. **Lint/formatting:** `ruff check src/atlas_agent/safety/atomic_write.py` and
   any modified files.
2. **Type check:** `mypy src/atlas_agent/safety/atomic_write.py` (project
   already uses mypy).
3. **Forbidden claims:** re-run `scripts/check_forbidden_claims.py`.
4. **Bounded autonomy governance:** re-run
   `scripts/check_bounded_autonomy_governance.py`.
5. **CLI contract:** re-run `scripts/check_cli_command_compatibility.py` after
   adding `"doctor"`.
6. **Grep for old pattern:** add a one-time check (or a lightweight script) to
   ensure no new code reintroduces `with_suffix(.*"\.tmp")` in safety modules.
   This can be a shell grep in the verification matrix rather than a new
   committed script.

No new long-running checker script is required for CAND-009.

---

## 16. CLI doctor contract hygiene plan

### 16.1 Decision

The top-level `doctor` command in `src/atlas_agent/cli.py` (lines 168-181) is
intentional and read-only. It is registered alongside `init`, `validate`, and
`configure`. It does not execute trading logic, load credentials, or call
brokers/providers.

### 16.2 Companion fix

Add `"doctor"` to `top_level_commands` in
`tests/fixtures/cli_command_contract.json`.

**Current `top_level_commands` snippet (lines 4-49):**

```json
"top_level_commands": [
    "agent",
    "approve-order",
    ...
    "validate",
    "workspace"
]
```

**Proposed change:**

```json
"top_level_commands": [
    "agent",
    "approve-order",
    ...
    "doctor",
    "validate",
    "workspace"
]
```

Alphabetical placement is next to `dashboard` / `demo` / `discipline`; place
after `discipline` and before `events` for readability.

### 16.3 Boundaries

- Do not change CLI behavior.
- Do not remove `doctor`.
- Do not add new commands.
- Do not expand this companion item beyond the one-line contract update.

---

## 17. Verification matrix

Run after implementation:

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 -m pytest tests/test_atomic_write.py -q
python3.11 -m pytest tests/test_heartbeat.py tests/test_deadman.py tests/test_safety_state.py -q
python3.11 -m pytest tests/test_kill_switch*.py -q
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

If feasible after implementation:

```bash
bash scripts/release_check.sh
python3.11 -m pytest -q --durations=25
```

Expected results:
- All commands exit 0 except `atlas run --mode live`, which must exit 2.
- `scripts/check_cli_command_compatibility.py` must report zero warnings
  (no `doctor` warning).
- No `live` readiness claim appears in output.

---

## 18. Rollback plan

If CAND-009 causes regressions:

1. Revert the four source-file edits to restore the inline fixed `.tmp` logic.
2. Delete `src/atlas_agent/safety/atomic_write.py`.
3. Delete `tests/test_atomic_write.py` and revert additions to existing tests.
4. Revert the one-line `"doctor"` addition to
   `tests/fixtures/cli_command_contract.json` if it causes unrelated issues.
5. Re-run the verification matrix.
6. The system returns to the v0.6.16 safety-state write behavior, which is
   already fail-closed for readers.

---

## 19. Acceptance criteria

- [ ] `docs/safety-state-atomic-write-hardening-design.md` exists and contains
      all sections required by the CAND-009 brief.
- [ ] `src/atlas_agent/safety/atomic_write.py` is implemented with the API in
      section 8 and uses stdlib only.
- [ ] All four fixed `.tmp` patterns in sections 4 are replaced with helper calls.
- [ ] No public API signature changes.
- [ ] File formats, JSON indentation/sorting, and `chmod(0o600)` behavior are
      preserved.
- [ ] New tests cover helper behavior, concurrency, and safety-module regression.
- [ ] Existing safety-module tests still pass.
- [ ] `atlas run --mode live` still exits 2.
- [ ] `scripts/check_cli_command_compatibility.py` passes with no `doctor`
      warning after the contract update.
- [ ] All verification matrix commands pass (with the expected live-mode
      failure).
- [ ] No live trading, live submit, broker/provider execution, credential
      loading, or order placement is introduced.
- [ ] Only the design doc, the new helper, the four source files, the new tests,
      and the one-line CLI contract JSON are modified. No release metadata,
      version, tag, or changelog release-date changes are made.

---

## 20. Open questions, resolved conservatively

1. **Should the helper `fsync` before `replace`?**
   - **Resolved:** No by default. Existing code uses `Path.write_text`, which
     does not fsync. CAND-009 preserves that style. An optional `fsync=False`
     parameter may be left for future callers but must not be enabled by CAND-009.

2. **Should the helper enforce a specific file extension for temp files?**
   - **Resolved:** Use `.tmp` suffix with a unique prefix derived from the target
     name. This keeps temp files recognizable while preventing collisions.

3. **Should the helper create missing parent directories?**
   - **Resolved:** Yes, default `ensure_parent=True`, matching all four current
     callers. Callers that want to fail if the parent is missing can pass
     `ensure_parent=False`.

4. **Should the helper expose a single `atomic_write` function or separate text
   and JSON functions?**
   - **Resolved:** Separate `atomic_write_text` and `atomic_write_json` functions.
     This mirrors the existing callers (two JSON modules, one text-like module
     in the future) and keeps the JSON option serialization explicit.

5. **Should the companion CLI `doctor` fix be part of CAND-009 or a separate
   hygiene item?**
   - **Resolved:** It is a companion one-line hygiene fix documented in this
     design, not a separate candidate. It does not expand CAND-009 scope beyond
     a contract update.

6. **Should CAND-009 add a new static checker script?**
   - **Resolved:** No new committed checker. The verification matrix uses existing
     scripts plus a grep for the old fixed `.tmp` pattern.

7. **Should temp files be hidden with a leading dot?**
   - **Resolved:** No. Use a unique visible name (`<target>.<random>.tmp`). This
     keeps temp files easy to find during incident response while still being
     clearly temporary.

---

## Design review readiness

This design is **ready for independent review**.

The specification is complete, bounded, and conservative. It changes only
safety-state persistence mechanics, introduces no live-trading or execution
surface, and includes a clear test and verification plan.
