# CAND-010: Safety-State Persistence Regression Guard Implementation Plan

> I'm using the `writing-plans` skill to create the implementation plan.
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a committed static regression guard (`scripts/check_safety_atomic_write.py`) plus a companion pytest test (`tests/test_check_safety_atomic_write.py`) that fails verification if any of the four CAND-009 safety persistence modules reintroduce fixed `<target>.tmp` write patterns.

**Architecture:** A stdlib-only checker script scans a deterministic list of guarded source files for forbidden fixed-temp construction patterns. It accepts an optional repository root argument, emits file/line/pattern violations, and exits `2` on regression, `1` on internal error, and `0` when clean. A pytest wrapper verifies the checker against the real repo and against temporary injected regressions. The checker is wired into `scripts/dev_check.sh` (and therefore `scripts/release_check.sh --quick`) and optionally into `scripts/ci_check.sh`.

**Tech Stack:** Python 3.11+, `pathlib`, `re`, `sys`, `argparse`, `subprocess` (stdlib only). No broker/provider/config imports, no credential loading, no network access.

**Plan location note:** The repository does not have a dedicated implementation-plans directory. The user specified `docs/safety-state-persistence-regression-guard-implementation-plan.md`, so this plan is saved at that path, mirroring the CAND-009 implementation plan convention.

---

## 1. Title and candidate ID

- **Candidate ID:** CAND-010
- **Title:** Safety-State Persistence Regression Guard
- **Target release line:** v0.6.18
- **Current public release:** v0.6.17
- **Package version:** 0.6.17
- **Status:** implementation planning only
- **Design document:** `docs/safety-state-persistence-regression-guard-design.md`
- **Design review verdict:** `PASS_WITH_WARNINGS`
- **Design review recommendation:** Accept the design and proceed to implementation planning. Do not proceed to implementation without this plan and a separate implementation review.

---

## 2. Planning baseline

| Item | Value |
|---|---|
| Repository | `usernotfinded/atlas-agent` |
| Branch | `main` |
| Planning HEAD | `e3915b8180cdb643b95e1a697f6896e918a70dc3` |
| Design document | `docs/safety-state-persistence-regression-guard-design.md` |
| Design review verdict | `PASS_WITH_WARNINGS` |
| Public release | `v0.6.17` |
| Package version | `0.6.17` |
| Candidate line | `v0.6.18` |
| Next planned release | `v0.6.18` |
| Release status | no v0.6.18 tag, release, or PyPI publication exists |
| PyPI published | `false` |
| Live mode | fail-closed (`atlas run --mode live` exits 2) |

### Phase 0 baseline verification (already run during planning)

```bash
git status --short
git rev-parse HEAD
git log --oneline -10
git tag --points-at HEAD
git tag --list 'v0.6.18*'
git ls-remote --tags origin 'v0.6.18*'
python3.11 - <<'PY'
import atlas_agent
print(atlas_agent.__version__)
PY
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
atlas validate
atlas run --mode live
git diff --check
```

Observed results during planning:

- Tree is clean (`git status --short` empty).
- HEAD is `e3915b8180cdb643b95e1a697f6896e918a70dc3`.
- `v0.6.17` tag points at HEAD.
- No local or remote `v0.6.18*` tag.
- Package version is `0.6.17`.
- `check_release_metadata.py`, `check_version_consistency.py`, `check_forbidden_claims.py`, `check_bounded_autonomy_governance.py`, `check_cli_command_compatibility.py` all exit 0.
- `atlas validate` reports workspace/config missing but no errors.
- `atlas run --mode live` exits 2 / fail-closed.
- `git diff --check` exits 0.

---

## 3. Design-review findings incorporated

The independent design review produced three non-blocking warnings. This plan accounts for each:

1. **HEAD mismatch in design baseline.** Section 2 of the design doc lists baseline/design HEAD `3cffef98f0fdab0cf248193de19d4295321eba4a`; the actual design commit HEAD is `e3915b8180cdb643b95e1a697f6896e918a70dc3`. During implementation, update the design doc's Section 2 to list the real design HEAD (`e3915b8...`) and add a note explaining the discrepancy, or simply correct it to the actual value. This plan documents the correction in Section 7 (docs/changelog plan).

2. **`ruff`/`mypy` availability.** The design review noted these tools were unavailable. In the implementation environment, `ruff` and `mypy` binaries are present. This plan therefore requires running them on modified files if companion cleanup is applied, and recording their output as evidence. If they become unavailable in a different environment, the cleanup must not be guessed; report the missing tool as a warning and skip the cleanup.

3. **Broad `+ ".tmp"` false positives.** The design doc's broad `+ ".tmp"` pattern can flag legitimate code. This plan scopes the broad concatenation check to lines that also contain a `Path`-like construction signal (`with_suffix`, `write_text`, `replace`, assignment to a `tmp_path`-like name, or `Path(`), and skips pure comment lines. Literal `".json.tmp"` and `with_suffix(...)` patterns remain hard errors even in comments because they describe the exact anti-pattern.

Additional nice-to-have review items folded in:

- The checker accepts a positional `repo_root` argument and also supports `--repo-root`, so tests can point it at temporary fixtures cleanly.
- The checker documents and uses the exit-code contract `0 clean`, `1 internal error`, `2 violation`.
- Section 9.2 explains why `target + ".tmp"` is listed separately from `str(target) + ".tmp"`.

---

## 4. Scope

In scope for implementation:

- Create `scripts/check_safety_atomic_write.py`, a stdlib-only static checker.
- Create `tests/test_check_safety_atomic_write.py`, a pytest companion that verifies the checker passes the current codebase and fails injected regressions.
- Integrate the checker into `scripts/dev_check.sh` so `scripts/release_check.sh --quick` runs it.
- Optionally integrate the checker into `scripts/ci_check.sh` if consistent with existing wiring.
- Apply optional companion lint/type hygiene cleanup to CAND-009 touched files, verified by `ruff`/`mypy`.
- Update `docs/safety-state-persistence-regression-guard-design.md` to correct the baseline HEAD and mark the design as "implementation planned".
- Record CAND-010 under `CHANGELOG.md` `[Unreleased]` only after implementation, not during planning.

Out of scope (non-goals) are listed in Section 5.

---

## 5. Non-goals

CAND-010 implementation explicitly does **not**:

- Implement runtime behavior changes.
- Enable live trading or live submit.
- Place, cancel, or flatten orders.
- Create pending orders or mutate approval queues.
- Call brokers, providers, or network endpoints.
- Load credentials, secrets, or API keys.
- Change safety-state file formats or schemas.
- Change the semantics of `HeartbeatManager`, `DeadmanSwitch`, `KillSwitchController`, or `KillSwitchState`.
- Weaken `RiskManager`, kill switch, deadman, heartbeat, or audit hash-chain.
- Add `fsync`, third-party dependencies, or new runtime logic.
- Bump version, tag, release, or publish to PyPI.
- Create a v0.6.18 release cutover.
- Modify release metadata or changelog release dates during planning.

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
- No weakening of kill switch, deadman, heartbeat, or audit hash-chain.
- No audit hash-chain bypass.
- `atlas run --mode live` remains exit 2 / fail-closed.
- Package version remains `0.6.17`.
- Public release remains `v0.6.17`.
- No v0.6.18 tag, GitHub Release, or PyPI publication is created.
- CAND-010 remains a static regression guard only.
- CAND-009 atomic-write behavior remains unchanged.

---

## 7. Selected checker/test architecture

**Primary architecture:** Approach A (dedicated checker script) with a lightweight Approach-C test companion, exactly as recommended by the design doc.

Create:

- `scripts/check_safety_atomic_write.py` — the authoritative static regression guard.
- `tests/test_check_safety_atomic_write.py` — verifies the checker passes on the current repo and fails injected regressions.

This mirrors repository conventions:

- `scripts/check_demo_proof.py` → `tests/test_demo_proof_checker.py`
- `scripts/check_submit_execution_safety.py` → `tests/test_submit_execution_safety_check.py`
- `scripts/check_forbidden_claims.py` → used in gates

The checker is the authoritative gate; the test is the safety net that prevents silent checker breakage.

---

## 8. File-by-file implementation plan

| # | File | Action | Responsibility |
|---|---|---|---|
| 1 | `scripts/check_safety_atomic_write.py` | Create | Static regression guard for fixed `<target>.tmp` patterns. |
| 2 | `tests/test_check_safety_atomic_write.py` | Create | Verify checker pass/fail/output behavior on real repo and temp fixtures. |
| 3 | `scripts/dev_check.sh` | Modify | Add checker invocation after bounded autonomy governance check. |
| 4 | `scripts/ci_check.sh` | Modify (optional) | Add checker invocation near other static checks if consistent. |
| 5 | `tests/safety/test_atomic_write.py` | Modify (optional companion cleanup) | Remove unused `original_write_text` / `original_replace` assignments. |
| 6 | `tests/safety/test_deadman.py` | Modify (optional companion cleanup) | Add missing `from pathlib import Path` import. |
| 7 | `tests/safety/test_kill_switch_core.py` | Modify (optional companion cleanup) | Add missing `from pathlib import Path` import. |
| 8 | `src/atlas_agent/safety/kill_switch.py` | Modify (optional companion cleanup) | Address mypy `union-attr` on `last_heartbeat().isoformat()`. |
| 9 | `docs/safety-state-persistence-regression-guard-design.md` | Modify (minor) | Correct baseline HEAD mismatch and update status note. |
| 10 | `docs/safety-state-persistence-regression-guard-implementation-plan.md` | Update | Mark planning complete and note any deviations. |
| 11 | `CHANGELOG.md` | Modify (after implementation) | Add CAND-010 entry under `[Unreleased]`; no release claim. |

### Guarded files (must contain no fixed `<target>.tmp` patterns)

```text
src/atlas_agent/safety/heartbeat.py
src/atlas_agent/safety/deadman.py
src/atlas_agent/safety/kill_switch.py
src/atlas_agent/safety/state.py
```

### Reference/helper file (allowed to construct `.tmp` for unique temp names)

```text
src/atlas_agent/safety/atomic_write.py
```

### Why `atomic_write.py` is not a guarded target

`atomic_write.py` is the only file allowed to construct `.tmp` names, and it must do so via `tempfile.mkstemp`. The checker's job is to ensure callers do not bypass the helper. The helper itself is trusted by candidate boundary; a separate optional positive check may verify it uses `mkstemp`, but that is not a hard gate.

---

## 9. Disallowed/allowed pattern policy

### 9.1 Disallowed patterns in guarded files

The checker must detect the following patterns in the four guarded files. Matching is case-sensitive and line-oriented.

