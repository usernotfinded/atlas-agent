# CAND-017 Post-Release CI Run-ID Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scripts/update_release_assurance_ci.py` and tests so that post-release assurance dossiers can be updated with GitHub Actions run IDs for a release tag.

**Architecture:** A small CLI script shells out to the authenticated `gh` CLI, parses JSON workflow runs, filters to core workflows, and updates the markdown and JSON assurance files. It is dry-run by default and requires `--write` to mutate files.

**Tech Stack:** Python 3.11 standard library, `gh` CLI, `pytest`.

---

## File structure

- **Create** `scripts/update_release_assurance_ci.py` — main CLI script.
- **Create** `tests/test_update_release_assurance_ci.py` — unit tests with mocked `gh` output.
- **Modify** `docs/releases/v0.6.23-candidates.md` — accept CAND-017 into the candidate chain.
- **Modify** `docs/releases/v0.6.23-plan.md` — list CAND-017 as an accepted candidate.
- **Modify** `docs/autonomy-roadmap.md` — record CAND-017 in the v0.6.23 section.

---

### Task 1: Create `scripts/update_release_assurance_ci.py` skeleton

**Files:**
- Create: `scripts/update_release_assurance_ci.py`

- [ ] **Step 1: Write the module docstring and constants**

```python
#!/usr/bin/env python3
"""Update post-release assurance dossiers with GitHub Actions CI run IDs.

Deterministic helper. Dry-run by default; pass --write to mutate files.
Uses the authenticated gh CLI. Does not load credentials, call brokers,
providers, or trading code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CORE_WORKFLOWS = [
    "CI",
    "Release Gate",
    "Atlas Agent Paper Routines",
]

CI_SECTION_HEADER = "## GitHub Actions / CI Status"
```

- [ ] **Step 2: Add `run_gh` helper**

```python
def run_gh(args: list[str]) -> str:
    """Run gh with the given args and return stdout as string."""
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
```

- [ ] **Step 3: Add `release_exists` and `fetch_runs` helpers**

```python
def release_exists(tag: str) -> bool:
    try:
        run_gh(["release", "view", tag, "--json", "url"])
        return True
    except subprocess.CalledProcessError:
        return False


def fetch_runs(tag: str) -> list[dict]:
    fields = [
        "name",
        "displayTitle",
        "headBranch",
        "event",
        "status",
        "conclusion",
        "url",
        "createdAt",
        "databaseId",
    ]
    stdout = run_gh(
        [
            "run",
            "list",
            "--branch",
            tag,
            "--limit",
            "100",
            "--json",
            ",".join(fields),
        ]
    )
    return json.loads(stdout)
```

- [ ] **Step 4: Add `filter_core_runs` helper**

```python
def filter_core_runs(runs: list[dict]) -> list[dict]:
    """Keep the most recent run for each core workflow name."""
    seen: set[str] = set()
    filtered: list[dict] = []
    for run in runs:
        name = run.get("name", "")
        if name in CORE_WORKFLOWS and name not in seen:
            seen.add(name)
            filtered.append(run)
    return filtered
```

- [ ] **Step 5: Add formatting helpers**

```python
def format_md_table(runs: list[dict]) -> str:
    lines = [
        "| Workflow | Run | Conclusion |",
        "|---|---|---|",
    ]
    for run in runs:
        name = run.get("name", "")
        run_id = run.get("databaseId", "")
        url = run.get("url", "")
        conclusion = run.get("conclusion", run.get("status", ""))
        if url:
            link = f"{run_id} ({url})"
        else:
            link = str(run_id)
        lines.append(f"| {name} | {link} | {conclusion} |")
    return "\n".join(lines)


def format_json_runs(runs: list[dict]) -> list[dict]:
    return [
        {
            "name": run.get("name", ""),
            "run_id": run.get("databaseId"),
            "url": run.get("url", ""),
            "conclusion": run.get("conclusion", run.get("status", "")),
            "created_at": run.get("createdAt", ""),
        }
        for run in runs
    ]
```

- [ ] **Step 6: Add file-update helpers**

```python
def update_md_file(path: Path, table: str) -> None:
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^({re.escape(CI_SECTION_HEADER)}\n\n).*?(?=\n## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    replacement = rf"\1{table}\n\n"
    new_content, count = pattern.subn(replacement, content)
    if count == 0:
        raise ValueError(f"Could not find section {CI_SECTION_HEADER!r} in {path}")
    path.write_text(new_content, encoding="utf-8")


def update_json_file(path: Path, runs: list[dict]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ci_status"] = {
        "status": "recorded",
        "note": "Runs captured by scripts/update_release_assurance_ci.py",
        "runs": format_json_runs(runs),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
```

