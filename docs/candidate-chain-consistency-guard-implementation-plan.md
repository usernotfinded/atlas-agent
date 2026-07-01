# CAND-012: Candidate-Chain Consistency Guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `scripts/check_candidate_chain.py` and `tests/test_candidate_chain.py`, then integrate the checker into dev/CI gates and update the checks reference, without modifying runtime code, version files, or release state.

**Architecture:** A stdlib-only deterministic checker loads `docs/releases/release-metadata.json` via the existing `scripts/release_metadata.py` helper, discovers candidate-chain Markdown/JSON files under `docs/releases/`, validates alignment between metadata and candidate-chain docs, enforces candidate status/verdict/value rules, scans candidate-chain Markdown for candidate-chain-specific forbidden claims, and exits `0`/`1`/`2`. Companion pytest tests use `tmp_path` fixture trees and subprocess invocation.

**Tech Stack:** Python 3.11 standard library; `pytest` for tests; existing `scripts/release_metadata.py` helper.

---

## 1. Title and candidate ID

- **Candidate ID:** `CAND-012`
- **Title:** Candidate-Chain Consistency Guard
- **Subtitle:** Deterministic validation that release-metadata, candidate-chain Markdown, and candidate-chain JSON remain aligned, coherent, and free of premature release or live-trading claims.
- **Safety classification:** docs/checker/test-only; no runtime changes.

## 2. Baseline state

At the time of this implementation plan, the repository is in the following state:

- `git status --short`: clean.
- `git rev-parse HEAD`: `027cc36eda401c9714630beaf29a2dc9b66c11ef`.
- `git tag --points-at HEAD`: none (HEAD is the design commit; tag `v0.6.19` points to `01a4958fdbec516cd797516917391cd1236ab5ea`).
- `git rev-parse v0.6.19^{}`: `01a4958fdbec516cd797516917391cd1236ab5ea`.
- `gh release view v0.6.19`: exists, GitHub-only.
- `git tag --list 'v0.6.20*'`: empty.
- `git ls-remote --tags origin 'v0.6.20*'`: empty.
- `gh release view v0.6.20`: not found.
- `atlas_agent.__version__`: `0.6.19`.
- `pyproject.toml` version: `0.6.19`.
- `docs/releases/release-metadata.json`: `source_version` `0.6.19`, `current_public_release` `v0.6.19`, `next_planned_release` `v0.6.20`, `pypi_published` `false`, `release_type` `github_only`.
- `atlas run --mode live`: exits `2` / fail-closed.
- `mypy src/atlas_agent/safety/kill_switch.py`: zero issues.
- Design document: `docs/candidate-chain-consistency-guard-design.md` approved and independently reviewed `PASS_WITH_WARNINGS`.

## 3. Design-review findings incorporated

This implementation plan addresses the four non-blocking warnings from the independent design review.

### 3.1 Corrected `check_forbidden_claims.py` premise

`scripts/check_forbidden_claims.py` scans the `docs/` tree recursively, so candidate-chain Markdown files are already covered by the general forbidden-claims checker. CAND-012’s value proposition is therefore:

> Adding deterministic consistency validation between release metadata, candidate-chain JSON, candidate-chain Markdown, candidate status fields, release status fields, PyPI flags, tag/GitHub Release claims, and candidate-chain-specific release-state claims.

The checker does not need to duplicate general safety/profit scanning.

### 3.2 Avoid private underscore API reuse

The implementation will **not** import `_FORBIDDEN_PHRASES`, `_collect_paths`, or any other underscore-prefixed member from `scripts/check_forbidden_claims.py`. Instead, `scripts/check_candidate_chain.py` will define a small, stable, candidate-chain-specific forbidden phrase/pattern list and accept limited duplication.

### 3.3 Exact Markdown status patterns

The checker will parse only explicit, narrow status-line patterns from candidate-chain Markdown:

- `Status: <value>`
- `Release status: <value>`
- `Candidate status: <value>`
- `Acceptance status: <value>`
- `Current public release: <value>`
- `Next planned release: <value>`
- `PyPI: <value>`
- `PyPI published: <true|false>`
- `GitHub Release: <value>`
- `Tag created: <true|false>`
- Bullet equivalents: `- Status: <value>`, `* Status: <value>`, `• Status: <value>`

Rules:

