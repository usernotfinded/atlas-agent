# CAND-012 Release Assurance Diagnostics Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `--diagnostics-json` output of `scripts/release_assurance.py` into the manual GitHub Actions workflow as an opt-in downloadable artifact, with checker/tests/docs/gate integration.

**Architecture:** Add a boolean `upload_diagnostics_json` input to `.github/workflows/release-assurance.yml`, capture the release-assurance exit code in a shell step, optionally pass `--diagnostics-json`, upload the file on failure, then re-emit the captured exit code. Add a static checker and pytest suite to enforce the workflow shape, then integrate into dev/CI gates and docs.

**Tech Stack:** GitHub Actions YAML, Python 3.11, pytest, `actions/upload-artifact@v6`.

---

## File map

| File | Responsibility |
|------|----------------|
| `.github/workflows/release-assurance.yml` | Add opt-in input, conditional diagnostics flag, captured exit code, diagnostics artifact upload, preserved failure conclusion. |
| `scripts/check_release_assurance_diagnostics_workflow.py` | Static checker for workflow input, conditional flag, upload semantics, failure semantics, permissions, secrets, safety. |
| `tests/test_release_assurance_diagnostics_workflow.py` | pytest coverage for checker pass/fail cases. |
| `docs/security/release-assurance-diagnostics.md` | Document workflow input and artifact download. |
| `docs/security/release-assurance-workflow-dispatch.md` | Add input to dispatch examples and download instructions. |
| `docs/security/release-readiness.md` | Add optional diagnostics artifact section. |
| `docs/reviewer-checklist.md` | Minimal cross-link. |
| `docs/public-launch-readiness.md` | Minimal cross-link. |
| `scripts/dev_check.sh` | Add diagnostics workflow check + tests. |
| `scripts/ci_check.sh` | Add diagnostics workflow check + tests. |
| `.github/workflows/ci.yml` | Add diagnostics workflow check + tests. |

---

### Task 1: Add workflow input and conditional diagnostics flag

**Files:**
- Modify: `.github/workflows/release-assurance.yml:20-24`
- Modify: `.github/workflows/release-assurance.yml:66-79`

- [ ] **Step 1: Add `upload_diagnostics_json` input**

Insert after `bundle_demo_version:`:

```yaml
      upload_diagnostics_json:
        description: "Upload a redacted release-assurance diagnostics JSON artifact on failure"
        type: boolean
        required: false
        default: false
```

- [ ] **Step 2: Replace the unconditional release-assurance step with a capturing step**

Replace the `Generate release assurance pack` step with:

```yaml
      - name: Generate release assurance pack
        id: release_assurance
        shell: bash
        run: |
          mkdir -p artifacts/release_assurance_diagnostics
          diagnostics_flag="${{ inputs.upload_diagnostics_json && '--diagnostics-json artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json' || '' }}"
          set +e
          python scripts/release_assurance.py \
            --version "${RELEASE_TAG}" \
            --output "artifacts/release_assurance/${RELEASE_TAG}-ci" \
            ${{ inputs.include_reviewer_trust_snapshot && '--include-reviewer-trust-snapshot' || '' }} \
            ${diagnostics_flag}
          exit_code=$?
          set -e
          echo "exit_code=${exit_code}" >> "${GITHUB_OUTPUT}"
          if [[ "${exit_code}" -ne 0 ]]; then
            echo "::warning::Release assurance pack generation failed (exit ${exit_code})."
          fi
          exit 0
```

- [ ] **Step 3: Make the main artifact upload success-only**

Add `if: steps.release_assurance.outputs.exit_code == '0'` to the existing `Upload release assurance artifact` step.

---

### Task 2: Add diagnostics upload and preserve failure semantics

**Files:**
- Modify: `.github/workflows/release-assurance.yml:80-103`

- [ ] **Step 1: Add diagnostics artifact upload step**

After the main `Upload release assurance artifact` step, add:

```yaml
      - name: Upload release assurance diagnostics artifact
        if: always() && inputs.upload_diagnostics_json && steps.release_assurance.outputs.exit_code != '0'
        uses: actions/upload-artifact@v6
        with:
          name: release-assurance-diagnostics
          path: artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json
          if-no-files-found: ignore
          retention-days: 14
```

- [ ] **Step 2: Make bundle demo steps conditional on success**

