# CAND-006 Implementation Plan: Optional Release Assurance Bundle Integration for Reviewer Trust Snapshot

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `--include-reviewer-trust-snapshot` flag to `scripts/release_assurance.py` that builds and validates a reviewer trust snapshot inside the assurance output directory, plus supporting checker, tests, workflow input, docs, and gate integration.

**Architecture:** Keep the change surgical: add one CLI flag to the existing release assurance script, conditionally call the existing snapshot builder/checker, add a static integration checker, add focused pytest coverage, extend the manual workflow with a boolean input, and update docs/gates. No protected runtime boundaries are touched.

**Tech Stack:** Python 3.11, pytest, argparse, pathlib, subprocess, GitHub Actions YAML.

---

### Task 1: Add `--include-reviewer-trust-snapshot` flag to `scripts/release_assurance.py`

**Files:**
- Modify: `scripts/release_assurance.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_release_assurance_snapshot_integration.py`:

```python
def test_release_assurance_help_includes_snapshot_flag():
    text = Path("scripts/release_assurance.py").read_text(encoding="utf-8")
    assert "--include-reviewer-trust-snapshot" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py::test_release_assurance_help_includes_snapshot_flag -v`

Expected: FAIL

- [ ] **Step 3: Add the argument and conditional builder/checker call**

In `scripts/release_assurance.py`:

```python
parser.add_argument(
    "--include-reviewer-trust-snapshot",
    action="store_true",
    help="Include a deterministic reviewer trust snapshot in the assurance output.",
)
```

After the assurance pack is written and `valid` is computed, conditionally:

```python
if args.include_reviewer_trust_snapshot:
    import build_reviewer_trust_snapshot
    import check_reviewer_trust_snapshot
    snapshot_dir = out_dir / "reviewer-trust-snapshot"
    build_reviewer_trust_snapshot.build_snapshot(snapshot_dir, deterministic=True)
    check_result = check_reviewer_trust_snapshot.run_checks(snapshot_dir)
    summary["reviewer_trust_snapshot_included"] = check_result["passed"]
    if not check_result["passed"]:
        valid = False
        findings.extend(
            f"Reviewer trust snapshot: {e}" for e in check_result["errors"]
        )
    # Rewrite summary JSON so the new key is persisted.
    (out_dir / "release-assurance-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py::test_release_assurance_help_includes_snapshot_flag -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/release_assurance.py tests/test_release_assurance_snapshot_integration.py
git commit -m "feat: add --include-reviewer-trust-snapshot flag to release_assurance.py"
```

---

### Task 2: Add focused tests for default and opt-in behavior

**Files:**
- Create: `tests/test_release_assurance_snapshot_integration.py`

- [ ] **Step 1: Write failing tests**

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE = REPO_ROOT / "scripts" / "release_assurance.py"


def _run_release_assurance(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RELEASE_ASSURANCE), "--version", "v0.6.11", "--output", str(tmp_path), *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_default_release_assurance_does_not_include_reviewer_snapshot(tmp_path):
    result = _run_release_assurance(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "reviewer-trust-snapshot").exists()
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert "reviewer_trust_snapshot_included" not in summary


def test_opt_in_release_assurance_includes_valid_reviewer_snapshot(tmp_path):
    result = _run_release_assurance(tmp_path, "--include-reviewer-trust-snapshot")
    assert result.returncode == 0, result.stderr
    snapshot_dir = tmp_path / "reviewer-trust-snapshot"
    assert snapshot_dir.exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.json").exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.md").exists()
    assert (snapshot_dir / "checksums.sha256").exists()
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary.get("reviewer_trust_snapshot_included") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -v`

Expected: FAIL (snapshot dir missing, summary key missing)

- [ ] **Step 3: Implement minimal code to pass**

The code added in Task 1 should make these pass. Ensure deterministic mode is used.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_release_assurance_snapshot_integration.py
git commit -m "test: default and opt-in release assurance snapshot integration"
```

---

### Task 3: Add `scripts/check_release_assurance_snapshot_integration.py`

**Files:**
- Create: `scripts/check_release_assurance_snapshot_integration.py`

- [ ] **Step 1: Write failing test**

```python
def test_checker_runs_and_passes_on_real_repo():
    result = subprocess.run(
        [sys.executable, "scripts/check_release_assurance_snapshot_integration.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py::test_checker_runs_and_passes_on_real_repo -v`