- JSON remains authoritative for machine-readable fields.
- Markdown scanning is lightweight and line-oriented.
- Markdown wording differences produce warnings unless they create a clear contradiction.
- Only explicit status lines are parsed; arbitrary prose is scanned only for forbidden claims.

### 3.4 Historical release-line derivation

Historical release lines are derived from `docs/releases/release-metadata.json` release entries whose `status` is `"historical"`.

- `current_public_release = metadata.current_public_release`
- `next_planned_release = metadata.next_planned_release`
- `historical_release_lines = {r.tag for r in metadata.releases if r.status == "historical"}`
- `released_release_lines = {current_public_release} ∪ historical_release_lines`
- `planning_release_line = next_planned_release`
- Unknown release lines warn, not fail, unless they claim released/tag/GitHub Release/PyPI publication status or contradict metadata.

## 4. Implementation scope

The implementation covers:

1. Create `scripts/check_candidate_chain.py`.
2. Create `tests/test_candidate_chain.py`.
3. Modify `scripts/dev_check.sh` to run the new checker after release metadata/version checks.
4. Modify `scripts/ci_check.sh` to run the new checker after release metadata/version checks.
5. Update `docs/development/checks-reference.md` to document the new checker.

No runtime code, version files, release notes, or candidate-chain release docs are created or modified.

## 5. Non-goals

CAND-012 explicitly does **not**:

1. Create the `v0.6.20` candidate-chain files (`v0.6.20-candidates.md`, `v0.6.20-candidates.json`, etc.).
2. Modify runtime code under `src/atlas_agent/`.
3. Bump the package version or start the `v0.6.20` release cutover.
4. Create a `v0.6.20` tag or GitHub Release.
5. Publish to PyPI.
6. Replace `scripts/check_release_metadata.py`, `scripts/check_version_consistency.py`, `scripts/check_forbidden_claims.py`, or `scripts/check_bounded_autonomy_governance.py`.
7. Implement complex NLP or semantic analysis.
8. Enforce a single universal candidate-chain schema across all historical releases.
9. Add new live-trading, broker, provider, credential, network, or execution capabilities.
10. Refactor `scripts/check_forbidden_claims.py` unless a strong public-helper pattern already exists (the plan defaults to a local phrase list).

## 6. Release-metadata model

The checker will reuse `scripts/release_metadata.py`:

```python
from release_metadata import load_metadata, ReleaseMetadata

metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
data = load_metadata(metadata_path)
metadata = ReleaseMetadata(data)
```

Required metadata fields used by the checker:

| Field | Type | Use |
|---|---|---|
| `schema_version` | int | Must be `1`. |
| `source_version` | str | Package version, e.g. `0.6.19`. |
| `current_public_release` | str | Current public tag, e.g. `v0.6.19`. |
| `next_planned_release` | str | Next planning tag, e.g. `v0.6.20`. |
| `pypi_published` | bool | Global PyPI publication status. |
| `releases` | list[dict] | Release records with `tag`, `version`, `status`, `github_release`, `pypi_published`, `tag_created`, `github_release_created`. |

If `load_metadata` fails or the file is missing, the checker exits `1`.

## 7. Candidate-chain file discovery

Discover files under `docs/releases/` matching these glob patterns:

- `v*.*.*-candidates.md`
- `v*.*.*-candidates.json`
- `v*.*.*-candidate-selection.md`
- `v*.*.*-plan.md`

For each file, derive the release line from the filename:

```python
import re
_CANDIDATE_FILENAME_RE = re.compile(r"^(v\d+\.\d+\.\d+)-(?:candidates|candidate-selection|plan)\.(md|json)$")
```

Group discovered files by release line. Only files with sane version-like names are considered; others are ignored.

## 8. JSON validation rules

### 8.1 Modern schema (current)

For `vX.Y.Z-candidates.json` files that contain a `release_line` field and a `candidates` array, validate:

- `release_line` matches the filename-derived release line.
- `status` (if present) is one of: `proposed`, `accepted`, `released`, `deferred`, `rejected`, `superseded`.
- `source_version` (if present) matches metadata `source_version` when the release line is current or next planned.
- `current_public_release` (if present) matches metadata `current_public_release` when the release line is current or next planned.
- `next_planned_release` (if present) matches metadata `next_planned_release` when the release line is current or next planned.
- `pypi_published` (if present) matches metadata `pypi_published`.
- `tag_created` must not be `true` for the next planned release.
- `github_release_created` must not be `true` for the next planned release.
- Candidate `id` values are unique within the release line.
- Candidate `status` is in the allowed set.
- Candidate `acceptance_verdict` (if present) is in: `PASS`, `FAIL`, `PENDING`, `WITHDRAWN`, `PASS_WITH_WARNINGS`, `DEFERRED`.
- A candidate with `status: released` has `accepted: true` and `acceptance_verdict: PASS`.
- A candidate with `accepted: true` has a non-empty `title`.

