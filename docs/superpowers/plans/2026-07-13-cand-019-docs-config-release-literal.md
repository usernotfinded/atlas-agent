# CAND-019: Docs/config hardcoded release-literal sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `scripts/check_hardcoded_release_literals.py` to also scan example configs, example code, and docs examples for hardcoded release-identity literals, and add regression tests.

**Architecture:** Keep the existing Python AST scanner for `scripts/*.py` unchanged. Add a second text scanner that walks `configs/`, `examples/`, and `docs/examples/` and reports any line containing a monitored literal from `release-metadata.json`. Combine both scanners in `main()` for a single pass/fail result.

**Tech Stack:** Python 3.11 standard library (`ast`, `re`, `pathlib`, `json`). pytest for tests.

---

### Task 1: Add docs/config text scanner to the checker

**Files:**
- Modify: `scripts/check_hardcoded_release_literals.py`

- [ ] **Step 1.1: Add imports and directory list**

Add `import re` at the top (keep existing imports). After the existing `SCRIPTS_DIR` constant, add:

```python
DOCS_CONFIG_DIRS = [
    REPO_ROOT / "configs",
    REPO_ROOT / "examples",
    REPO_ROOT / "docs" / "examples",
]
```

- [ ] **Step 1.2: Add text-file scanner helper**

Insert these two functions after `_scan_file`:

```python
def _scan_text_file(path: Path, literals: set[str]) -> list[tuple[int, str, str]]:
    """Scan a single text file for monitored release-identity literals.

    Returns a list of (lineno, literal, snippet) tuples.
    """
    if not literals:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    pattern = re.compile("|".join(re.escape(lit) for lit in literals))
    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            snippet = line.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            findings.append((lineno, match.group(0), snippet))
    return findings


def _scan_docs_config_dirs(literals: set[str]) -> list[tuple[Path, int, str, str]]:
    """Scan configured docs/config example directories for monitored literals."""
    findings: list[tuple[Path, int, str, str]] = []
    for directory in DOCS_CONFIG_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            for lineno, value, snippet in _scan_text_file(path, literals):
                findings.append((path, lineno, value, snippet))
    return findings
```

- [ ] **Step 1.3: Wire both scanners into `main()`**

Replace the existing `main()` body with:

```python
def main() -> int:
    literals = _load_release_literals()
    if not literals:
        print("No release-identity literals loaded from metadata; nothing to check.")
        return 0

    script_findings: list[tuple[Path, int, str, str]] = []
    for path in sorted(SCRIPTS_DIR.iterdir()):
        if not _is_active_script(path):
            continue
        for lineno, value, context in _scan_file(path, literals):
            script_findings.append((path, lineno, value, context))

    docs_findings = _scan_docs_config_dirs(literals)

    if not script_findings and not docs_findings:
        print("Hardcoded release-literal check PASSED")
        print(f"  Scanned {len(list(SCRIPTS_DIR.glob('*.py')))} script file(s)")
        docs_file_count = sum(
            1
            for directory in DOCS_CONFIG_DIRS
            if directory.exists()
            for file_path in directory.rglob("*")
            if file_path.is_file()
        )
        print(f"  Scanned {docs_file_count} docs/config example file(s)")
        print(f"  Monitored literals: {sorted(literals)}")
        return 0

    print("Hardcoded release-literal check FAILED")
    if script_findings:
        print("  Active scripts contain literals that should be metadata-driven:")
        for path, lineno, value, context in script_findings:
            rel = path.relative_to(REPO_ROOT)
            print(f"  - {rel}:{lineno} {context!r} literal {value!r}")
    if docs_findings:
        print("  Docs/config examples contain literals that should be metadata-driven:")
        for path, lineno, value, snippet in docs_findings:
            rel = path.relative_to(REPO_ROOT)
            print(f"  - {rel}:{lineno} literal {value!r}  # {snippet}")
    return 2
```

- [ ] **Step 1.4: Run the checker on the repository**

Run:

```bash
python3.11 scripts/check_hardcoded_release_literals.py
```

Expected: exit 0 with a summary that includes a non-negative docs/config example file count.

---

### Task 2: Add regression tests for the docs/config scanner

**Files:**
- Modify: `tests/test_check_hardcoded_release_literals.py`

- [ ] **Step 2.1: Import the new helper**

Update the import block from:

```python
from scripts.check_hardcoded_release_literals import (
    _is_active_script,
    _load_release_literals,
    _scan_file,
    main,
)
```

to:

```python
from scripts.check_hardcoded_release_literals import (
    _is_active_script,
    _load_release_literals,
    _scan_docs_config_dirs,
    _scan_file,
    _scan_text_file,
    main,
)
```

- [ ] **Step 2.2: Add a docs/config drift fixture**

Insert after the existing `repo_clean` fixture:

```python
@pytest.fixture
def repo_docs_drift(tmp_path, monkeypatch):
    """Create a minimal repo layout with a drifted docs/config example."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    docs_releases = tmp_path / "docs" / "releases"
    docs_releases.mkdir(parents=True)
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.99",
        "current_public_release": "v0.6.99",
        "next_planned_release": "v0.6.100",
    }
    (docs_releases / "release-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    (scripts_dir / "check_active.py").write_text(
        'print("no hardcoded literals here")\n',
        encoding="utf-8",
    )

    (configs_dir / "market.example.yaml").write_text(
        'symbol: "DEMO-v0.6.99"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.REPO_ROOT", tmp_path
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.METADATA_PATH",
        docs_releases / "release-metadata.json",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR", scripts_dir
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [configs_dir],
    )
    return tmp_path
```

