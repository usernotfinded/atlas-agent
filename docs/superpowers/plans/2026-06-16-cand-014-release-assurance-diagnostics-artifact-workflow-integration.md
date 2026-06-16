# CAND-014 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the CAND-013 diagnostics artifact validator into `.github/workflows/release-assurance.yml` as an opt-in, default-off validation step that runs before upload when release assurance fails.

**Architecture:** Add a `validate_diagnostics_artifact` boolean input (default `false`) and a conditional validator step that invokes `scripts/check_release_assurance_diagnostics_artifact.py`. The validator step sits between the failure-code capture and the diagnostics artifact upload. The existing upload step and final failure step remain unchanged, preserving failure semantics. Update the static workflow checker and its tests to enforce the new input, step, and ordering. Update docs and gate integrations.

**Tech Stack:** GitHub Actions YAML, Python 3.11, pytest, bash, `gh` CLI for optional dispatch verification.

---

## Task 1: Add workflow input and validator step

**Files:**
- Modify: `.github/workflows/release-assurance.yml`

- [ ] **Step 1: Add `validate_diagnostics_artifact` input**

Insert after the `upload_diagnostics_json` input block (around line 29):

```yaml
      validate_diagnostics_artifact:
        description: "Validate the diagnostics JSON before uploading it"
        type: boolean
        required: false
        default: false
```

- [ ] **Step 2: Add validator step before diagnostics upload**

Insert a new step between the `Generate release assurance pack` step and the `Upload release assurance diagnostics artifact` step:

```yaml
      - name: Validate release assurance diagnostics artifact
        if: >-
          inputs.upload_diagnostics_json &&
          inputs.validate_diagnostics_artifact &&
          steps.release_assurance.outputs.exit_code != '0'
        run: |
          python3.11 scripts/check_release_assurance_diagnostics_artifact.py \
            artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json
```

- [ ] **Step 3: Verify ordering**

Ensure the YAML ordering is:
1. `Generate release assurance pack` (captures exit_code)
2. `Upload release assurance artifact` (success only)
3. `Validate release assurance diagnostics artifact` (failure + flags)
4. `Upload release assurance diagnostics artifact` (failure + upload flag)
5. bundle demo steps
6. `Fail if release assurance failed`

---

## Task 2: Update workflow checker

**Files:**
- Modify: `scripts/check_release_assurance_diagnostics_workflow.py`

- [ ] **Step 1: Add a helper to extract a single input block**

Refactor `_check_diagnostics_input` into two helpers: `_input_block` (returns lines for a named input) and `_check_input_boolean_default_false(name, text)`.

```python
def _input_block(text: str, input_name: str) -> str:
    """Return the YAML block for a named workflow input, or empty string."""
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{input_name}:"):
            start_idx = i
            break
    if start_idx is None:
        return ""
    start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    block_lines: list[str] = []
    for line in lines[start_idx + 1 :]:
        if line.strip() == "":
            block_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= start_indent:
            break
        block_lines.append(line)
    return "\n".join(block_lines)


def _check_boolean_input(text: str, input_name: str) -> list[str]:
    errors: list[str] = []
    block = _input_block(text, input_name)
    if not block:
        errors.append(f"Workflow must declare a {input_name} input")
        return errors
    if "type: boolean" not in block:
        errors.append(f"{input_name} input must be type boolean")
    if "default: false" not in block:
        errors.append(f"{input_name} input must default to false")
    return errors
```

- [ ] **Step 2: Update existing diagnostics input check**

Replace `_check_diagnostics_input(text)` body with:

```python
def _check_diagnostics_input(text: str) -> list[str]:
    return _check_boolean_input(text, "upload_diagnostics_json")
```

- [ ] **Step 3: Add validation input check**

Add `_check_validation_input(text)` and call it from `check_workflow`:

```python
def _check_validation_input(text: str) -> list[str]:
    return _check_boolean_input(text, "validate_diagnostics_artifact")
```

Call it in `check_workflow` after `_check_diagnostics_input`.

- [ ] **Step 4: Add validator step check**

Add `_check_diagnostics_validator_step(text)` and call it from `check_workflow`:

```python
VALIDATOR_STEP_NAME = "Validate release assurance diagnostics artifact"
VALIDATOR_COMMAND_MARKER = "scripts/check_release_assurance_diagnostics_artifact.py"


def _check_diagnostics_validator_step(text: str) -> list[str]:
    errors: list[str] = []
    if VALIDATOR_STEP_NAME not in text:
        errors.append(f"Workflow must declare a step named '{VALIDATOR_STEP_NAME}'")
        return errors

    if_line = _step_if_line(text, VALIDATOR_STEP_NAME)
    if if_line is None:
        errors.append("Diagnostics validator step must be conditional")
    else:
        if_line_lower = if_line.lower()
        if "inputs.upload_diagnostics_json" not in if_line_lower:
            errors.append(
                "Diagnostics validator step must be conditional on inputs.upload_diagnostics_json"
            )
        if "inputs.validate_diagnostics_artifact" not in if_line_lower:
            errors.append(
                "Diagnostics validator step must be conditional on inputs.validate_diagnostics_artifact"
            )
        if not (
            "steps.release_assurance.outputs.exit_code != '0'" in if_line_lower
            or "failure()" in if_line_lower
        ):
            errors.append(
                "Diagnostics validator step must only run on release assurance failure"
            )

    if VALIDATOR_COMMAND_MARKER not in text:
        errors.append(
            "Diagnostics validator step must call scripts/check_release_assurance_diagnostics_artifact.py"
        )

    return errors
```

- [ ] **Step 5: Add ordering check**

Add `_check_validator_before_upload(text)` and call it from `check_workflow`:

```python
def _step_position(text: str, step_name: str) -> int:
    return text.find(f"- name: {step_name}")


def _check_validator_before_upload(text: str) -> list[str]:
    errors: list[str] = []
    validator_pos = _step_position(text, VALIDATOR_STEP_NAME)
    upload_pos = _step_position(text, "Upload release assurance diagnostics artifact")
    if validator_pos == -1:
        errors.append("Cannot check ordering: validator step missing")
    if upload_pos == -1:
        errors.append("Cannot check ordering: diagnostics upload step missing")
    if validator_pos != -1 and upload_pos != -1 and validator_pos > upload_pos:
        errors.append("Diagnostics validator step must run before diagnostics artifact upload")
    return errors
```

Call both new checks in `check_workflow` after `_check_diagnostics_upload_step`.

---

## Task 3: Update workflow tests

**Files:**
- Modify: `tests/test_release_assurance_diagnostics_workflow.py`

- [ ] **Step 1: Add direct workflow assertions**

In `TestReleaseAssuranceDiagnosticsWorkflow`, add:

```python
    def test_validate_diagnostics_artifact_input_exists(self) -> None:
        text = _workflow_text()
        assert "validate_diagnostics_artifact:" in text
        assert "type: boolean" in text

    def test_validate_diagnostics_artifact_defaults_to_false(self) -> None:
        text = _workflow_text()
        lines = text.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("validate_diagnostics_artifact:"):
                start_idx = i
                break
        assert start_idx is not None
        start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        block_lines: list[str] = []
        for line in lines[start_idx + 1 :]:
            if line.strip() == "":
                block_lines.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= start_indent:
                break
            block_lines.append(line)
        block = "\n".join(block_lines)
        assert "default: false" in block

    def test_validator_step_exists(self) -> None:
        text = _workflow_text()
        assert "Validate release assurance diagnostics artifact" in text
        assert "scripts/check_release_assurance_diagnostics_artifact.py" in text

    def test_validator_step_is_conditional(self) -> None:
        text = _workflow_text()
        if_line = _step_if_line(text, "Validate release assurance diagnostics artifact")
        assert if_line is not None
        if_line_lower = if_line.lower()
        assert "inputs.upload_diagnostics_json" in if_line_lower
        assert "inputs.validate_diagnostics_artifact" in if_line_lower
        assert "steps.release_assurance.outputs.exit_code != '0'" in if_line_lower

    def test_validator_step_runs_before_upload(self) -> None:
        text = _workflow_text()
        validator_pos = text.find("Validate release assurance diagnostics artifact")
        upload_pos = text.find("Upload release assurance diagnostics artifact")
        assert validator_pos != -1
        assert upload_pos != -1
        assert validator_pos < upload_pos
```

- [ ] **Step 2: Add checker negative tests**

In `TestReleaseAssuranceDiagnosticsWorkflowChecker`, add:

```python
    def test_checker_fails_if_validate_diagnostics_defaults_to_true(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "validate_diagnostics_artifact:\n        description: \"Validate the diagnostics JSON before uploading it\"\n        type: boolean\n        required: false\n        default: false",
                "validate_diagnostics_artifact:\n        description: \"bad\"\n        type: boolean\n        required: false\n        default: true",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validate_diagnostics_artifact" in e and "default to false" in e.lower() for e in result["errors"])

    def test_checker_fails_if_validator_step_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Validate release assurance diagnostics artifact\n        if: >-\n          inputs.upload_diagnostics_json &&\n          inputs.validate_diagnostics_artifact &&\n          steps.release_assurance.outputs.exit_code != '0'\n        run: |\n          python3.11 scripts/check_release_assurance_diagnostics_artifact.py \\\n            artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json\n\n",
                "",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validate release assurance diagnostics artifact" in e.lower() for e in result["errors"])

    def test_checker_fails_if_validator_step_unconditional(self, tmp_path: Path) -> None:
        original = _workflow_text()
        # Remove the `if:` block from the validator step.
        lines = original.splitlines()
        validator_idx: int | None = None
        for i, line in enumerate(lines):
            if "Validate release assurance diagnostics artifact" in line:
                validator_idx = i
                break
        assert validator_idx is not None
        if_idx: int | None = None
        for j in range(validator_idx + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("- name:"):
                break
            if stripped.startswith("if:"):
                if_idx = j
                break
        assert if_idx is not None
        modified_lines = lines[:if_idx] + lines[if_idx + 1:]
        modified = "\n".join(modified_lines)
        tmp = tmp_path / "release-assurance-diagnostics-validator-unconditional.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validator step must be conditional" in e.lower() for e in result["errors"])

    def test_checker_fails_if_upload_before_validator(self, tmp_path: Path) -> None:
        original = _workflow_text()
        # Swap validator and upload step blocks by finding their `- name:` lines.
        lines = original.splitlines()
        validator_idx: int | None = None
        upload_idx: int | None = None
        for i, line in enumerate(lines):
            if "Validate release assurance diagnostics artifact" in line:
                validator_idx = i
            if "Upload release assurance diagnostics artifact" in line:
                upload_idx = i
        assert validator_idx is not None
        assert upload_idx is not None
        # Find the end of each block (next `- name:` or EOF).
        def block_end(start: int) -> int:
            for j in range(start + 1, len(lines)):
                if lines[j].strip().startswith("- name:"):
                    return j
            return len(lines)
        validator_end = block_end(validator_idx)
        upload_end = block_end(upload_idx)
        validator_block = lines[validator_idx:validator_end]
        upload_block = lines[upload_idx:upload_end]
        if validator_idx < upload_idx:
            modified_lines = (
                lines[:validator_idx]
                + upload_block
                + lines[validator_end:upload_idx]
                + validator_block
                + lines[upload_end:]
            )
        else:
            modified_lines = (
                lines[:upload_idx]
                + validator_block
                + lines[upload_end:validator_idx]
                + upload_block
                + lines[validator_end:]
            )
        modified = "\n".join(modified_lines)
        tmp = tmp_path / "release-assurance-diagnostics-upload-before-validator.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validator step must run before diagnostics artifact upload" in e.lower() for e in result["errors"])

    def test_checker_fails_if_validator_command_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "scripts/check_release_assurance_diagnostics_artifact.py",
                "scripts/check_release_assurance_diagnostics_artifact_MISSING.py",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("check_release_assurance_diagnostics_artifact.py" in e for e in result["errors"])
```

---

## Task 4: Update docs

**Files:**
- Modify: `docs/security/release-assurance-diagnostics.md`
- Modify: `docs/security/release-assurance-workflow-dispatch.md`
- Modify: `docs/security/release-readiness.md`
- Modify: `docs/reviewer-checklist.md`
- Modify: `docs/public-launch-readiness.md`

- [ ] **Step 1: `docs/security/release-assurance-diagnostics.md`**

In the `## Workflow diagnostics artifact` section, after the dispatch command, add:

```markdown
If you also want the workflow to validate the diagnostics JSON before uploading it,
set `validate_diagnostics_artifact=true`. The validator runs only when release
assurance failed, `upload_diagnostics_json=true`, and `validate_diagnostics_artifact=true`.
The artifact is uploaded only if validation succeeds, and the workflow still fails
afterward because release assurance failed.
```