Normalization:

- Status values are lowercased before validation.
- Verdict values are uppercased before validation.
- Extra JSON fields are allowed.

### 8.2 Legacy/unknown schema

If a `vX.Y.Z-candidates.json` file lacks a `release_line` field or uses an `artifact_type` field (e.g., `v0.6.1-candidates.json`, `v0.6.13-candidates.json`), perform only lightweight checks:

- Filename-derived release line is sane.
- No `pypi_published: true` if the field exists and metadata says `false`.
- No `released` claim if the release line is the next planned release.
- No forbidden candidate-chain-specific claims in the Markdown counterpart.

Full structural validation is applied only to files following the current schema.

## 9. Markdown scanning rules

### 9.1 Status-line parser

Parse lines matching:

```python
import re
_STATUS_LINE_RE = re.compile(
    r"^[\s\-\*•]*\s*(?P<field>[^:\n]+?)\s*:\s*(?P<value>[^\n]+?)\s*$",
    re.IGNORECASE,
)
```

Normalize field names by lowercasing, stripping markdown emphasis (`*`, `_`, `\``), and collapsing whitespace.

Recognized fields and normalized names:

| Markdown field | Normalized key |
|---|---|
| `Status` | `status` |
| `Release status` | `status` |
| `Candidate status` | `candidate_status` |
| `Acceptance status` | `acceptance_status` |
| `Current public release` | `current_public_release` |
| `Next planned release` | `next_planned_release` |
| `PyPI`, `PyPI published` | `pypi_published` |
| `GitHub Release` | `github_release_created` |
| `Tag created` | `tag_created` |

Boolean normalization for Markdown values:

- `true`, `yes`, `created`, `published` → `True`
- `false`, `no`, `not created`, `not published`, `unpublished` → `False`

### 9.2 Markdown/JSON agreement

When both Markdown and JSON files exist for the same release line:

- `release_line` must agree.
- `status` must agree where both files contain explicit status statements.
- `current_public_release` must agree where present.
- `next_planned_release` must agree where present.
- `pypi_published` must agree where present.

JSON is authoritative. Markdown contradictions fail only when explicit and unambiguous.

### 9.3 Markdown-only rules

- Next planned release Markdown must not claim `released` status.
- Next planned release Markdown must not claim `tag_created: true`.
- Next planned release Markdown must not claim `github_release_created: true`.
- Next planned release Markdown must not claim `pypi_published: true`.
- Current public release Markdown must reference itself as the current public release.

## 10. Forbidden-claim strategy

Define a small, local phrase list inside `scripts/check_candidate_chain.py`.

### 10.1 Candidate-chain-specific phrases

| Category | Phrase patterns (terms that must appear contiguously in the doc) |
|---|---|
| Live-trading readiness | `"live trading ready"`, `"live-ready"`, `"safe to run live"`, `"ready for live trading"` |
| Autonomous live trading | `"autonomous"` + `"live trading"` + `"is implemented"`, `"unattended"` + `"live trading"`, `"direct AI-to-broker execution"` |
| Profitability | `"guaranteed"` + `"profit"`, `"guaranteed"` + `"returns"` |
| Broker endorsement | `"broker endorsed"`, `"broker-approved"` |
| Order submission permission | `"submit orders without approval"`, `"live submit enabled"` |
| PyPI publication | `"pypi published"`, `"published to pypi"` |

### 10.2 Negative-context handling

Allow negative/disclaimer contexts using a line-level negative-indicator check before flagging:

```python
_NEGATIVE_INDICATORS = (
    "not ", "no ", "never", "does not", "do not", "is not", "are not",
    "was not", "unpublished", "not created", "fail closed", "must not",
    "cannot", "without", "prohibited", "forbidden",
)
```

If any negative indicator appears in the same line before the phrase, treat the phrase as allowed. This is intentionally simple and avoids NLP.

### 10.3 Scan scope