Change each bundle demo step's `if:` from `inputs.run_bundle_demo` to:

```yaml
        if: ${{ inputs.run_bundle_demo && steps.release_assurance.outputs.exit_code == '0' }}
```

Affected steps: `Run release assurance bundle demo`, `Validate release assurance bundle manifest`, `Upload release assurance bundle demo artifact`.

- [ ] **Step 3: Add final failure-restore step**

At the end of the job, add:

```yaml
      - name: Fail if release assurance failed
        if: steps.release_assurance.outputs.exit_code != '0'
        run: |
          echo "Release assurance failed with exit code ${{ steps.release_assurance.outputs.exit_code }}"
          exit ${{ steps.release_assurance.outputs.exit_code }}
```

---

### Task 3: Add static workflow checker

**Files:**
- Create: `scripts/check_release_assurance_diagnostics_workflow.py`

- [ ] **Step 1: Create checker with the following structure**

Use the same style as `scripts/check_release_assurance_bundle_workflow.py`.

Key functions:

```python
def _check_diagnostics_input(text: str) -> list[str]:
    errors: list[str] = []
    if "upload_diagnostics_json:" not in text:
        errors.append("Workflow must declare upload_diagnostics_json input")
        return errors
    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("upload_diagnostics_json:"):
            start_idx = i
            break
    if start_idx is None:
        errors.append("Could not locate upload_diagnostics_json input block")
        return errors
    start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    block_lines: list[str] = []
    for line in lines[start_idx + 1:]:
        if line.strip() == "":
            block_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= start_indent:
            break
        block_lines.append(line)
    block = "\n".join(block_lines)
    if "type: boolean" not in block:
        errors.append("upload_diagnostics_json input must be type boolean")
    if "default: false" not in block:
        errors.append("upload_diagnostics_json input must default to false")
    return errors


def _check_diagnostics_flag_conditional(text: str) -> list[str]:
    errors: list[str] = []
    if "--diagnostics-json" not in text:
        errors.append("Workflow must pass --diagnostics-json when diagnostics are enabled")
        return errors
    for i, line in enumerate(text.splitlines(), start=1):
        if "--diagnostics-json" in line:
            if "inputs.upload_diagnostics_json" not in line and "diagnostics_flag" not in line:
                errors.append(
                    f"Line {i}: --diagnostics-json must be conditional on inputs.upload_diagnostics_json"
                )
    return errors


def _step_has_if(text: str, step_name: str) -> bool:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if f"- name: {step_name}" in line:
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if next_line == "":
                    continue
                if next_line.startswith("- name:"):
                    break
                if next_line.startswith("if:"):
                    return True
            break
    return False


def _check_diagnostics_upload_step(text: str) -> list[str]:
    errors: list[str] = []
    if "release-assurance-diagnostics" not in text:
        errors.append("Workflow must upload an artifact named 'release-assurance-diagnostics'")
        return errors
    if not _step_has_if(text, "Upload release assurance diagnostics artifact"):
        errors.append("Diagnostics artifact upload step must be conditional")
    if "if-no-files-found: ignore" not in text:
        errors.append("Diagnostics artifact upload must use if-no-files-found: ignore")
    return errors


def _check_failure_semantics(text: str) -> list[str]:
    errors: list[str] = []
    if "exit_code" not in text:
        errors.append("Workflow must capture release_assurance.py exit_code")
    if "GITHUB_OUTPUT" not in text:
        errors.append("Workflow must write exit_code to GITHUB_OUTPUT")
    if not _step_has_if(text, "Fail if release assurance failed"):
        errors.append("Workflow must have a final step that re-emits the captured exit code on failure")
    return errors
```

Also include the safety checks from `check_release_assurance_bundle_workflow.py`:

```python
REQUIRED_ENV_SNIPPETS = [
    'ENABLE_LIVE_TRADING: "false"',
    'PROVIDER_EXECUTION_ENABLED: "false"',
    'BROKER_EXECUTION_ENABLED: "false"',
]

FORBIDDEN_COMMANDS = [
    "git push",
    "git tag",
    "git commit",
    "gh release create",
    "gh release upload",
    "twine" + " upload",
    "twine" + " publish",
]

SAFE_TOKEN_PATTERN = re.compile(
    r"\$\{\{\s*(?:github\.token|secrets\.GITHUB_TOKEN)\s*\}\}",
    re.IGNORECASE,
)
```