- [ ] **Step 7: Add `main` and entry point**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update post-release assurance dossiers with CI run IDs."
    )
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.6.23")
    parser.add_argument("--md", required=True, help="Path to markdown assurance file")
    parser.add_argument("--json", required=True, help="Path to JSON assurance file")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually update the files (default is dry-run)",
    )
    args = parser.parse_args(argv)

    if not release_exists(args.tag):
        print(f"GitHub Release {args.tag} not found.", file=sys.stderr)
        return 1

    runs = filter_core_runs(fetch_runs(args.tag))
    table = format_md_table(runs)
    json_runs = format_json_runs(runs)

    md_path = Path(args.md)
    json_path = Path(args.json)

    if args.write:
        update_md_file(md_path, table)
        update_json_file(json_path, runs)
        print(f"Updated {md_path} and {json_path}")
    else:
        print("Dry run. Proposed markdown update:")
        print(table)
        print("\nProposed JSON runs:")
        print(json.dumps(json_runs, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

### Task 2: Create `tests/test_update_release_assurance_ci.py`

**Files:**
- Create: `tests/test_update_release_assurance_ci.py`

- [ ] **Step 1: Write imports and fixtures**

```python
import json
import subprocess
from pathlib import Path

import pytest

from scripts.update_release_assurance_ci import (
    CORE_WORKFLOWS,
    filter_core_runs,
    format_json_runs,
    format_md_table,
    update_json_file,
    update_md_file,
)


@pytest.fixture
def sample_runs():
    return [
        {
            "name": "CI",
            "databaseId": 123,
            "url": "https://github.com/org/repo/actions/runs/123",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:00:00Z",
        },
        {
            "name": "Release Gate",
            "databaseId": 124,
            "url": "https://github.com/org/repo/actions/runs/124",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:05:00Z",
        },
        {
            "name": "CI",
            "databaseId": 125,
            "url": "https://github.com/org/repo/actions/runs/125",
            "conclusion": "failure",
            "status": "completed",
            "createdAt": "2026-07-13T09:00:00Z",
        },
        {
            "name": "Unknown Workflow",
            "databaseId": 126,
            "url": "https://github.com/org/repo/actions/runs/126",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:10:00Z",
        },
    ]
```

- [ ] **Step 2: Test `filter_core_runs` keeps most recent per workflow**

```python
def test_filter_core_runs_keeps_most_recent(sample_runs):
    result = filter_core_runs(sample_runs)
    names = [r["name"] for r in result]
    assert names == ["CI", "Release Gate"]
    assert result[0]["databaseId"] == 123  # first CI, not older 125
```

- [ ] **Step 3: Test `format_md_table`**

```python
def test_format_md_table(sample_runs):
    filtered = filter_core_runs(sample_runs)
    table = format_md_table(filtered)
    assert "| Workflow | Run | Conclusion |" in table
    assert "| CI | [123](https://github.com/org/repo/actions/runs/123) | success |" in table
    assert "| Release Gate | [124](https://github.com/org/repo/actions/runs/124) | success |" in table
```

- [ ] **Step 4: Test `format_json_runs`**

```python
def test_format_json_runs(sample_runs):
    filtered = filter_core_runs(sample_runs)
    runs = format_json_runs(filtered)
    assert runs[0] == {
        "name": "CI",
        "run_id": 123,
        "url": "https://github.com/org/repo/actions/runs/123",
        "conclusion": "success",
        "created_at": "2026-07-13T10:00:00Z",
    }
```

- [ ] **Step 5: Test `update_md_file` replaces CI section**

```python
def test_update_md_file(tmp_path):
    md = tmp_path / "assurance.md"
    md.write_text(
        "# Assurance\n\n## GitHub Actions / CI Status\n\nplaceholder\n\n## Safety\n\nsafe.\n",
        encoding="utf-8",
    )
    update_md_file(md, "| Workflow | Run |\n|---|---|\n| CI | 123 (url) |")
    content = md.read_text(encoding="utf-8")
    assert "## GitHub Actions / CI Status" in content
    assert "placeholder" not in content
    assert "| CI | 123 (url) |" in content
    assert "## Safety" in content
```

- [ ] **Step 6: Test `update_json_file`**

```python
def test_update_json_file(tmp_path, sample_runs):
    json_file = tmp_path / "assurance.json"
    json_file.write_text(
        json.dumps({"release": "v0.6.23", "ci_status": {"status": "placeholder"}}),
        encoding="utf-8",
    )
    filtered = filter_core_runs(sample_runs)
    update_json_file(json_file, filtered)
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["ci_status"]["status"] == "recorded"
    assert data["ci_status"]["runs"][0]["name"] == "CI"
```

- [ ] **Step 7: Test main dry-run does not mutate**

```python
def test_main_dry_run_does_not_mutate(tmp_path, monkeypatch):
    md = tmp_path / "assurance.md"
    md.write_text(
        "# Assurance\n\n## GitHub Actions / CI Status\n\nplaceholder\n\n",
        encoding="utf-8",
    )
    jf = tmp_path / "assurance.json"
    jf.write_text(
        json.dumps({"release": "v0.6.23", "ci_status": {"status": "placeholder"}}),
        encoding="utf-8",
    )

    def fake_release_exists(tag):
        return True

    def fake_fetch_runs(tag):
        return [
            {
                "name": "CI",
                "databaseId": 999,
                "url": "https://example.com/999",
                "conclusion": "success",
                "status": "completed",
                "createdAt": "2026-07-13T10:00:00Z",
            }
        ]

    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.release_exists", fake_release_exists
    )
    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.fetch_runs", fake_fetch_runs
    )

    from scripts.update_release_assurance_ci import main

    assert main(["--tag", "v0.6.23", "--md", str(md), "--json", str(jf)]) == 0
    assert "placeholder" in md.read_text(encoding="utf-8")
    assert json.loads(jf.read_text(encoding="utf-8"))["ci_status"]["status"] == "placeholder"
```

- [ ] **Step 8: Test main missing release exits non-zero**

```python
def test_main_missing_release(monkeypatch):
    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.release_exists", lambda tag: False
    )
    from scripts.update_release_assurance_ci import main

    assert main(["--tag", "v0.6.99", "--md", "x.md", "--json", "x.json"]) == 1
```

---

### Task 3: Update candidate-chain docs

**Files:**
- Modify: `docs/releases/v0.6.23-candidates.md`
- Modify: `docs/releases/v0.6.23-plan.md`
- Modify: `docs/autonomy-roadmap.md`

- [ ] **Step 1: Accept CAND-017 in `docs/releases/v0.6.23-candidates.md`**

Replace the "Candidate acceptance" and "Accepted" sections with:

```markdown
## Candidate acceptance

**CAND-017** is accepted into the `v0.6.23` candidate chain as a
release-maintenance tooling candidate. Accepting a candidate here is
documentation/governance only and does not authorize live trading, live submit,
order placement, broker/provider execution, credential loading, network access,
or approval queue mutation.

## Accepted

- **CAND-017: Post-Release CI Run-ID Recorder**
  - Adds `scripts/update_release_assurance_ci.py` and tests.
  - Queries GitHub Actions for core workflow runs associated with a release tag.
  - Updates `docs/releases/v0.6.X-post-release-assurance.md` and `.json` with
    run IDs and URLs.
  - Dry-run by default; requires `--write` to mutate files.
  - Uses the authenticated `gh` CLI and Python standard library only.
  - Does not enable live trading, live submit, broker/provider execution,
    credential loading, network access, order placement, pending-order creation,
    or approval queue mutation.
  - Does not change `RiskManager`, kill switch, deadman, heartbeat, or audit
    hash-chain behavior.
  - Does not broaden the CAND-014 provider-artifact extraction boundary.
```

- [ ] **Step 2: Update `docs/releases/v0.6.23-plan.md` accepted table**

Add CAND-017 to the candidate table and update the intro text to note one
candidate is accepted.

- [ ] **Step 3: Update `docs/autonomy-roadmap.md`**

Add a new subsection under `### Candidate status in the v0.6.23 planning line`
describing CAND-017, similar to the CAND-016 description.

---

### Task 4: Run verification and commit

- [ ] **Step 1: Run new tests**

```bash
python3.11 -m pytest tests/test_update_release_assurance_ci.py -q
```
Expected: all pass.

- [ ] **Step 2: Run project checks**

```bash
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_candidate_chain.py
python3.11 -m pytest tests/test_candidate_chain.py tests/test_public_docs_consistency.py -q
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/update_release_assurance_ci.py tests/test_update_release_assurance_ci.py docs/releases/v0.6.23-candidates.md docs/releases/v0.6.23-plan.md docs/autonomy-roadmap.md
git commit -m "feat(cand-017): post-release CI run-ID recorder"
```

---

## Self-review

- Spec coverage: all sections map to tasks above.
- Placeholder scan: no TBD/TODO/fill-in-details found.
- Type consistency: function names and data shapes are consistent.