Scan only candidate-chain Markdown files:

- `docs/releases/vX.Y.Z-candidates.md`
- `docs/releases/vX.Y.Z-candidate-selection.md`
- `docs/releases/vX.Y.Z-plan.md`

Do not scan `docs/releases/release-metadata.json` or `docs/releases/vX.Y.Z.md` release notes.

## 11. Historical/current/planning release-line derivation

```python
current_public_release = metadata.current_public_release
next_planned_release = metadata.next_planned_release
historical_release_lines = {
    r["tag"] for r in metadata.releases if r.get("status") == "historical"
}
released_release_lines = {current_public_release} | historical_release_lines
planning_release_line = next_planned_release
```

Rules:

- `released` status allowed only for `released_release_lines`.
- `accepted`/`proposed` status allowed for `planning_release_line`.
- Unknown release lines warn, unless they claim released/tag/GitHub Release/PyPI publication status or contradict metadata, in which case they fail.
- Current public release must not appear as planning-only in current metadata.
- Next planned release must not appear as released before cutover.

## 12. Warning vs error policy

| Condition | Severity |
|---|---|
| Contradiction between JSON and metadata | Error (exit `2`) |
| Contradiction between Markdown and JSON | Error (exit `2`) |
| `released` status for next planned release | Error (exit `2`) |
| `pypi_published: true` while metadata says `false` | Error (exit `2`) |
| `tag_created: true` for next planned release | Error (exit `2`) |
| `github_release_created: true` for next planned release | Error (exit `2`) |
| Duplicate candidate ID | Error (exit `2`) |
| Unknown candidate status or verdict | Error (exit `2`) |
| Forbidden candidate-chain-specific claim | Error (exit `2`) |
| Unknown release line without contradictory claims | Warning (no exit `2`) |
| Historical stale successor reference | Warning (no exit `2`) |
| Missing optional `candidate-selection.md` or `plan.md` | None |
| Extra JSON fields | None |

## 13. Expected files

### 13.1 Files to create

| File | Responsibility |
|---|---|
| `scripts/check_candidate_chain.py` | Deterministic candidate-chain consistency checker. |
| `tests/test_candidate_chain.py` | Pytest coverage using temporary fixture repositories. |

### 13.2 Files to modify

| File | Change |
|---|---|
| `scripts/dev_check.sh` | Add `python3.11 scripts/check_candidate_chain.py` after release metadata and version consistency checks. |
| `scripts/ci_check.sh` | Add `python3.11 scripts/check_candidate_chain.py` after release metadata and version consistency checks. |
| `docs/development/checks-reference.md` | Document the new checker under Core Checks. |

### 13.3 Files that must not change

No runtime code, safety module, broker adapter, provider adapter, risk configuration, approval logic, kill-switch logic, deadman logic, heartbeat logic, or audit hash-chain code is touched.

## 14. Test implementation plan

Tests live in `tests/test_candidate_chain.py` and use `tmp_path` fixture trees plus `subprocess.run`.

### Task 1: Test harness helpers

**Files:**
- Create: `tests/test_candidate_chain.py`

- [ ] **Step 1: Define constants and helper to run checker**

```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_candidate_chain.py"


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
```

- [ ] **Step 2: Add helper to build a minimal valid fixture repo**

```python
def _write_metadata(repo: Path) -> None:
    metadata_path = repo / "docs" / "releases" / "release-metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_version": "0.6.19",
                "current_public_release": "v0.6.19",
                "next_planned_release": "v0.6.20",
                "pypi_published": False,
                "release_type": "github_only",
                "releases": [
                    {
                        "tag": "v0.6.19",
                        "version": "0.6.19",
                        "status": "current_public",
                        "github_release": True,
                        "pypi_published": False,
                        "release_type": "github_only",
                        "tag_created": True,
                        "github_release_created": True,
                    },
                    {
                        "tag": "v0.6.18",
                        "version": "0.6.18",
                        "status": "historical",
                        "github_release": True,
                        "pypi_published": False,
                        "release_type": "github_only",
                        "tag_created": True,
                        "github_release_created": True,
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
```

### Task 2: Pass/fail smoke tests

**Files:**
- Modify: `tests/test_candidate_chain.py`

- [ ] **Step 3: Test checker passes on current repo**

```python
def test_checker_passes_on_current_repo() -> None:
    result = _run_checker()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout
```