Expose `check_workflow(workflow_path=None) -> dict[str, Any]` and a `main()` with `--json` support.

- [ ] **Step 2: Run checker on real workflow**

```bash
python3.11 scripts/check_release_assurance_diagnostics_workflow.py
```

Expected: `Release assurance diagnostics workflow check PASSED`

---

### Task 4: Add tests for the workflow checker

**Files:**
- Create: `tests/test_release_assurance_diagnostics_workflow.py`

- [ ] **Step 1: Create tests**

```python
"""Tests for the release-assurance diagnostics workflow checker (CAND-012)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_release_assurance_diagnostics_workflow import check_workflow

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-assurance.yml"


def test_real_workflow_passes() -> None:
    result = check_workflow(WORKFLOW_PATH)
    assert result["passed"], f"Expected workflow to pass, got: {result['errors']}"


def test_checker_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_release_assurance_diagnostics_workflow.py"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert "summary" in data


def test_checker_fails_if_input_defaults_true(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace("default: false", "default: true")
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("default" in e.lower() for e in result["errors"])


def test_checker_fails_if_diagnostics_flag_unconditional(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace("${diagnostics_flag}", "--diagnostics-json artifacts/x.json")
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("conditional" in e.lower() for e in result["errors"])


def test_checker_fails_if_upload_unconditional(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "if: always() && inputs.upload_diagnostics_json && steps.release_assurance.outputs.exit_code != '0'",
        "if: always()",
    )
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("conditional" in e.lower() for e in result["errors"])


def test_checker_fails_if_arbitrary_secret(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "GH_TOKEN: ${{ github.token }}",
        "GH_TOKEN: ${{ secrets.MY_TOKEN }}",
    )
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("secret" in e.lower() for e in result["errors"])


def test_checker_fails_if_contents_write(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace("contents: read", "contents: write")
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("contents" in e.lower() for e in result["errors"])


def test_checker_fails_if_release_command(tmp_path: Path) -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "python scripts/release_assurance.py",
        "python scripts/release_assurance.py\n          gh release create v0.6.12",
    )
    fake = tmp_path / "release-assurance.yml"
    fake.write_text(text, encoding="utf-8")
    result = check_workflow(fake)
    assert not result["passed"]
    assert any("release create" in e.lower() for e in result["errors"])
```

- [ ] **Step 2: Run new tests**

```bash
python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q
```

Expected: all tests pass.

---

### Task 5: Update documentation

**Files:**
- Modify: `docs/security/release-assurance-diagnostics.md`
- Modify: `docs/security/release-assurance-workflow-dispatch.md`
- Modify: `docs/security/release-readiness.md`
- Modify: `docs/reviewer-checklist.md`
- Modify: `docs/public-launch-readiness.md`

- [ ] **Step 1: `release-assurance-diagnostics.md`**

Add a "Workflow diagnostics artifact" section before "How to debug workflow failures":

```markdown
## Workflow diagnostics artifact

The manual Release Assurance workflow (`.github/workflows/release-assurance.yml`)
has an opt-in input, `upload_diagnostics_json` (default `false`). When set to `true`,
if `release_assurance.py` fails, the workflow uploads the redacted diagnostics JSON
as a `release-assurance-diagnostics` artifact.

Dispatch with diagnostics upload:

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.6.11 \
  --field upload_diagnostics_json=true
```

Download the artifact after the run:

```bash
gh run download <run-id> --name release-assurance-diagnostics --dir ./diagnostics
```

The artifact only appears when the workflow fails and diagnostics are enabled.
If the workflow succeeds, no diagnostics file is created and the upload step is skipped.
The workflow still fails after uploading the diagnostics artifact.
```

- [ ] **Step 2: `release-assurance-workflow-dispatch.md`**

Add `upload_diagnostics_json` to the safe input values and CLI examples. Add a download command for `release-assurance-diagnostics`.

- [ ] **Step 3: `release-readiness.md`**

Add a subsection under `### Optional release assurance bundle demo` describing `upload_diagnostics_json` and the failure-only artifact.

- [ ] **Step 4: Cross-links**

Add one sentence to `docs/reviewer-checklist.md` and `docs/public-launch-readiness.md` referencing the new workflow input and checker.

