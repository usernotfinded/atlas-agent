# Template Source-of-Truth Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `src/atlas_agent/templates/` the single canonical template source, remove the duplicate root-level `templates/` tree, and update checkers/tests/docs so the packaged copy is the only source of truth while preserving fail-closed defaults and clean-install behavior.

**Architecture:** Delete the byte-identical root `templates/routine-trader/` duplicate; redirect `src/atlas_agent/workspace.py` fallback to the packaged copy filesystem path; replace the root-vs-package parity checker with canonical packaged-template integrity tests; update docs/checkers that referenced the root path.

**Tech Stack:** Python 3.14, setuptools package-data, importlib.resources, pytest, bash.

---

## Decision gate

**Selected option: A** — make the packaged copy canonical and delete the root-level duplicate.

| Criterion | Evidence |
|---|---|
| `src/atlas_agent/templates/` contains complete canonical content | `diff -rq templates/routine-trader src/atlas_agent/templates/routine-trader` is empty; 51 files each, byte-identical |
| Root `templates/` is not required by installed package behavior | `importlib.resources.files("atlas_agent").joinpath("templates", ...)` is already the primary source in `workspace.py`; wheel/sdist/clean-install checks use packaged path |
| Docs/checkers/tests can be safely updated | Scouts identified all references; no human-facing docs tell users to edit root `templates/` |
| `atlas init` works from clean install/wheel | `scripts/check_clean_install.py` already exercises this; package-data declaration is correct |
| No release/package/distribution checks fail | `pyproject.toml` package-data already ships `src/atlas_agent/templates/routine-trader/**` |

---

## Task 1: Delete root-level template duplicate

**Files:**
- Delete: `templates/routine-trader/` (entire tree)
- Delete: empty `templates/` directory after removal
- Modify: `MANIFEST.in`
- Modify: `.gitignore`

- [ ] **Step 1: Remove root template tree**

```bash
cd /Users/natanmucelli/Desktop/prog/atlas-agent
git rm -r templates/routine-trader
rmdir templates 2>/dev/null || true
```

- [ ] **Step 2: Remove stale MANIFEST.in directive**

Edit `MANIFEST.in` and delete line 1:

```text
recursive-include templates *
```

Remaining content:

```text
recursive-include docs *.md
recursive-include configs *.yaml
include LICENSE
include README.md
include DISCLAIMER.md
include CONTRIBUTING.md
include SECURITY.md
include AGENTS.md
```

- [ ] **Step 3: Remove stale .gitignore exceptions**

Edit `.gitignore` and delete lines 34-35:

```text
!templates/routine-trader/memory/
!templates/routine-trader/memory/**
```

Keep lines 36-37 for the packaged copy.

- [ ] **Step 4: Verify no root template files remain tracked**

```bash
git ls-files | grep "^templates/" || true
```

Expected: no output.

---

## Task 2: Update workspace.py fallback to canonical packaged path

**Files:**
- Modify: `src/atlas_agent/workspace.py:192-195` (error message)
- Modify: `src/atlas_agent/workspace.py:217-219` (fallback path)

- [ ] **Step 1: Update error message**

Replace:

```python
raise WorkspaceInitError(
    f"Template '{template}' not found. "
    "Ensure atlas_agent is installed with package data or that "
    "a repo template exists at templates/<template>."
)
```

with:

```python
raise WorkspaceInitError(
    f"Template '{template}' not found. "
    "Ensure atlas_agent is installed with package data "
    "(src/atlas_agent/templates/<template>)."
)
```

- [ ] **Step 2: Update fallback path**

Replace:

```python
fallback = Path(__file__).parent.parent.parent / "templates" / template
```

with:

```python
fallback = Path(__file__).parent / "templates" / template
```

- [ ] **Step 3: Run workspace tests**

```bash
python -m pytest tests/test_workspace_init.py -q
```

Expected: all pass.

---

## Task 3: Remove root-vs-package parity checker and test

**Files:**
- Delete: `scripts/check_template_parity.py`
- Delete: `tests/test_template_parity.py`
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `tests/test_release_check_scripts.py`