| # | Pattern | Example that must fail |
|---|---|---|
| 1 | `with_suffix(... + ".tmp")` | `tmp_path = target.with_suffix(target.suffix + ".tmp")` |
| 2 | `with_suffix(... + '.tmp')` | `tmp_path = target.with_suffix(target.suffix + '.tmp')` |
| 3 | `suffix + ".tmp"` | `tmp_path = target.suffix + ".tmp"` |
| 4 | `suffix + '.tmp'` | `tmp_path = target.suffix + '.tmp'` |
| 5 | literal `".json.tmp"` | `tmp_path = target.parent / (target.name + ".json.tmp")` |
| 6 | literal `'.json.tmp'` | `tmp_path = target.parent / (target.name + '.json.tmp')` |
| 7 | `Path(str(target) + ".tmp")` | `tmp_path = Path(str(target) + ".tmp")` |
| 8 | `str(target) + ".tmp"` | `temp = str(target) + ".tmp"` |
| 9 | `target + ".tmp"` | `temp = target + ".tmp"` (where `target` is a `Path`-like name) |
| 10 | `NamedTemporaryFile(delete=False)` | Any use outside the helper file |
| 11 | `mktemp` | Insecure fixed-name temp generation |
| 12 | Hardcoded temp paths ending in `.json.tmp` | e.g., `"memory/state.json.tmp"` |

### 9.2 Why `target + ".tmp"` is separate from `str(target) + ".tmp"`

`str(target) + ".tmp"` is an explicit string-concatenation pattern that presumes a `Path` object is being coerced. `target + ".tmp"` is a distinct syntactic form: it may occur when a variable named `target` is already a string, or when a developer mistakenly attempts string concatenation directly on a `Path`-like name. Listing it separately ensures the checker catches both forms without relying on the regex engine to infer variable types. It also documents that either form is forbidden, even if type narrowing would make one of them a runtime error.

### 9.3 Regex-ready pattern definitions

The implementation should use regexes equivalent to:

```text
r'\.with_suffix\s*\([^)]*\+\s*["\']\.tmp["\']'
r'\.with_suffix\s*\([^)]*\+\s*["\']\.json\.tmp["\']'
r'suffix\s*\+\s*["\']\.tmp["\']'
r'suffix\s*\+\s*["\']\.json\.tmp["\']'
r'["\']\.json\.tmp["\']'
r'Path\s*\(\s*str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']\s*\)'
r'str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']'
r'\+\s*["\']\.tmp["\']'
r'NamedTemporaryFile\s*\('
r'\bmktemp\b'
r'["\'][^"\']*\.json\.tmp["\']'
```

Notes:

- The broad `+ ".tmp"` pattern is scoped to lines that also contain a `Path`-like construction signal (`with_suffix`, `write_text`, `replace`, assignment to a `tmp_path`-like name, or `Path(`). Pure comment lines are skipped for this pattern.
- Literal `".json.tmp"` and `with_suffix(...)` patterns are hard errors even in comments because they describe the exact anti-pattern.
- `mktemp` is flagged only as a word boundary so that `mkstemp` in the helper is not matched.
- The existing `kill_switch.py` lock path uses `with_suffix(self.state_path.suffix + ".lock")` (line 169). This is a `.lock` construction, not `.tmp`, and therefore does not match any of the patterns above.

### 9.4 Allowed patterns

The checker must allow:

1. **Helper imports** in guarded files:
   ```python
   from atlas_agent.safety.atomic_write import atomic_write_json, atomic_write_text
   ```

2. **Helper calls** in guarded files:
   ```python
   atomic_write_json(self.heartbeat_path, payload, chmod=0o600)
   atomic_write_text(self.state_path, content)
   ```

3. **Unique temp creation in `atomic_write.py`**:
   ```python
   fd, temp_str = tempfile.mkstemp(
       dir=target.parent,
       prefix=f"{target.name}.",
       suffix=".tmp",
   )
   ```
   The checker excludes `atomic_write.py` from the fixed-temp scan.

4. **Tests that intentionally assert the checker catches regressions**: The checker script must not scan `tests/test_check_safety_atomic_write.py` with strict rules. Tests build injected patterns dynamically where necessary.

5. **Historical documentation** describing old behavior, unless the checker is intentionally extended to scan docs. The default scope is source files only.

6. **Comments in guarded files** that mention `.tmp` in a negative or historical context, provided they do not contain actual executable code patterns. Pure comment lines are skipped for the broad `.tmp` concatenation pattern.

---

## 10. Checker algorithm and CLI contract

### 10.1 Module outline

`scripts/check_safety_atomic_write.py`

Responsibilities:

1. Resolve repository root from positional argument, `--repo-root`, or script location.
2. Resolve the four guarded files and the helper file.
3. Verify guarded files exist; exit `1` if any are missing or repo root is invalid.
4. For each guarded file, scan each line for disallowed patterns.
5. Record violations with file path, line number, pattern description, and source snapshot.
6. Print violations and exit `2` if any found; otherwise print `PASSED` and exit `0`.

### 10.2 CLI contract