Expected: FAIL (script does not exist)

- [ ] **Step 3: Implement the checker**

```python
#!/usr/bin/env python3
"""Validate the release-assurance/reviewer-snapshot integration contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE = REPO_ROOT / "scripts" / "release_assurance.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-assurance.yml"
BUILDER = REPO_ROOT / "scripts" / "build_reviewer_trust_snapshot.py"
CHECKER = REPO_ROOT / "scripts" / "check_reviewer_trust_snapshot.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_flag_present(text: str) -> list[str]:
    if "--include-reviewer-trust-snapshot" not in text:
        return ["release_assurance.py does not define --include-reviewer-trust-snapshot"]
    return []


def _check_default_unchanged(text: str) -> list[str]:
    if "if args.include_reviewer_trust_snapshot:" not in text:
        return ["release_assurance.py does not conditionally invoke the snapshot builder"]
    return []


def _check_no_unsafe_commands(text: str) -> list[str]:
    violations: list[str] = []
    unsafe = [
        (r"git\s+push", "git push"),
        (r"git\s+tag\s+[^-]", "git tag creation"),
        (r"gh\s+release\s+create", "gh release create"),
        (r"gh\s+release\s+upload", "gh release upload"),
        (r"twine\s+upload", "twine upload"),
        (r"python\s+-m\s+twine\s+upload", "twine upload"),
    ]
    for pattern, label in unsafe:
        if re.search(pattern, text):
            violations.append(f"Unsafe command detected: {label}")
    return violations


def _check_workflow_safe(path: Path) -> list[str]:
    if not path.exists():
        return [f"Workflow file missing: {path}"]
    text = _read_text(path)
    violations: list[str] = []
    if "workflow_dispatch" not in text:
        violations.append("release-assurance.yml is not manually triggered")
    if "contents: write" in text or "contents: read" not in text:
        violations.append("release-assurance.yml must use contents: read only")
    if re.search(r"secrets\.", text):
        violations.append("release-assurance.yml references secrets")
    return violations


def _check_builder_checker_reused() -> list[str]:
    violations: list[str] = []
    if not BUILDER.exists():
        violations.append("build_reviewer_trust_snapshot.py is missing")
    if not CHECKER.exists():
        violations.append("check_reviewer_trust_snapshot.py is missing")
    return violations


def run_checks(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root or REPO_ROOT
    errors: list[str] = []
    warnings: list[str] = []

    text = _read_text(RELEASE_ASSURANCE)
    errors.extend(_check_flag_present(text))
    errors.extend(_check_default_unchanged(text))
    errors.extend(_check_no_unsafe_commands(text))
    errors.extend(_check_workflow_safe(WORKFLOW))
    errors.extend(_check_builder_checker_reused())

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release assurance snapshot integration.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root.")
    args = parser.parse_args()

    result = run_checks(args.repo_root)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1

    if result["passed"]:
        print("Release assurance snapshot integration check PASSED")
    else:
        print("Release assurance snapshot integration check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py::test_checker_runs_and_passes_on_real_repo -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/check_release_assurance_snapshot_integration.py tests/test_release_assurance_snapshot_integration.py
git commit -m "feat: add release assurance snapshot integration checker"
```

---

### Task 4: Extend `.github/workflows/release-assurance.yml`

**Files:**
- Modify: `.github/workflows/release-assurance.yml`

- [ ] **Step 1: Add boolean input and conditional flag**

```yaml
on:
  workflow_dispatch:
    inputs:
      release:
        description: "Release tag to verify"
        required: true
        default: "v0.6.11"
      include_reviewer_trust_snapshot:
        description: "Include a reviewer trust snapshot in the assurance output"
        type: boolean
        required: false
        default: false
```

And in the generate step:

```yaml
      - name: Generate release assurance pack
        run: |
          python scripts/release_assurance.py \
            --version "${RELEASE_TAG}" \
            --output "artifacts/release_assurance/${RELEASE_TAG}-ci" \
            ${{ inputs.include_reviewer_trust_snapshot && '--include-reviewer-trust-snapshot' || '' }}
```

- [ ] **Step 2: Run workflow checker**