- [ ] **Step 1: Delete parity checker and test**

```bash
git rm scripts/check_template_parity.py
git rm tests/test_template_parity.py
```

- [ ] **Step 2: Update dev_check.sh**

Replace section at lines 60-64:

```bash
echo ""
echo "3a. template parity check"
SECONDS=0
"$PYTHON_BIN" scripts/check_template_parity.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

with:

```bash
echo ""
echo "3a. packaged template integrity check"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_packaging.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Replace section at lines 185-190:

```bash
echo ""
echo "18a. template parity tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_parity.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Delete these lines entirely (no replacement needed; the integrity check above replaces both).

- [ ] **Step 3: Update ci_check.sh**

Replace section at lines 53-58:

```bash
echo ""
echo "4a. template parity checks"
SECONDS=0
"$PYTHON_BIN" scripts/check_template_parity.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

with:

```bash
echo ""
echo "4a. packaged template integrity check"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_packaging.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Delete line 244 (`"$PYTHON_BIN" -m pytest tests/test_template_parity.py -q`) from the focused pytest subset; the integrity check above replaces it.

- [ ] **Step 4: Update test_release_check_scripts.py**

Edit `tests/test_release_check_scripts.py` lines 787 and 791:

Replace line 787:

```python
assert "check_template_parity.py" in content
```

with:

```python
assert "test_template_packaging.py" in content
```

Replace line 791:

```python
assert "tests/test_template_parity.py" in content
```

with:

```python
assert "tests/test_template_packaging.py" in content
```

- [ ] **Step 5: Run release check script tests**

```bash
python -m pytest tests/test_release_check_scripts.py -q
```

Expected: all pass.

---

## Task 4: Update env template checker and tests

**Files:**
- Modify: `scripts/check_env_templates.py`
- Modify: `tests/test_env_templates.py`
- Modify: `scripts/check_generated_artifacts.py`

- [ ] **Step 1: Update check_env_templates.py paths**

Replace the `env_files` list at lines 132-136:

```python
env_files = [
    repo_root / ".env.example",
    repo_root / "templates" / "routine-trader" / ".env.example",
    repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
]
```

with:

```python
env_files = [
    repo_root / ".env.example",
    repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
]
```

Replace the parity-check section at lines 150-155:

```python
root_path = repo_root / ".env.example"
tmpl_paths = [
    repo_root / "templates" / "routine-trader" / ".env.example",
    repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
]
```

with:

```python
root_path = repo_root / ".env.example"
tmpl_paths = [
    repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
]
```

- [ ] **Step 2: Update test_env_templates.py synthetic tests**

Replace `test_detects_template_parity_mismatch` (lines 70-78):

```python
def test_detects_template_parity_mismatch(self, tmp_path: Path) -> None:
    root = tmp_path / ".env.example"
    tmpl = tmp_path / "templates" / "routine-trader" / ".env.example"
    tmpl.parent.mkdir(parents=True)
    root.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.6\n")
    tmpl.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.55\n")
    result = _run_checker(str(tmp_path))
    assert result.returncode == 1
    assert "value mismatch for 'MINIMUM_CONFIDENCE'" in result.stdout
```

with:

```python
def test_detects_packaged_template_parity_mismatch(self, tmp_path: Path) -> None:
    root = tmp_path / ".env.example"
    tmpl = tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example"
    tmpl.parent.mkdir(parents=True)
    root.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.6\n")
    tmpl.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.55\n")
    result = _run_checker(str(tmp_path))
    assert result.returncode == 1
    assert "value mismatch for 'MINIMUM_CONFIDENCE'" in result.stdout