Update the dispatch command to include the optional validation flag:

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.0.0-does-not-exist \
  --field upload_diagnostics_json=true \
  --field validate_diagnostics_artifact=true
```

- [ ] **Step 2: `docs/security/release-assurance-workflow-dispatch.md`**

Update the safe input values list and CLI command to include `validate_diagnostics_artifact=false`.
Add a new section `## Validating diagnostics before upload` explaining the opt-in input and failure-preservation.

- [ ] **Step 3: `docs/security/release-readiness.md`**

In the `#### Optional diagnostics artifact` section, mention `validate_diagnostics_artifact=true` and validation-before-upload.

- [ ] **Step 4: `docs/reviewer-checklist.md`**

Add checklist items:

```markdown
- [ ] `.github/workflows/release-assurance.yml` has an opt-in `validate_diagnostics_artifact` input defaulting to `false` and runs `scripts/check_release_assurance_diagnostics_artifact.py` before uploading the `release-assurance-diagnostics` artifact.
```

- [ ] **Step 5: `docs/public-launch-readiness.md`**

Add a bullet under the local verification list referencing the updated workflow checker.

---

## Task 5: Update gate scripts

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`

- [ ] **Step 1: `scripts/dev_check.sh`**

No new checker/test file is needed (existing ones are updated). Keep step labels `13s`/`13t` for workflow checker/tests and `13u`/`13v` for artifact checker/tests. No change required unless reordering is desired.

- [ ] **Step 2: `scripts/ci_check.sh`**

Same as above; existing steps already run the updated checker and tests.

---

## Task 6: Update CI workflow

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Keep existing steps**

The existing steps at lines 89–92 already run the workflow checker and tests. No change required.

---

## Task 7: Local validation

- [ ] Run:

```bash
python3.11 scripts/check_release_assurance_diagnostics_workflow.py
python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q
python3.11 scripts/check_release_assurance_diagnostics_artifact.py --help
python3.11 scripts/check_release_assurance_diagnostics.py
python3.11 scripts/check_release_assurance_bundle_workflow.py
python3.11 scripts/check_release_assurance_snapshot_integration.py
python3.11 scripts/check_docs_archive_hygiene.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_version_consistency.py
git diff --check
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

Expected: all pass.

---

## Task 8: Commit and push

- [ ] Stage explicit files:

```bash
git add .github/workflows/release-assurance.yml
git add scripts/check_release_assurance_diagnostics_workflow.py
git add tests/test_release_assurance_diagnostics_workflow.py
# Add only the docs that actually changed
git add docs/security/release-assurance-diagnostics.md
# ... etc
git add docs/superpowers/specs/2026-06-16-cand-014-release-assurance-diagnostics-artifact-workflow-integration-design.md
```

- [ ] Commit:

```bash
git commit -m "ci: validate release assurance diagnostics artifact before upload"
```

- [ ] Push:

```bash
git push origin main
```

---

## Task 9: Post-push CI verification

- [ ] Watch push-CI:

```bash
gh run list --repo usernotfinded/atlas-agent --branch main --limit 5
```

Wait for the run to complete. If it fails, inspect logs, fix, commit, push, and repeat.

---

## Task 10: Optional controlled failure dispatch

- [ ] After push-CI succeeds, run:

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.0.0-does-not-exist \
  --field upload_diagnostics_json=true \
  --field validate_diagnostics_artifact=true \
  --field run_bundle_demo=false \
  --field bundle_demo_version=v0.6.11
```

- [ ] Wait for the run, then:

```bash
gh run list --repo usernotfinded/atlas-agent --workflow=release-assurance.yml --limit 5
```

Expected:
- Workflow conclusion: failure
- Validator step: passed
- Diagnostics artifact: uploaded
- Final failure step: preserved

- [ ] Download and re-validate:

```bash
gh run download <run-id> --name release-assurance-diagnostics --dir ./local-diagnostics
python3.11 scripts/check_release_assurance_diagnostics_artifact.py ./local-diagnostics \
  --expect-release v0.0.0-does-not-exist \
  --expect-failed-check package_version_aligned \
  --json
```

If dispatch is blocked, report the exact blocker.