```text
usage: check_safety_atomic_write.py [-h] [--repo-root REPO_ROOT] [repo_root]

Static regression guard for fixed <target>.tmp safety-state writes.

positional arguments:
  repo_root             repository root path (default: parent of script dir)

options:
  -h, --help            show this help message and exit
  --repo-root REPO_ROOT
                        repository root path (alternative to positional)
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | No disallowed patterns found. |
| `1` | Internal checker error (invalid repo root, missing guarded file, bad argument). |
| `2` | One or more disallowed patterns found. |

### 10.3 Reference implementation

The following is the exact code an implementer should write.

```python
#!/usr/bin/env python3
"""Static regression guard for fixed <target>.tmp safety-state writes.

Deterministic and local-only. Does not import Atlas runtime modules, load
credentials, contact brokers, or make network calls.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


class Violation(NamedTuple):
    path: Path
    line: int
    pattern: str
    snapshot: str


# Files that must not contain fixed <target>.tmp construction patterns.
GUARDED_RELATIVE_PATHS = [
    "src/atlas_agent/safety/heartbeat.py",
    "src/atlas_agent/safety/deadman.py",
    "src/atlas_agent/safety/kill_switch.py",
    "src/atlas_agent/safety/state.py",
]

# Helper file is allowed to construct .tmp names via mkstemp.
HELPER_RELATIVE_PATH = "src/atlas_agent/safety/atomic_write.py"

# Patterns are (regex, human-readable description).
# Order matters: the first matching pattern on a line wins.
DISALLOWED_PATTERNS: list[tuple[str, str]] = [
    (
        r'\.with_suffix\s*\([^)]*\+\s*["\']\.json\.tmp["\']',
        "fixed with_suffix .json.tmp pattern",
    ),
    (
        r'\.with_suffix\s*\([^)]*\+\s*["\']\.tmp["\']',
        "fixed with_suffix .tmp pattern",
    ),
    (r'suffix\s*\+\s*["\']\.json\.tmp["\']', "suffix + .json.tmp pattern"),
    (r'suffix\s*\+\s*["\']\.tmp["\']', "suffix + .tmp pattern"),
    (r'["\']\.json\.tmp["\']', "literal .json.tmp"),
    (
        r'Path\s*\(\s*str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']\s*\)',
        "Path(str(target) + .tmp) pattern",
    ),
    (r'str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']', "str(target) + .tmp pattern"),
    (r'NamedTemporaryFile\s*\(', "NamedTemporaryFile usage outside helper"),
    (r'\bmktemp\b', "mktemp usage"),
    (r'["\'][^"\']*\.json\.tmp["\']', "hardcoded .json.tmp path"),
]

# Broad .tmp concatenation is only an error in a code-context line.
BROAD_TMP_PATTERN = (
    r'\+\s*["\']\.tmp["\']',
    "broad + .tmp concatenation",
)

# A line is considered code-context for the broad pattern if it contains any
# of these signals. This avoids flagging comments/docstrings that merely
# mention the old pattern.
_BROAD_CONTEXT_SIGNALS = [
    "with_suffix",
    "write_text",
    "replace",
    "Path(",
    "tmp_path",
    "temp_path",
    "tmp =",
    "temp =",
]


def _is_comment_line(line: str) -> bool:
    return line.strip().startswith("#")


def _has_broad_context_signal(line: str) -> bool:
    return any(signal in line for signal in _BROAD_CONTEXT_SIGNALS)


def _scan_line(line: str) -> str | None:
    for pattern, description in DISALLOWED_PATTERNS:
        if re.search(pattern, line):
            return description
    broad_pattern, broad_description = BROAD_TMP_PATTERN
    if not _is_comment_line(line) and _has_broad_context_signal(line):
        if re.search(broad_pattern, line):
            return broad_description
    return None


def _scan_file(path: Path, repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        description = _scan_line(line)
        if description is not None:
            violations.append(
                Violation(
                    path=path.relative_to(repo_root),
                    line=lineno,
                    pattern=description,
                    snapshot=line.strip(),
                )
            )
    return violations


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = args.repo_root or (args.positional_root if args.positional_root else None)
    if raw is None:
        return Path(__file__).resolve().parent.parent
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"repo root is not a directory: {root}")
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "positional_root",
        nargs="?",
        default=None,
        help="repository root path (default: parent of script directory)",
    )
    parser.add_argument(
        "--repo-root",
        dest="repo_root",
        default=None,
        help="repository root path (alternative to positional)",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = _resolve_repo_root(args)
    except ValueError as exc:
        print(f"Safety atomic-write regression check ERROR: {exc}", file=sys.stderr)
        return 1

    guarded_paths = [repo_root / rel for rel in GUARDED_RELATIVE_PATHS]
    helper_path = repo_root / HELPER_RELATIVE_PATH

    missing = [p for p in guarded_paths + [helper_path] if not p.exists()]
    if missing:
        for p in missing:
            rel = p.relative_to(repo_root) if p.is_relative_to(repo_root) else p
            print(
                f"Safety atomic-write regression check ERROR: missing file {rel}",
                file=sys.stderr,
            )
        return 1

    violations: list[Violation] = []
    for path in guarded_paths:
        violations.extend(_scan_file(path, repo_root))

    if violations:
        print("Safety atomic-write regression check FAILED")
        for v in violations:
            print(f"  {v.path}:{v.line}: {v.pattern}")
            print(f"      {v.snapshot}")
        return 2

    print("Safety atomic-write regression check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### 10.4 Expected behavior on current codebase

Running the checker against the current repo must exit 0 and print:

```text
Safety atomic-write regression check PASSED
```

---

## 11. Integration plan

### 11.1 Preferred integration

Add the checker to `scripts/dev_check.sh` after the bounded autonomy governance check (step `4a`) and before the bounded autonomy governance tests (step `4b`). This causes `scripts/release_check.sh --quick` (which delegates to `dev_check.sh`) to run it automatically.

Suggested insertion in `scripts/dev_check.sh`:

```bash
echo ""
echo "4a. bounded autonomy governance check"
SECONDS=0
"$PYTHON_BIN" scripts/check_bounded_autonomy_governance.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4a1. safety atomic-write regression guard"
SECONDS=0
"$PYTHON_BIN" scripts/check_safety_atomic_write.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

### 11.2 Optional CI integration

If the repository prefers the checker in `scripts/ci_check.sh` as well, add the same single-line invocation near the other static checks (after step `3a. bounded autonomy governance check`):

```bash
echo ""
echo "3a1. safety atomic-write regression guard"
SECONDS=0
"$PYTHON_BIN" scripts/check_safety_atomic_write.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Because `release_check.sh --quick` already covers dev checks, duplicate invocation in CI is optional. The plan recommends adding it only if it matches the existing CI wiring style.

### 11.3 GitHub Actions

If the repository's GitHub Actions workflow invokes `scripts/ci_check.sh` or `scripts/release_check.sh --quick`, no workflow change is required once the checker is integrated into those scripts.

### 11.4 Integration constraints

- The checker must run in less than one second.
- It must fail fast (non-zero exit) with a clear message.
- It must not require network access, credentials, or a configured workspace.
- It must not write to disk.
- Do not remove or weaken existing gates.
- Do not remove CAND-009 tests.

---

## 12. Test plan

### 12.1 New test file

`tests/test_check_safety_atomic_write.py`

### 12.2 Required test cases

| # | Test | Expected result |
|---|---|---|
| 1 | `test_checker_passes_current_codebase` | Running `scripts/check_safety_atomic_write.py` against repo root exits 0 and prints `PASSED`. |
| 2 | `test_checker_fails_heartbeat_fixed_tmp` | Inject fixed `.tmp` pattern into a temp copy of `heartbeat.py`, run checker, expect exit 2 and output mentioning `heartbeat.py` and the pattern. |
| 3 | `test_checker_fails_deadman_fixed_tmp` | Same as #2 for `deadman.py`. |
| 4 | `test_checker_fails_kill_switch_fixed_tmp` | Same as #2 for `kill_switch.py`. |
| 5 | `test_checker_fails_state_fixed_tmp` | Same as #2 for `state.py`. |
| 6 | `test_checker_permits_atomic_write_helper` | The helper file's `mkstemp` `.tmp` construction does not cause a violation. |
| 7 | `test_checker_permits_regression_strings_in_tests` | Tests that assert `(tmp_path / "target.json.tmp").exists()` do not cause the checker to fail. Achieved by not scanning `tests/` with strict rules. |
| 8 | `test_checker_output_includes_file_and_line` | An injected regression produces output containing the relative path and a line number. |
| 9 | `test_checker_exits_1_for_invalid_repo_root` | Running with a non-existent repo root exits 1. |
| 10 | `test_checker_exits_1_for_missing_guarded_file` | Running against a temp repo missing a guarded file exits 1. |
| 11 | `test_checker_exits_2_for_violation` | An injected regression exits 2. |
| 12 | `test_checker_accepts_positional_root` | Passing repo root as positional argument works. |
| 13 | `test_checker_accepts_repo_root_flag` | Passing repo root via `--repo-root` works. |
| 14 | `test_existing_cand009_tests_still_pass` | Run the existing CAND-009 safety tests and assert they pass. |

### 12.3 Reference test implementation

The following is the exact code an implementer should write.

```python
"""Tests for the CAND-010 safety atomic-write regression guard.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_safety_atomic_write.py"
GUARDED_FILES = {
    "heartbeat.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "heartbeat.py",
    "deadman.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "deadman.py",
    "kill_switch.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "kill_switch.py",
    "state.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "state.py",
}
HELPER_FILE = REPO_ROOT / "src" / "atlas_agent" / "safety" / "atomic_write.py"


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _build_tmp_repo(tmp_path: Path, *, omit: str | None = None) -> Path:
    repo = tmp_path / "repo"
    target = repo / "src" / "atlas_agent" / "safety"
    target.mkdir(parents=True)
    for name, src in GUARDED_FILES.items():
        if name == omit:
            continue
        dst = target / name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    helper_dst = target / "atomic_write.py"
    helper_dst.write_text(HELPER_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    return repo


def _inject_regression(repo: Path, filename: str, regression: str) -> None:
    target = repo / "src" / "atlas_agent" / "safety" / filename
    original = target.read_text(encoding="utf-8")
    injected = original + f"\n# injected regression\n{regression}\n"
    target.write_text(injected, encoding="utf-8")


class TestCheckerExists:
    def test_script_exists_and_is_executable(self) -> None:
        assert CHECKER_SCRIPT.exists(), f"Checker not found: {CHECKER_SCRIPT}"
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env python3"), "Checker missing python3 shebang"


class TestCheckerPassesOnCurrentRepo:
    def test_checker_passes(self) -> None:
        result = _run_checker()
        assert result.returncode == 0, (
            f"Checker failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout

    def test_checker_accepts_positional_root(self) -> None:
        result = _run_checker(str(REPO_ROOT))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_checker_accepts_repo_root_flag(self) -> None:
        result = _run_checker("--repo-root", str(REPO_ROOT))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout


class TestCheckerFailsInjectedRegressions:
    @pytest.mark.parametrize("filename", list(GUARDED_FILES.keys()))
    def test_injected_with_suffix_tmp_fails(self, tmp_path: Path, filename: str) -> None:
        # Build the regression string dynamically so the literal forbidden
        # pattern does not appear in this test source.
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, filename, regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2, (
            f"Expected violation exit 2, got {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert filename in result.stdout
        assert "fixed with_suffix .tmp pattern" in result.stdout

    def test_injected_literal_json_tmp_fails(self, tmp_path: Path) -> None:
        suffix = '"' + '.json.tmp"'
        regression = f"tmp_path = target.parent / (target.name + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "state.py", regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2
        assert "state.py" in result.stdout
        assert "literal .json.tmp" in result.stdout


class TestCheckerOutputFormat:
    def test_output_includes_file_and_line(self, tmp_path: Path) -> None:
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "heartbeat.py", regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2
        assert "heartbeat.py:" in result.stdout
        # Line number should appear after the colon.
        assert any(ch.isdigit() for ch in result.stdout.split("heartbeat.py:", 1)[1].split(":", 1)[0])


class TestCheckerExitCodes:
    def test_exits_1_for_invalid_repo_root(self) -> None:
        result = _run_checker("/nonexistent/path/that/does/not/exist")
        assert result.returncode == 1

    def test_exits_1_for_missing_guarded_file(self, tmp_path: Path) -> None:
        repo = _build_tmp_repo(tmp_path, omit="state.py")
        result = _run_checker(str(repo))
        assert result.returncode == 1
        assert "missing file" in (result.stdout + result.stderr).lower()

    def test_exits_2_for_violation(self, tmp_path: Path) -> None:
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "heartbeat.py", regression)
        result = _run_checker(str(repo))
        assert result.returncode == 2


class TestCheckerDoesNotFlagHelper:
    def test_atomic_write_helper_is_allowed(self) -> None:
        # Running the checker on the real repo already passes, which implies
        # atomic_write.py is allowed. This test makes that explicit.
        result = _run_checker()
        assert result.returncode == 0
        assert "atomic_write.py" not in result.stdout


class TestCheckerSafety:
    def test_no_network_calls_in_checker(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text

    def test_no_credential_loading_in_checker(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "load_dotenv" not in text
        assert "os.environ" not in text
        assert "environ[" not in text
        assert "getenv(" not in text


class TestExistingCAND009TestsStillPass:
    def test_cand009_safety_tests_pass(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/safety/test_atomic_write.py",
                "tests/safety/test_heartbeat.py",
                "tests/safety/test_deadman.py",
                "tests/safety/test_safety_state.py",
                "tests/safety/test_kill_switch_core.py",
                "-q",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
```

---

## 13. Companion lint/type hygiene plan

The companion cleanup is **optional and non-behavioral**. It fixes pre-existing ruff/mypy issues in CAND-009 touched files. It must not expand CAND-010 beyond the static guard.

### 13.1 Confirmed issues (as of planning HEAD)

Running `ruff check` and `mypy` on the relevant files reports:

```text
F841 Local variable `original_write_text` is assigned to but never used
   --> tests/safety/test_atomic_write.py:53:5
F841 Local variable `original_replace` is assigned to but never used
   --> tests/safety/test_atomic_write.py:70:5
F841 Local variable `original_replace` is assigned to but never used
   --> tests/safety/test_atomic_write.py:94:5
F821 Undefined name `Path`
   --> tests/safety/test_deadman.py:314:54
F821 Undefined name `Path`
   --> tests/safety/test_kill_switch_core.py:186:57

mypy: src/atlas_agent/safety/kill_switch.py:46: error: Item "None" of "datetime | None" has no attribute "isoformat"  [union-attr]
```

### 13.2 Proposed fixes

1. **`tests/safety/test_atomic_write.py`**
   - Remove the unused assignments to `original_write_text` (line 53) and `original_replace` (lines 70 and 94). Keep the monkeypatched functions; only the captured original references are unused.

2. **`tests/safety/test_deadman.py`**
   - Add `from pathlib import Path` at the top of the file to satisfy the type annotation `tmp_path: Path` on line 314.

3. **`tests/safety/test_kill_switch_core.py`**
   - Add `from pathlib import Path` at the top of the file to satisfy the type annotation `tmp_path: Path` on line 186.

4. **`src/atlas_agent/safety/kill_switch.py`**
   - Replace the inline `self.heartbeat_manager.last_heartbeat().isoformat()` with a narrowed local variable:
     ```python
     last_hb = self.heartbeat_manager.last_heartbeat()
     payload = {
         "last_heartbeat": last_hb.isoformat() if last_hb else None,
     }
     ```
   - This preserves runtime behavior and resolves the mypy `union-attr` error.

### 13.3 Boundaries

- These fixes are local hygiene only.
- They do not change runtime behavior, public APIs, or file formats.
- They do not enable live trading or any execution path.
- If any fix conflicts with another pending change, it may be deferred; the static guard does not depend on it.
- If `ruff`/`mypy` are unavailable in the implementation environment, do not guess; report the missing tool as a warning and skip the cleanup.

---

## 14. False-positive mitigation plan

The broad `+ ".tmp"` pattern is the primary false-positive risk. Mitigations:

1. **Scope to code-context lines only.** The broad pattern is only evaluated if the line contains one of:
   - `with_suffix`
   - `write_text`
   - `replace`
   - `Path(`
   - `tmp_path` / `temp_path`
   - `tmp =` / `temp =`

2. **Skip pure comment lines.** Lines whose first non-whitespace character is `#` are not evaluated for the broad pattern.

3. **Literal and `with_suffix` patterns remain strict.** Any literal `".json.tmp"` or `with_suffix(... + ".tmp")` is flagged even in comments because these describe the exact anti-pattern.

4. **Do not scan tests or docs with strict rules.** The checker default scope is the four guarded source files plus the helper file.

5. **If broad pattern proves noisy during implementation review, demote to warning.** The plan prefers a hard error, but the design doc allows demotion to warning if the signal-to-noise ratio is unacceptable. Any demotion must be documented and reviewed.

---

## 15. Verification matrix

### Phase 0 — Baseline verification (already run during planning)

```bash
git status --short
git rev-parse HEAD
git tag --points-at HEAD
git tag --list 'v0.6.18*'
git ls-remote --tags origin 'v0.6.18*'
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
atlas validate
atlas run --mode live
git diff --check
```

Expected:

- Clean tree.
- HEAD is `e3915b8180cdb643b95e1a697f6896e918a70dc3`.
- `v0.6.17` tag points at HEAD.
- No local or remote `v0.6.18*` tag.
- All scripts exit 0.
- `atlas run --mode live` exits 2.

### Phase 1 — Implementation acceptance

After CAND-010 is implemented, run:

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 scripts/check_safety_atomic_write.py
python3.11 -m pytest tests/test_check_safety_atomic_write.py -q
python3.11 -m pytest tests/safety/test_atomic_write.py tests/safety/test_heartbeat.py tests/safety/test_deadman.py tests/safety/test_safety_state.py tests/safety/test_kill_switch*.py -q
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

If companion cleanup is applied:

```bash
ruff check src/atlas_agent/safety/atomic_write.py src/atlas_agent/safety/heartbeat.py src/atlas_agent/safety/deadman.py src/atlas_agent/safety/kill_switch.py src/atlas_agent/safety/state.py tests/safety/test_atomic_write.py tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py
mypy src/atlas_agent/safety/atomic_write.py src/atlas_agent/safety/heartbeat.py src/atlas_agent/safety/deadman.py src/atlas_agent/safety/kill_switch.py src/atlas_agent/safety/state.py
```

Optional:

```bash
python3.11 -m pytest -q --durations=25
bash scripts/release_check.sh
```

Expected:

- All commands exit 0 except `atlas run --mode live`, which must exit 2.
- `scripts/check_safety_atomic_write.py` prints `PASSED`.
- `ruff check` and `mypy` report no new issues.
- No live readiness or trading safety claim appears in output.

---

## 16. Rollback plan

If CAND-010 causes regressions:

1. Remove `scripts/check_safety_atomic_write.py`.
2. Remove `tests/test_check_safety_atomic_write.py`.
3. Revert the integration lines added to `scripts/dev_check.sh` (and `scripts/ci_check.sh` if applicable).
4. Revert the companion cleanup changes if they caused the regression.
5. Revert any docs/changelog updates related to CAND-010.
6. Re-run the verification matrix.

The system returns to the CAND-009 state, which remains fail-closed.

---

## 17. Commit plan

For the planning task only, commit the implementation plan document:

```bash
git add docs/safety-state-persistence-regression-guard-implementation-plan.md
git commit -m "docs(cand-010): add safety-state regression guard implementation plan"
git push origin main
```

Do not commit implementation code.

For the future implementation phase, suggest these small commits:

```text
feat(cand-010): add safety-state atomic-write regression guard checker
test(cand-010): cover regression guard pass/fail/output cases
chore(cand-010): integrate regression guard into dev check
chore(cand-010): optionally integrate regression guard into ci check
docs(cand-010): correct design baseline HEAD and update status
chore(cand-010): optional lint/type hygiene cleanup
chore(changelog): record CAND-010 under Unreleased
```

---

## 18. Acceptance criteria

- [ ] `docs/safety-state-persistence-regression-guard-implementation-plan.md` exists and contains all 19 required sections.
- [ ] `scripts/check_safety_atomic_write.py` is implemented and uses stdlib only (`pathlib`, `re`, `sys`, `argparse`).
- [ ] The checker scans the four guarded modules and exits non-zero on any disallowed fixed `<target>.tmp` pattern.
- [ ] The checker permits `.tmp` construction inside `atomic_write.py`.
- [ ] The checker accepts a positional repo root or `--repo-root`.
- [ ] The checker documents and uses exit codes `0` clean, `1` internal error, `2` violation.
- [ ] The checker integrates into `scripts/release_check.sh --quick` (via `scripts/dev_check.sh`).
- [ ] `tests/test_check_safety_atomic_write.py` covers pass, fail, output format, and exit-code cases.
- [ ] Existing CAND-009 safety tests still pass.
- [ ] `atlas run --mode live` still exits 2.
- [ ] All verification matrix commands pass (with the expected live-mode failure).
- [ ] No live trading, live submit, broker/provider execution, credential loading, or order placement is introduced.
- [ ] Only the design doc, the new checker, the new checker test, the dev check integration, optional CI check integration, optional companion cleanup, and changelog entry are modified. No release metadata, version, tag, or changelog release-date changes are made during planning.

---

## 19. Implementation prompt readiness

This plan is ready for an implementer agent. Each task below contains:

- Exact file paths.
- Complete code or diff snippets.
- Exact test commands and expected outcomes.
- Exact commit commands and messages.

The implementer must not deviate from the safety invariants in Section 6.

---

## 20. Task-by-task execution plan

### Task 1: Create the checker script

**Files:**
- Create: `scripts/check_safety_atomic_write.py`
- Test: `tests/test_check_safety_atomic_write.py` (created in Task 2)

- [ ] **Step 1: Write the checker module**

Create `scripts/check_safety_atomic_write.py` with the code from Section 10.3.

- [ ] **Step 2: Make it executable**

Run:

```bash
chmod +x scripts/check_safety_atomic_write.py
```

- [ ] **Step 3: Run the checker on the current repo**

Run:

```bash
python3.11 scripts/check_safety_atomic_write.py
```

Expected: exit 0 and print `Safety atomic-write regression check PASSED`.

- [ ] **Step 4: Verify exit codes manually**

Run:

```bash
python3.11 scripts/check_safety_atomic_write.py /nonexistent; echo "EXIT=$?"
```

Expected: `EXIT=1`.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_safety_atomic_write.py
git commit -m "feat(cand-010): add safety-state atomic-write regression guard checker"
```

---

### Task 2: Create the checker tests

**Files:**
- Create: `tests/test_check_safety_atomic_write.py`

- [ ] **Step 1: Write the test module**

Create `tests/test_check_safety_atomic_write.py` with the code from Section 12.3.

- [ ] **Step 2: Run the tests**

Run:

```bash
python3.11 -m pytest tests/test_check_safety_atomic_write.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_check_safety_atomic_write.py
git commit -m "test(cand-010): cover regression guard pass/fail/output cases"
```

---

### Task 3: Integrate into dev check

**Files:**
- Modify: `scripts/dev_check.sh`

- [ ] **Step 1: Add checker invocation after step 4a**

Insert the block from Section 11.1 into `scripts/dev_check.sh`.

- [ ] **Step 2: Run dev check (or at least the new step)**

Run:

```bash
python3.11 scripts/check_safety_atomic_write.py
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/dev_check.sh
git commit -m "chore(cand-010): integrate regression guard into dev check"
```

---

### Task 4: Optionally integrate into CI check

**Files:**
- Modify: `scripts/ci_check.sh`

- [ ] **Step 1: Add checker invocation near other static checks**

Insert the block from Section 11.2 into `scripts/ci_check.sh`.

- [ ] **Step 2: Commit**

```bash
git add scripts/ci_check.sh
git commit -m "chore(cand-010): integrate regression guard into ci check"
```

---

### Task 5: Update the design doc

**Files:**
- Modify: `docs/safety-state-persistence-regression-guard-design.md`

- [ ] **Step 1: Correct Section 2 baseline HEAD**

Change:

```text
- Design HEAD: `3cffef98f0fdab0cf248193de19d4295321eba4a`
```

to:

```text
- Design HEAD: `e3915b8180cdb643b95e1a697f6896e918a70dc3`
```

Also update the Phase 0 expected HEAD in Section 17 from `3cffef98f0fdab0cf248193de19d4295321eba4a` to `e3915b8180cdb643b95e1a697f6896e918a70dc3`.

- [ ] **Step 2: Update status**

Change:

```text
**Status:** design-only
```

to:

```text
**Status:** design accepted; implementation planned
```

- [ ] **Step 3: Commit**

```bash
git add docs/safety-state-persistence-regression-guard-design.md
git commit -m "docs(cand-010): correct design baseline HEAD and update status"
```

---

### Task 6: Optional companion lint/type hygiene cleanup

**Files:**
- Modify: `tests/safety/test_atomic_write.py`
- Modify: `tests/safety/test_deadman.py`
- Modify: `tests/safety/test_kill_switch_core.py`
- Modify: `src/atlas_agent/safety/kill_switch.py`

- [ ] **Step 1: Apply the four cleanup changes from Section 13.2**

- Remove unused `original_write_text` and `original_replace` assignments in `tests/safety/test_atomic_write.py`.
- Add `from pathlib import Path` to `tests/safety/test_deadman.py`.
- Add `from pathlib import Path` to `tests/safety/test_kill_switch_core.py`.
- Narrow `last_heartbeat()` call in `src/atlas_agent/safety/kill_switch.py` line 46.

- [ ] **Step 2: Run ruff and mypy**

Run:

```bash
ruff check src/atlas_agent/safety/atomic_write.py src/atlas_agent/safety/heartbeat.py src/atlas_agent/safety/deadman.py src/atlas_agent/safety/kill_switch.py src/atlas_agent/safety/state.py tests/safety/test_atomic_write.py tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py
mypy src/atlas_agent/safety/atomic_write.py src/atlas_agent/safety/heartbeat.py src/atlas_agent/safety/deadman.py src/atlas_agent/safety/kill_switch.py src/atlas_agent/safety/state.py
```

Expected: no issues in the modified files.

- [ ] **Step 3: Run affected tests**

Run:

```bash
python3.11 -m pytest tests/safety/test_atomic_write.py tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py tests/safety/test_safety_state.py tests/safety/test_heartbeat.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/safety/test_atomic_write.py tests/safety/test_deadman.py tests/safety/test_kill_switch_core.py src/atlas_agent/safety/kill_switch.py
git commit -m "chore(cand-010): optional lint/type hygiene cleanup"
```

---

### Task 7: Update changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CAND-010 entry under `[Unreleased]`**

Insert under `## [Unreleased]`:

```markdown
### Added
- CAND-010: Safety-State Persistence Regression Guard. Added `scripts/check_safety_atomic_write.py` and `tests/test_check_safety_atomic_write.py` to prevent reintroduction of fixed `<target>.tmp` writes in safety persistence modules. Integrated into `scripts/dev_check.sh` and optionally `scripts/ci_check.sh`.

### Safety
- No live trading, live submit, broker/provider execution, credential loading, or order placement introduced.
- `atlas run --mode live` remains fail-closed.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore(changelog): record CAND-010 under Unreleased"
```

---

### Task 8: Final verification

Run the full Phase 1 verification matrix from Section 15.

Expected: all commands exit 0 except `atlas run --mode live`, which exits 2.

---

## Self-review checklist

1. **Spec coverage:** Every design-doc section is addressed by a task or explicit plan note.
2. **Placeholder scan:** No `TBD`, `TODO`, `implement later`, or vague descriptions remain.
3. **Type consistency:** `repo_root` is consistently `Path`; exit codes are consistently documented as 0/1/2; file paths match the guarded list.
4. **Safety boundaries:** No live trading, live submit, broker/provider calls, credential loading, or order placement is introduced.