```

Replace `test_allows_safe_non_empty_defaults` setup (lines 80-99):

```python
def test_allows_safe_non_empty_defaults(self, tmp_path: Path) -> None:
    lines = [
        "TRADING_MODE=paper",
        "ENABLE_LIVE_TRADING=false",
        "ORDER_APPROVAL_MODE=manual_live",
        "REQUIRE_ORDER_APPROVAL=true",
        "ALLOW_LEVERAGE=false",
        "KILL_SWITCH_ENABLED=false",
        "ALPACA_BASE_URL=https://paper-api.alpaca.markets",
        "DATA_PATH=data/sample/ohlcv.csv",
        "MAX_DAILY_LOSS=100",
    ]
    text = "\n".join(lines) + "\n"
    (tmp_path / ".env.example").write_text(text)
    (tmp_path / "templates" / "routine-trader").mkdir(parents=True)
    (tmp_path / "templates" / "routine-trader" / ".env.example").write_text(text)
    (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader").mkdir(parents=True)
    (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example").write_text(text)
    result = _run_checker(str(tmp_path))
    assert result.returncode == 0, result.stdout
```

with:

```python
def test_allows_safe_non_empty_defaults(self, tmp_path: Path) -> None:
    lines = [
        "TRADING_MODE=paper",
        "ENABLE_LIVE_TRADING=false",
        "ORDER_APPROVAL_MODE=manual_live",
        "REQUIRE_ORDER_APPROVAL=true",
        "ALLOW_LEVERAGE=false",
        "KILL_SWITCH_ENABLED=false",
        "ALPACA_BASE_URL=https://paper-api.alpaca.markets",
        "DATA_PATH=data/sample/ohlcv.csv",
        "MAX_DAILY_LOSS=100",
    ]
    text = "\n".join(lines) + "\n"
    (tmp_path / ".env.example").write_text(text)
    (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader").mkdir(parents=True)
    (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example").write_text(text)
    result = _run_checker(str(tmp_path))
    assert result.returncode == 0, result.stdout
```

- [ ] **Step 3: Update check_generated_artifacts.py allowlist**

Edit `scripts/check_generated_artifacts.py` lines 42-46:

```python
SECRET_TEMPLATE_ALLOWLIST = {
    ".env.example",
    "src/atlas_agent/templates/routine-trader/.env.example",
    "templates/routine-trader/.env.example",
}
```

with:

```python
SECRET_TEMPLATE_ALLOWLIST = {
    ".env.example",
    "src/atlas_agent/templates/routine-trader/.env.example",
}
```

- [ ] **Step 4: Run env template tests**

```bash
python scripts/check_env_templates.py
python -m pytest tests/test_env_templates.py -q
```

Expected: all pass.

---

## Task 5: Update template packaging tests

**Files:**
- Modify: `tests/test_template_packaging.py`

- [ ] **Step 1: Remove root-template references and add no-duplicate guard**

Replace lines 13-24:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_TEMPLATE = REPO_ROOT / "templates" / "routine-trader"
PKG_TEMPLATE = REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader"

SECRET_MARKERS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY")
SAFE_EXCLUSIONS = {
    # These files are allowed to mention secret-related terms in instructional context
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
    REPO_ROOT / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
}
```

with:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_TEMPLATE = REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader"

SECRET_MARKERS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY")
SAFE_EXCLUSIONS = {
    # These files are allowed to mention secret-related terms in instructional context
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
}
```

Delete `TestTemplateParity` class entirely (lines 37-60).

Replace `test_all_memory_files_are_packaged_resources` (lines 69-76):

```python
def test_all_memory_files_are_packaged_resources(self) -> None:
    pkg_memory = _relative_files(PKG_TEMPLATE / "memory")
    template = resources.files("atlas_agent").joinpath("templates", "routine-trader")
    for rel in sorted(pkg_memory):
        pkg_rel = "memory" / Path(rel)
        assert template.joinpath(str(pkg_rel)).is_file(), (
            f"Packaged template missing memory file: {pkg_rel}"
        )
```

Replace `TestNoSecretsInTemplates` to use only `PKG_TEMPLATE`:

```python
class TestNoSecretsInTemplates:
    def test_no_secret_values_in_template_starter_files(self) -> None:
        for path in PKG_TEMPLATE.rglob("*"):
            if not path.is_file():
                continue
            if path in SAFE_EXCLUSIONS:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in SECRET_MARKERS:
                if f"{marker}=" in text or f"{marker}:" in text:
                    pytest.fail(
                        f"Possible secret value in template file {path}: "
                        f"found '{marker}=' or '{marker}:'"
                    )

    def test_no_real_env_file_in_templates(self) -> None:
        assert not PKG_TEMPLATE.joinpath(".env").exists(), (
            f"Template must not include real .env file: {PKG_TEMPLATE / '.env'}"
        )

    def test_gitignore_ignores_env_in_templates(self) -> None:
        gitignore = PKG_TEMPLATE / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text(encoding="utf-8")
        assert ".env" in content, (
            f"Template .gitignore must ignore .env: {gitignore}"
        )


class TestNoDuplicateRootTemplate:
    def test_no_root_level_template_shadows_packaged_copy(self) -> None:
        root_template = REPO_ROOT / "templates" / "routine-trader"
        assert not root_template.exists(), (
            f"Root-level template duplicate must not exist: {root_template}"
        )
```

- [ ] **Step 2: Run template packaging tests**

```bash
python -m pytest tests/test_template_packaging.py -q
```

Expected: all pass.

---

## Task 6: Update workspace init test for canonical fallback

**Files:**
- Modify: `tests/test_workspace_init.py`

- [ ] **Step 1: Update fallback test**

Replace `test_init_falls_back_to_repo_template_when_package_resource_unavailable` (lines 52-69):

```python
def test_init_falls_back_to_packaged_template_when_package_resource_unavailable(
    tmp_path, monkeypatch
) -> None:
    class MissingResources:
        def joinpath(self, *parts: str) -> "MissingResources":
            return self

        def is_dir(self) -> bool:
            return False

    monkeypatch.setattr(workspace_mod.resources, "files", lambda package: MissingResources())
    workspace = tmp_path / "my-trader"

    result = init_workspace(workspace, template="routine-trader")

    assert result.path == workspace
    assert (workspace / "README.md").exists()
    assert (workspace / "memory" / "portfolio.md").exists()
```

- [ ] **Step 2: Run workspace tests**

```bash
python -m pytest tests/test_workspace_init.py -q
```

Expected: all pass.

---

## Task 7: Update docs and capability inventory references

**Files:**
- Modify: `docs/v0.6-roadmap.md`
- Modify: `docs/development/code-inventory-followups.md`
- Modify: `tests/fixtures/product_capability_inventory.json`

- [ ] **Step 1: Update roadmap path**

Edit `docs/v0.6-roadmap.md` line 30:

Replace `templates/routine-trader/configs/strategy.example.yaml` with `src/atlas_agent/templates/routine-trader/configs/strategy.example.yaml`.

- [ ] **Step 2: Update code inventory follow-ups**

Edit `docs/development/code-inventory-followups.md` line 68:

Replace:

```markdown
2. Template source-of-truth simplification (CAND-004).
```

with:

```markdown
2. Deep architectural review of remaining public-API candidates for deprecation path.
```

- [ ] **Step 3: Update product capability inventory source path**

Edit `tests/fixtures/product_capability_inventory.json` line 32:

Replace `"templates/routine-trader/"` with `"src/atlas_agent/templates/routine-trader/"`.

- [ ] **Step 4: Run product capability inventory check**

```bash
python scripts/check_product_capability_inventory.py
```

Expected: PASSED.

---

## Task 8: Mark CAND-004 implemented

**Files:**
- Modify: `docs/releases/v0.6.10-candidates.md`
- Modify: `docs/releases/v0.6.10-candidates.json`

- [ ] **Step 1: Update markdown**

Edit `docs/releases/v0.6.10-candidates.md`:

1. In the candidates table (line 44), change CAND-004 `recommendation` from `**later**` to `**now**` and add a note that it is implemented.
2. Move CAND-004 from the **Deferred Candidates** table (lines 64-67) to the **Accepted Candidates** list (after line 57) with `— **implemented**`.
3. Update the CAND-004 summary to reflect the chosen approach (packaged copy canonical, root duplicate removed).

- [ ] **Step 2: Update JSON**

Edit `docs/releases/v0.6.10-candidates.json`:

1. For the CAND-004 object, set `"recommendation": "now"`, `"selected_for_v0610": true`, `"implemented": true`.
2. Remove CAND-004 from the `deferred` array.
3. Update the summary to reflect the chosen approach.

- [ ] **Step 3: Run planning checks**

```bash
python scripts/check_v0610_planning.py
python -m pytest tests/test_check_v0610_planning.py -q
```

Expected: PASS / all pass.

---

## Task 9: Package and clean-install verification

**Files:**
- None (verification only)

- [ ] **Step 1: Build wheel/sdist and verify templates**

```bash
rm -rf dist build *.egg-info
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
python -c "import importlib.resources as r; import atlas_agent; t = r.files('atlas_agent').joinpath('templates', 'routine-trader'); print(t.is_dir(), t.joinpath('.env.example').is_file())"
```

Expected: `(True, True)`.

- [ ] **Step 2: Run clean-install check**

```bash
python scripts/check_clean_install.py
```

Expected: PASSED.

- [ ] **Step 3: Run package distribution check**

```bash
python scripts/check_package_distribution.py
```

Expected: PASSED.

- [ ] **Step 4: Clean build artifacts**

```bash
rm -rf dist build *.egg-info
```

Do not commit these.

---

## Task 10: Full validation gates

**Files:**
- None (verification only)

- [ ] **Step 1: Run required check scripts**

```bash
python scripts/check_release_metadata.py
python scripts/check_version_consistency.py
python scripts/check_trust_center.py
python scripts/check_public_docs_consistency.py
python scripts/check_reviewer_onboarding.py
python scripts/check_reviewer_outreach.py
python scripts/check_backtest_report_schema.py
python scripts/check_v0610_planning.py
python scripts/check_template_parity.py  # This command should no longer exist; skip
python scripts/check_env_templates.py
python -m compileall src
git diff --check
git diff --cached --check
```

(Note: `check_template_parity.py` is deleted; ensure no script references it.)

- [ ] **Step 2: Run targeted tests**

```bash
python -m pytest tests/test_check_v0610_planning.py -q
python -m pytest tests/test_template_packaging.py -q
python -m pytest tests/test_release_check_scripts.py -q
python -m pytest tests -k "template or init or routine_trader or package or clean_install" -q
```

Expected: all pass.

- [ ] **Step 3: Run full gates**

```bash
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

Expected: all pass.

- [ ] **Step 4: Research gate (if relevant)**

```bash
./scripts/research_check.sh
```

Run only if template/docs changes overlap with research workflows; otherwise skip and note.

---

## Task 11: Commit, push, and verify CI

**Files:**
- None (git operations)

- [ ] **Step 1: Artifact hygiene check**

```bash
git status --short
git diff --name-only
find . -maxdepth 3 -type f \( -name 'analyze_*.py' -o -name '*_analysis.py' -o -name 'inventory_*.py' -o -name 'references_*.json' -o -name 'walkthrough.md' -o -name '*.tmp' \) -print
```

Ensure no `dist/`, `build/`, `*.egg-info`, or temp files are staged.

- [ ] **Step 2: Stage and commit**

```bash
git add -A  # or stage individual changed files
git commit -m "chore: simplify template source of truth"
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Verify CI**

```bash
gh run list --repo usernotfinded/atlas-agent --branch main --limit 10
gh run watch --repo usernotfinded/atlas-agent
```

Wait for the new commit's CI run to conclude with success.

---

## Self-review checklist

1. **Spec coverage:**
   - Delete root duplicate ✅ Task 1
   - Make packaged copy canonical ✅ Task 1-2
   - Update parity checker/tests ✅ Task 3-5
   - Update env template checks ✅ Task 4
   - Update workspace fallback ✅ Task 2, 6
   - Update docs/capability inventory ✅ Task 7
   - Mark CAND-004 implemented ✅ Task 8
   - Verify clean install/wheel ✅ Task 9
   - No runtime trading changes ✅ preserved throughout

2. **Placeholder scan:** No TBD/TODO/empty steps; all code/commands exact.

3. **Type consistency:** Paths, template names, and test class names are consistent.