Run: `python3.11 scripts/check_release_assurance_snapshot_integration.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-assurance.yml
git commit -m "ci: add optional include_reviewer_trust_snapshot input to release assurance workflow"
```

---

### Task 5: Add more checker tests

**Files:**
- Modify: `tests/test_release_assurance_snapshot_integration.py`

- [ ] **Step 1: Add tests for checker failure modes**

- Missing flag in mocked release_assurance.py fails checker.
- Unsafe workflow secret usage fails checker.
- `gh release create` in release_assurance.py fails checker.
- Missing builder/checker files fails checker.

- [ ] **Step 2: Run tests**

Run: `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_release_assurance_snapshot_integration.py
git commit -m "test: checker failure modes for release assurance snapshot integration"
```

---

### Task 6: Update docs minimally

**Files:**
- Modify: `docs/trust/reviewer-trust-snapshot.md`
- Modify: `docs/security/release-readiness.md`
- Modify: `docs/trust/README.md`
- Modify: `docs/reviewer-checklist.md`

- [ ] **Step 1: Add opt-in integration section to each doc**

For `docs/trust/reviewer-trust-snapshot.md`, add:

```markdown
## Include in a release assurance pack

The reviewer trust snapshot can be included in the local release assurance output:

```bash
python scripts/release_assurance.py \
  --version v0.6.11 \
  --output artifacts/release_assurance/v0.6.11-local \
  --include-reviewer-trust-snapshot
```

This is optional and off by default. It produces `<output>/reviewer-trust-snapshot/`
with the same files as a standalone snapshot build, then validates them. It does not
create tags, releases, or PyPI packages, and does not call providers, brokers, or
enable live trading.
```

Update the other docs similarly, keeping language consistent with the no-claims policy.

- [ ] **Step 2: Run docs checkers**

Run:
- `python3.11 scripts/check_public_docs_consistency.py`
- `python3.11 scripts/check_forbidden_claims.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/trust/reviewer-trust-snapshot.md docs/security/release-readiness.md docs/trust/README.md docs/reviewer-checklist.md
git commit -m "docs: document optional reviewer snapshot in release assurance"
```

---

### Task 7: Integrate into gates

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add checker and pytest to shell gates**

In `scripts/dev_check.sh` after the docs archive hygiene tests (around section 13i):

```bash
echo ""
echo "13j. release assurance snapshot integration check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_snapshot_integration.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13k. release assurance snapshot integration tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_snapshot_integration.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Do the equivalent in `scripts/ci_check.sh` (rename section numbers to follow existing 8h):

```bash
echo ""
echo "8i. release assurance snapshot integration check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_snapshot_integration.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8j. release assurance snapshot integration tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_snapshot_integration.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

- [ ] **Step 2: Add to `.github/workflows/ci.yml`**

Locate the existing reviewer trust snapshot steps and add the new checker/test step after them:

```yaml
      - name: Release assurance snapshot integration check
        run: python scripts/check_release_assurance_snapshot_integration.py

      - name: Release assurance snapshot integration tests
        run: python -m pytest tests/test_release_assurance_snapshot_integration.py -q
```

- [ ] **Step 3: Run affected gates**

Run: `./scripts/dev_check.sh` and `./scripts/ci_check.sh`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/dev_check.sh scripts/ci_check.sh .github/workflows/ci.yml
git commit -m "ci: integrate release assurance snapshot checker/tests into gates"
```

---

### Task 8: Final validation

- [ ] Run `./scripts/dev_check.sh`
- [ ] Run `./scripts/ci_check.sh`
- [ ] Run `./scripts/release_check.sh --quick`
- [ ] Run `python3.11 scripts/check_release_assurance_snapshot_integration.py --json`
- [ ] Run `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -q`
- [ ] Run `git diff --check`
- [ ] Stage explicit files, commit, and push to origin/main.

---

## Self-review

**Spec coverage:**
- Opt-in flag: Task 1.
- Default unchanged: Tasks 1 and 2.
- Workflow input: Task 4.
- Checker: Task 3.
- Tests: Tasks 2, 3, 5.
- Docs: Task 6.
- Gate integration: Task 7.

**Placeholder scan:** No TBD/TODO placeholders remain.

**Type consistency:** `--include-reviewer-trust-snapshot` flag name is consistent across CLI, tests, checker, and workflow.