- [ ] **Step 4: Test valid planning chain passes**

```python
def test_valid_planning_chain_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    candidates_json = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    candidates_json.parent.mkdir(parents=True, exist_ok=True)
    candidates_json.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "source_version": "0.6.19",
                "current_public_release": "v0.6.19",
                "next_planned_release": "v0.6.20",
                "pypi_published": False,
                "candidates": [
                    {
                        "id": "CAND-012",
                        "status": "proposed",
                        "accepted": False,
                        "title": "Candidate-Chain Consistency Guard",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 5: Test valid released chain passes**

```python
def test_valid_released_chain_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    candidates_json = repo / "docs" / "releases" / "v0.6.19-candidates.json"
    candidates_json.parent.mkdir(parents=True, exist_ok=True)
    candidates_json.write_text(
        json.dumps(
            {
                "release_line": "v0.6.19",
                "status": "released",
                "source_version": "0.6.19",
                "current_public_release": "v0.6.19",
                "next_planned_release": "v0.6.20",
                "pypi_published": False,
                "tag_created": True,
                "github_release_created": True,
                "candidates": [
                    {
                        "id": "CAND-011",
                        "status": "released",
                        "accepted": True,
                        "acceptance_verdict": "PASS",
                        "title": "Kill-Switch Type-Safety Cleanup",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

### Task 3: Failure tests

**Files:**
- Modify: `tests/test_candidate_chain.py`

- [ ] **Step 6: Test mismatched Markdown/JSON release line fails**

```python
def test_mismatched_md_json_release_line_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    md = repo / "docs" / "releases" / "v0.6.20-candidates.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# v0.6.20 Release Candidates\n\nStatus: planning\n", encoding="utf-8")
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.write_text(
        json.dumps({"release_line": "v0.6.21", "status": "planning", "candidates": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "release_line" in result.stdout.lower()
```

- [ ] **Step 7: Test duplicate candidate ID fails**

```python
def test_duplicate_candidate_id_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "candidates": [
                    {"id": "CAND-012", "status": "proposed", "accepted": False, "title": "A"},
                    {"id": "CAND-012", "status": "proposed", "accepted": False, "title": "B"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "duplicate" in result.stdout.lower()
```

- [ ] **Step 8: Test unknown candidate status fails**

```python
def test_unknown_candidate_status_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "candidates": [
                    {"id": "CAND-012", "status": "accepted_released", "accepted": False, "title": "A"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "unknown status" in result.stdout.lower()
```

- [ ] **Step 9: Test unknown acceptance verdict fails**

```python
def test_unknown_acceptance_verdict_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "candidates": [
                    {"id": "CAND-012", "status": "accepted", "accepted": True, "acceptance_verdict": "MAYBE", "title": "A"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "unknown verdict" in result.stdout.lower()
```

- [ ] **Step 10: Test next planned release claiming released fails**

```python
def test_next_planned_release_claiming_released_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "released",
                "candidates": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "released" in result.stdout.lower()
```

- [ ] **Step 11: Test next planned release claiming tag created fails**

```python
def test_next_planned_release_tag_created_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "tag_created": True,
                "candidates": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "tag_created" in result.stdout.lower()
```

- [ ] **Step 12: Test PyPI mismatch fails**

```python
def test_pypi_mismatch_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "pypi_published": True,
                "candidates": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "pypi" in result.stdout.lower()
```

- [ ] **Step 13: Test forbidden live-trading claim fails**

```python
def test_forbidden_live_trading_claim_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    md = repo / "docs" / "releases" / "v0.6.20-candidates.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# v0.6.20 Release Candidates\n\nStatus: planning\n\nThis release is live trading ready.\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 2
    assert "live trading ready" in result.stdout.lower()
```

- [ ] **Step 14: Test negative-context forbidden phrases pass**

```python
def test_negative_context_forbidden_phrases_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    md = repo / "docs" / "releases" / "v0.6.20-candidates.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# v0.6.20 Release Candidates\n\nStatus: planning\n\nThis release is not live trading ready. PyPI is not published.\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

### Task 4: Edge-case and safety tests

**Files:**
- Modify: `tests/test_candidate_chain.py`

- [ ] **Step 15: Test historical released candidate passes**

```python
def test_historical_released_candidate_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.18-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.18",
                "status": "released",
                "candidates": [
                    {"id": "CAND-010", "status": "released", "accepted": True, "acceptance_verdict": "PASS", "title": "A"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 16: Test accepted candidate in next planned release passes**

```python
def test_accepted_candidate_in_next_release_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "release_line": "v0.6.20",
                "status": "planning",
                "candidates": [
                    {"id": "CAND-012", "status": "accepted", "accepted": True, "acceptance_verdict": "PASS", "title": "A"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 17: Test missing optional docs passes**

```python
def test_missing_optional_selection_doc_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.20-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {"release_line": "v0.6.20", "status": "planning", "candidates": []},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 18: Test unknown schema with extra keys warns or passes**

```python
def test_unknown_schema_extra_keys_warn_or_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_metadata(repo)
    json_path = repo / "docs" / "releases" / "v0.6.1-candidates.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "artifact_type": "v061_patch_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.1",
                "candidates": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_checker(str(repo))
    assert result.returncode in (0, 2), result.stdout + result.stderr
```

- [ ] **Step 19: Test exit 1 for missing metadata**

```python
def test_exit_1_for_missing_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    result = _run_checker(str(repo))
    assert result.returncode == 1
```

- [ ] **Step 20: Test checker imports no network/credential/runtime modules**

```python
def test_no_network_calls_in_checker() -> None:
    text = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "import requests" not in text
    assert "import urllib" not in text
    assert "import httpx" not in text
    assert "import socket" not in text


def test_no_credential_loading_in_checker() -> None:
    text = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "load_dotenv" not in text
    assert "os.environ" not in text
    assert "environ[" not in text
    assert "getenv(" not in text
```

## 15. Dev/CI integration plan

### Task 5: Add checker to `scripts/dev_check.sh`

**Files:**
- Modify: `scripts/dev_check.sh`

- [ ] **Step 21: Insert candidate-chain consistency check after version consistency**

After the `1. version consistency` block in `scripts/dev_check.sh`, add:

```bash
echo ""
echo "1b. candidate-chain consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_candidate_chain.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Rationale: candidate-chain consistency is a release-governance gate that depends on release metadata and version consistency already being valid. It is fast (< 1 s) and has no network or credential dependencies.

### Task 6: Add checker to `scripts/ci_check.sh`

**Files:**
- Modify: `scripts/ci_check.sh`

- [ ] **Step 22: Insert candidate-chain consistency check after version consistency in CI**

After the `1. version consistency` block in `scripts/ci_check.sh`, add the same block as Step 21.

### Task 7: Update checks reference

**Files:**
- Modify: `docs/development/checks-reference.md`

- [ ] **Step 23: Add CAND-012 to Core Checks list**

Under `## Core Checks`, add:

```markdown
- `scripts/check_candidate_chain.py` validates that release-metadata,
  candidate-chain Markdown, and candidate-chain JSON agree on release identity,
  candidate status, acceptance verdicts, PyPI status, tag-created status, and
  GitHub-release-created status. It also scans candidate-chain docs for
  candidate-chain-specific premature-release and live-trading claims.
```

## 16. Verification matrix

After implementation, the following verification commands must pass:

| Step | Command | Expected |
|---|---|---|
| 1 | `python3.11 scripts/check_candidate_chain.py` | Exit `0`, summary contains `PASSED` |
| 2 | `python3.11 -m pytest tests/test_candidate_chain.py -q` | Exit `0`, all tests pass |
| 3 | `python3.11 scripts/check_release_metadata.py` | PASSED |
| 4 | `python3.11 scripts/check_version_consistency.py` | PASSED |
| 5 | `python3.11 scripts/check_forbidden_claims.py` | clean |
| 6 | `python3.11 scripts/check_bounded_autonomy_governance.py` | PASSED |
| 7 | `python3.11 scripts/check_trust_center.py` | PASSED |
| 8 | `python3.11 scripts/check_onboarding_docs.py` | PASSED |
| 9 | `python3.11 scripts/check_public_launch_readiness.py` | PASSED |
| 10 | `python3.11 scripts/check_cli_command_compatibility.py` | PASSED |
| 11 | `python3.11 scripts/check_safety_atomic_write.py` | PASSED |
| 12 | `mypy src/atlas_agent/safety/kill_switch.py` | zero issues |
| 13 | `atlas validate` | success |
| 14 | `atlas run --mode live` | Exit `2` |
| 15 | `bash scripts/dev_check.sh` | All steps pass (or candidate-chain step in isolation if full script times out) |
| 16 | `bash scripts/ci_check.sh` | All steps pass (or candidate-chain step in isolation if full script times out) |
| 17 | `bash scripts/release_check.sh --quick` | PASSED |
| 18 | `git diff --check` | clean |

## 17. Safety and release invariants

CAND-012 preserves every safety and release boundary:

- **No live trading enabled:** The checker is read-only.
- **No live submit enabled:** No execution path is touched.
- **No order placement, cancellation, or flattening:** The checker does not interact with orders.
- **No pending-order creation:** The checker does not create files outside temporary test fixtures.
- **No approval queue mutation:** No runtime state is mutated.
- **No broker calls:** No broker modules are imported or executed.
- **No provider calls:** No provider modules are imported or executed.
- **No credential loading:** The checker does not read environment variables, `.env` files, or secrets.
- **No network access:** Standard-library file I/O only.
- **RiskManager is not weakened:** Risk code is untouched.
- **No kill-switch, deadman, or heartbeat weakening:** Safety modules are untouched.
- **No audit hash-chain bypass:** Audit code is untouched.
- **`atlas run --mode live` exits `2`:** No runtime change affects this.
- **Package version remains `0.6.19`:** The checker does not bump version.
- **Current public release remains `v0.6.19`:** The checker validates but does not alter release claims.
- **Next planned release remains `v0.6.20`:** The checker enforces this metadata value.
- **PyPI remains unpublished:** The checker rejects any claim that PyPI is published while metadata says otherwise.
- **No `v0.6.20` tag or GitHub Release:** The checker rejects premature tag/release-created claims for the next planned release.

## 18. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| False positives on historical schemas | Could break existing historical docs. | Handle pre-current schemas permissively; only validate fields that exist; use warnings, not failures, for historical inconsistencies. |
| Duplication of forbidden-claims logic | Two scanners could drift. | Keep the candidate-chain phrase list small and stable; rely on `check_forbidden_claims.py` for general safety/profit wording. |
| Overly strict Markdown parsing | Legitimate prose could be flagged. | Parse only explicit status lines; make JSON authoritative; allow negative contexts. |
| Checker becomes slow | Could exceed the < 1 s target. | Only scan files under `docs/releases/`; skip deep content parsing. |
| Coupling to release-metadata.json schema | Future metadata changes could break the checker. | Use `ReleaseMetadata` helper; fail gracefully on missing expected fields. |
| Accidental runtime import | Could pull in `atlas_agent`. | Code review + tests assert no `import atlas_agent` in checker source. |

## 19. Rollback plan

Because CAND-012 is docs/checker/test-only, rollback is straightforward:

1. Revert or delete `scripts/check_candidate_chain.py` and `tests/test_candidate_chain.py`.
2. Revert the additions to `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `docs/development/checks-reference.md`.
3. Run the verification matrix to confirm no safety boundary or release state changed.
4. No runtime state, tags, releases, or packages are affected.

## 20. Acceptance criteria

CAND-012 is accepted when:

1. This implementation plan is reviewed and approved.
2. `scripts/check_candidate_chain.py` is implemented according to this plan.
3. `tests/test_candidate_chain.py` covers all required test cases and passes.
4. The checker runs successfully on the current repository with exit code `0`.
5. The checker is integrated into `scripts/dev_check.sh` and `scripts/ci_check.sh`.
6. `docs/development/checks-reference.md` documents the checker.
7. All verification commands in Section 16 continue to pass.
8. `atlas run --mode live` continues to exit `2`.
9. No runtime, safety, broker, provider, risk, approval, kill-switch, deadman, heartbeat, or audit hash-chain code is modified.
10. No version bump, tag, GitHub Release, or PyPI publication occurs as part of this candidate.

## 21. Implementation-readiness verdict

**Verdict:** `READY_FOR_IMPLEMENTATION`

Rationale:

- The checker scope is bounded and well-defined.
- Existing patterns (`scripts/check_release_metadata.py`, `scripts/check_safety_atomic_write.py`, `scripts/check_forbidden_claims.py`, `scripts/check_trust_center.py`) provide clear conventions.
- The four independent design-review warnings have been incorporated into the plan.
- The permissiveness/false-positive policy is explicit and conservative.
- No runtime changes are required.
- Test cases, dev/CI integration steps, and verification commands are concrete.