---

### Task 6: Integrate into gates

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: `scripts/dev_check.sh`**

After `13r. release assurance diagnostics tests`, add:

```bash
echo ""
echo "13s. release assurance diagnostics workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13t. release assurance diagnostics workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

- [ ] **Step 2: `scripts/ci_check.sh`**

After `8o. release assurance diagnostics tests`, add:

```bash
echo ""
echo "8r. release assurance diagnostics workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8s. release assurance diagnostics workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

- [ ] **Step 3: `.github/workflows/ci.yml`**

After the `Release assurance diagnostics tests` step, add:

```yaml
      - name: Release assurance diagnostics workflow check
        run: python3.11 scripts/check_release_assurance_diagnostics_workflow.py
      - name: Release assurance diagnostics workflow tests
        run: python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q
```

---

### Task 7: Local validation

- [ ] **Step 1: Focused checks**

```bash
python3.11 scripts/check_release_assurance_diagnostics.py
python3.11 scripts/check_release_assurance_bundle_workflow.py
python3.11 scripts/check_release_assurance_diagnostics_workflow.py
python3.11 scripts/check_release_assurance_snapshot_integration.py
python3.11 -m pytest tests/test_release_assurance_diagnostics.py -q
python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q
```

All must exit 0.

- [ ] **Step 2: Full gates**

```bash
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

All must pass.

---

### Task 8: Commit, push, verify CI, optional dispatch

- [ ] **Step 1: Stage explicit files and commit**

```bash
git add .github/workflows/release-assurance.yml \
        .github/workflows/ci.yml \
        scripts/check_release_assurance_diagnostics_workflow.py \
        tests/test_release_assurance_diagnostics_workflow.py \
        docs/security/release-assurance-diagnostics.md \
        docs/security/release-assurance-workflow-dispatch.md \
        docs/security/release-readiness.md \
        docs/reviewer-checklist.md \
        docs/public-launch-readiness.md \
        scripts/dev_check.sh \
        scripts/ci_check.sh \
        docs/superpowers/specs/2026-06-16-cand-012-release-assurance-diagnostics-artifact-design.md \
        docs/superpowers/plans/2026-06-16-cand-012-release-assurance-diagnostics-artifact-plan.md
git commit -m "ci: add optional release assurance diagnostics artifact (CAND-012)"
```

- [ ] **Step 2: Push to origin/main**

```bash
git push origin main
```

- [ ] **Step 3: Verify push-CI**

```bash
gh run list --repo usernotfinded/atlas-agent --branch main --limit 5
```

Wait for the run matching the pushed commit to conclude. Expected: `success`.

- [ ] **Step 4: Controlled failure dispatch (optional but requested)**

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.0.0-does-not-exist \
  --field include_reviewer_trust_snapshot=false \
  --field run_bundle_demo=false \
  --field bundle_demo_version=v0.6.11 \
  --field upload_diagnostics_json=true
```

After completion:

```bash
run_id=$(gh run list --workflow=release-assurance.yml --repo usernotfinded/atlas-agent --limit 1 --json databaseId -q '.[0].databaseId')
gh run download "$run_id" --name release-assurance-diagnostics --dir ./diagnostics
python3.11 - <<'PY'
import json
from pathlib import Path
p = Path("diagnostics/release-assurance-diagnostics.json")
print(p.exists())
if p.exists():
    data = json.loads(p.read_text())
    print(data.get("schema_version"))
    print(data.get("passed"))
PY
```

Expected: workflow conclusion `failure`, artifact exists, JSON `passed: false`, no raw secrets.

---

## Spec coverage self-check

| Spec requirement | Task |
|------------------|------|
| Optional `upload_diagnostics_json` input, default false | Task 1 |
| Pass `--diagnostics-json` only when enabled | Task 1 |
| Create diagnostics directory | Task 1 |
| Upload diagnostics artifact on failure | Task 2 |
| Preserve workflow failure conclusion | Task 2 |
| Workflow remains `workflow_dispatch` | unchanged |
| `permissions: contents: read` preserved | unchanged |
| Safe token only | unchanged |
| New checker + tests | Tasks 3-4 |
| Docs updates | Task 5 |
| Gate integration | Task 6 |
| Push/CI/dispatch validation | Task 8 |