- [ ] **Step 2.3: Add unit and integration tests**

Append at the end of the file:

```python
def test_scan_text_file_finds_literal():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "example.yaml"
        path.write_text(
            'symbol: "DEMO-v0.6.99"\n',
            encoding="utf-8",
        )
        findings = _scan_text_file(path, {"v0.6.99"})
        assert len(findings) == 1
        assert findings[0][1] == "v0.6.99"


def test_main_fails_on_docs_config_drift(repo_docs_drift, monkeypatch, capsys):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_docs_drift / "scripts",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [repo_docs_drift / "configs"],
    )
    assert main() == 2
    captured = capsys.readouterr().out
    assert "configs/market.example.yaml" in captured
    assert "v0.6.99" in captured


def test_main_passes_when_docs_config_clean(repo_clean, monkeypatch):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_clean / "scripts",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [repo_clean / "configs"],
    )
    assert main() == 0
```

- [ ] **Step 2.4: Run the new tests**

Run:

```bash
python3.11 -m pytest tests/test_check_hardcoded_release_literals.py -q
```

Expected: all tests pass (existing + new).

---

### Task 3: Record CAND-019 in the v0.6.25 candidate chain

**Files:**
- Modify: `docs/releases/v0.6.25-candidates.json`
- Modify: `docs/releases/v0.6.25-candidates.md`
- Modify: `docs/releases/v0.6.25-candidate-selection.md`

- [ ] **Step 3.1: Add candidate to JSON**

Replace the `"candidates": []` array in `docs/releases/v0.6.25-candidates.json` with:

```json
  "candidates": [
    {
      "id": "CAND-019",
      "title": "Docs/config hardcoded release-literal sweep",
      "status": "accepted",
      "accepted": true,
      "acceptance_verdict": "PASS",
      "safety_notes": "Static checker/test-only; extends release-literal scanning to docs/config examples; no runtime, safety, broker, provider, credential, or trading changes."
    }
  ]
```

- [ ] **Step 3.2: Add candidate to Markdown**

In `docs/releases/v0.6.25-candidates.md`, replace the "Accepted" section:

```markdown
## Accepted

- **CAND-019 — Docs/config hardcoded release-literal sweep** (accepted)  
  Extends `scripts/check_hardcoded_release_literals.py` to scan `configs/`,
  `examples/`, and `docs/examples/` for monitored release-identity literals,
  and adds regression tests. Static checker/test-only; no runtime, safety,
  broker, provider, credential, network, or trading changes.
```

And update the "Proposed" section to:

```markdown
## Proposed

No additional candidates are currently proposed for `v0.6.25`.
```

- [ ] **Step 3.3: Update candidate selection gate**

In `docs/releases/v0.6.25-candidate-selection.md`, replace the "Proposed candidates" section with:

```markdown
## Proposed candidates

- **CAND-019 — Docs/config hardcoded release-literal sweep**  
  Extend the release-literal checker to cover example configs, example code,
  and docs examples so release drift is caught before cutover. Static
  checker/test-only; no live trading, broker/provider execution, credential
  loading, network access, or approval queue mutation.
```

- [ ] **Step 3.4: Validate candidate-chain consistency**

Run:

```bash
python3.11 scripts/check_candidate_chain.py
python3.11 scripts/check_public_docs_consistency.py
```

Expected: both exit 0.

---

### Task 4: Full verification and commit

- [ ] **Step 4.1: Run all relevant checks**

```bash
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_hardcoded_release_literals.py
python3.11 scripts/check_candidate_chain.py
python3.11 -m pytest tests/test_check_hardcoded_release_literals.py tests/test_public_docs_consistency.py tests/test_candidate_chain.py -q
```

Expected: all pass.

- [ ] **Step 4.2: Commit the work**

```bash
git add scripts/check_hardcoded_release_literals.py tests/test_check_hardcoded_release_literals.py docs/releases/v0.6.25-candidates.json docs/releases/v0.6.25-candidates.md docs/releases/v0.6.25-candidate-selection.md docs/superpowers/specs/2026-07-13-cand-019-docs-config-release-literal-design.md
git commit -m "feat(cand-019): extend release-literal checker to docs/config examples

- Add text scanner for configs/, examples/, and docs/examples/.
- Report line numbers and snippets for docs/config findings.
- Add regression tests for the new scanner.
- Record CAND-019 in the v0.6.25 candidate chain."
```

---

## Spec coverage

| Spec requirement | Plan task |
|---|---|
| Scan `configs/*.yaml` | Task 1 |
| Scan `examples/**/*` | Task 1 |
| Scan `docs/examples/**/*` | Task 1 |
| Use monitored literals from `release-metadata.json` | Task 1 |
| Report path, line, literal, snippet | Task 1 |
| Add regression tests | Task 2 |
| Record candidate in `v0.6.25` chain | Task 3 |
| Full verification before commit | Task 4 |

## Placeholder scan

No TBD/TODO/fill-in-later entries. All code blocks are complete and runnable.
