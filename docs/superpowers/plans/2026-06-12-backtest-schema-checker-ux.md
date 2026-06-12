# Backtest Schema Checker UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `scripts/check_backtest_report_schema.py` ergonomics with `--json`, deterministic per-status counts, `--fail-on-legacy`, a clearer human summary, and direct unit tests, while keeping default behavior backward-compatible.

**Architecture:** Refactor the checker to use existing schema helpers (`get_schema_validation_result`, `unreadable_schema_result`), classify every scanned report into one of `valid/invalid/legacy/unreadable`, and emit either a deterministic human summary or a stable JSON envelope. Add an opt-in `--fail-on-legacy` flag and a `--root` override for isolated tests. Cover all report states with synthetic fixtures in a new test file.

**Tech Stack:** Python 3.11+, `argparse`, `json`, `pathlib`, `pytest`/`tmp_path`, existing `atlas_agent.backtest.report_schema` helpers.

---

## Task 1: Refactor `scripts/check_backtest_report_schema.py`

**Files:**
- Modify: `scripts/check_backtest_report_schema.py`

- [ ] **Step 1: Add argparse CLI with `--json`, `--fail-on-legacy`, `--root`**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check backtest report schema compliance."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary.",
    )
    parser.add_argument(
        "--fail-on-legacy",
        action="store_true",
        help="Treat legacy reports as failures.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(".atlas/backtests"),
        help="Root directory to scan (default: .atlas/backtests).",
    )
    return parser
```

- [ ] **Step 2: Refactor scanning logic to classify reports into structured results**

For each `*/result.json` under the root (sorted deterministically):

1. Try to load JSON.
2. On `json.JSONDecodeError` or any other read/parse exception, build result via `unreadable_schema_result(f"unreadable: {exc}")`.
3. Otherwise, build result via `get_schema_validation_result(data)`.
4. Increment one of `valid/invalid/legacy/unreadable` counts.

```python
from atlas_agent.backtest.report_schema import (
    SchemaValidationResult,
    get_schema_validation_result,
    unreadable_schema_result,
)

STATUS_COUNTS = {"valid": 0, "invalid": 0, "legacy": 0, "unreadable": 0}


def check_reports(root: Path) -> dict:
    report_paths = sorted(root.glob("*/result.json")) if root.exists() else []
    reports = []
    counts = dict(STATUS_COUNTS)

    for path in report_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            result = unreadable_schema_result(f"unreadable: {exc}")
        else:
            result = get_schema_validation_result(data)

        status = result.status
        if status == "valid":
            counts["valid"] += 1
        elif status == "legacy":
            counts["legacy"] += 1
        elif status == "unreadable":
            counts["unreadable"] += 1
        elif status.startswith("invalid"):
            counts["invalid"] += 1

        reports.append({
            "path": str(path),
            "status": status,
            "schema_version": result.schema_version,
            "valid": result.valid,
            "error": result.error,
            "errors": result.errors,
        })

    errors = [r for r in reports if not r["valid"]]
    return {
        "ok": counts["invalid"] == 0 and counts["unreadable"] == 0,
        "root": str(root),
        "total": len(report_paths),
        "counts": counts,
        "reports": reports,
        "errors": errors,
    }
```

- [ ] **Step 3: Implement deterministic human summary output**

Default text mode must remain backward-compatible in spirit:
- Valid reports print `OK   <path>`.
- Invalid reports print `FAIL <path>: <first error>` and indented additional errors if >1.
- Unreadable reports print `UNREADABLE <path>: <error>`.
- Legacy reports are silent by default (matching current behavior).
- Final summary shows deterministic counts.

```python
def print_text_summary(result: dict, fail_on_legacy: bool) -> None:
    counts = result["counts"]
    for report in result["reports"]:
        status = report["status"]
        path = report["path"]
        if status == "valid":
            print(f"OK   {path}")
        elif status.startswith("invalid"):
            print(f"FAIL {path}: {report['error']}")
            errors = report.get("errors") or []
            for err in errors[1:]:
                print(f"      {err}")
        elif status == "unreadable":
            print(f"UNREADABLE {path}: {report['error']}")

    overall = "passed" if result["ok"] and not (fail_on_legacy and counts["legacy"] > 0) else "failed"
    print(
        f"\nSchema check {overall}: "
        f"total={result['total']} "
        f"valid={counts['valid']} "
        f"invalid={counts['invalid']} "
        f"legacy={counts['legacy']} "
        f"unreadable={counts['unreadable']}"
    )
```

- [ ] **Step 4: Implement deterministic `--json` output**

JSON shape (stable, sorted keys, sorted arrays):

```json
{
  "ok": true,
  "root": ".atlas/backtests",
  "total": 1536,
  "counts": {
    "valid": 107,
    "legacy": 1429,
    "invalid": 0,
    "unreadable": 0
  },
  "reports": [
    {
      "path": ".atlas/backtests/example/result.json",
      "status": "valid",
      "schema_version": "backtest.report.v1",
      "valid": true,
      "error": null,
      "errors": null
    }
  ],
  "errors": []
}
```

```python
if args.json:
    output = {
        "ok": ok,
        "root": str(args.root),
        "total": result["total"],
        "counts": result["counts"],
        "reports": sorted(result["reports"], key=lambda r: r["path"]),
        "errors": sorted(result["errors"], key=lambda r: r["path"]),
    }
    print(json.dumps(output, sort_keys=True, indent=2))
```

- [ ] **Step 5: Implement exit-code matrix**

```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = check_reports(args.root)
    counts = result["counts"]
    ok = result["ok"] and not (args.fail_on_legacy and counts["legacy"] > 0)

    if args.json:
        output = {
            "ok": ok,
            "root": str(args.root),
            "total": result["total"],
            "counts": counts,
            "reports": sorted(result["reports"], key=lambda r: r["path"]),
            "errors": sorted(result["errors"], key=lambda r: r["path"]),
        }
        print(json.dumps(output, sort_keys=True, indent=2))
    else:
        print_text_summary(result, args.fail_on_legacy)

    return 0 if ok else 1
```

Exit codes:
- Default: `0` if `invalid == 0` and `unreadable == 0`; otherwise `1`.
- `--fail-on-legacy`: additionally returns `1` if `legacy > 0`.

- [ ] **Step 6: Verify the script still runs clean on the real `.atlas/backtests` tree**

Run:
```bash
python scripts/check_backtest_report_schema.py
python scripts/check_backtest_report_schema.py --json
```
Expected: exit `0` and deterministic output for the current repo state.

---

## Task 2: Add checker unit tests

**Files:**
- Create: `tests/scripts/test_check_backtest_report_schema.py`

- [ ] **Step 1: Create fixture helpers**

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_backtest_report_schema.py"


def _write_report(root: Path, run_id: str, data: dict | str) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"
    if isinstance(data, str):
        result_path.write_text(data, encoding="utf-8")
    else:
        result_path.write_text(json.dumps(data), encoding="utf-8")
    return result_path


def _valid_report(run_id: str = "valid-run") -> dict:
    return {
        "schema_version": "backtest.report.v1",
        "run_id": run_id,
        "status": "completed",
        "report_type": "backtest_research_summary",
        "config": {
            "run_id": run_id,
            "symbol": "DEMO",
            "data_path": "data.csv",
            "initial_equity": 10000.0,
            "strategy_mode": "paper",
        },
        "metrics": {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "trade_count": 0,
            "final_equity": 10000.0,
            "initial_equity": 10000.0,
        },
        "strategy_metadata": {"strategy_id": "buy_and_hold"},
        "fills": [],
        "equity_curve": [{"timestamp": "2024-01-01", "equity": 10000.0}],
        "diagnostics": {},
        "generated_at": "2024-01-01T00:00:00",
        "disclaimer": "Not financial advice.",
    }


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
```

- [ ] **Step 2: Test valid-only set**

```python
def test_all_valid_reports(tmp_path: Path):
    _write_report(tmp_path, "run-a", _valid_report("run-a"))
    _write_report(tmp_path, "run-b", _valid_report("run-b"))
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 0
    assert "OK   " in result.stdout
    assert "valid=2" in result.stdout
    assert "invalid=0" in result.stdout
```

- [ ] **Step 3: Test invalid report**

```python
def test_invalid_report_fails(tmp_path: Path):
    invalid = _valid_report("invalid-run")
    invalid["status"] = "bogus"
    _write_report(tmp_path, "invalid-run", invalid)
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 1
    assert "FAIL " in result.stdout
    assert "invalid=" in result.stdout
```

- [ ] **Step 4: Test legacy report default vs `--fail-on-legacy`**

```python
def test_legacy_report_skipped_by_default(tmp_path: Path):
    legacy = {"some": "legacy"}
    _write_report(tmp_path, "legacy-run", legacy)
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 0
    assert "legacy=1" in result.stdout


def test_legacy_report_fails_with_flag(tmp_path: Path):
    legacy = {"some": "legacy"}
    _write_report(tmp_path, "legacy-run", legacy)
    result = _run(["--root", str(tmp_path), "--fail-on-legacy"])
    assert result.returncode == 1
    assert "legacy=1" in result.stdout
```

- [ ] **Step 5: Test unreadable report**

```python
def test_unreadable_report_fails(tmp_path: Path):
    _write_report(tmp_path, "broken-run", "not json {{")
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 1
    assert "unreadable=1" in result.stdout
```

- [ ] **Step 6: Test mixed set**

```python
def test_mixed_reports(tmp_path: Path):
    _write_report(tmp_path, "valid-run", _valid_report("valid-run"))
    invalid = _valid_report("invalid-run")
    invalid["report_type"] = "wrong"
    _write_report(tmp_path, "invalid-run", invalid)
    _write_report(tmp_path, "legacy-run", {"legacy": True})
    _write_report(tmp_path, "broken-run", "bad json")
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 1
    assert "valid=1" in result.stdout
    assert "invalid=1" in result.stdout
    assert "legacy=1" in result.stdout
    assert "unreadable=1" in result.stdout
```

- [ ] **Step 7: Test `--json` output shape and determinism**

```python
def test_json_output(tmp_path: Path):
    _write_report(tmp_path, "valid-run", _valid_report("valid-run"))
    _write_report(tmp_path, "legacy-run", {"legacy": True})
    result = _run(["--root", str(tmp_path), "--json"])
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["counts"]["valid"] == 1
    assert data["counts"]["legacy"] == 1
    assert "reports" in data
    assert "errors" in data


def test_json_determinism(tmp_path: Path):
    _write_report(tmp_path, "b-run", _valid_report("b-run"))
    _write_report(tmp_path, "a-run", _valid_report("a-run"))
    first = _run(["--root", str(tmp_path), "--json"]).stdout
    second = _run(["--root", str(tmp_path), "--json"]).stdout
    assert first == second
```

- [ ] **Step 8: Test missing/empty root**

```python
def test_missing_root(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    result = _run(["--root", str(missing)])
    assert result.returncode == 0
    assert "total=0" in result.stdout
```

- [ ] **Step 9: Run new tests and confirm pass**

```bash
python -m pytest tests/scripts/test_check_backtest_report_schema.py -v
```
Expected: all tests pass.

---

## Task 3: Update candidate tracking and docs

**Files:**
- Modify: `docs/releases/v0.6.10-candidates.md`
- Modify: `docs/releases/v0.6.10-candidates.json`
- Modify: `docs/backtesting/report-schema.md`

- [ ] **Step 1: Mark CAND-003 implemented in Markdown**

Change the CAND-003 row in the accepted-candidates table from `**not yet implemented**` to `**implemented**`.

- [ ] **Step 2: Mark CAND-003 implemented in JSON**

Set `"implemented": true` on the CAND-003 candidate object in `docs/releases/v0.6.10-candidates.json`.

- [ ] **Step 3: Document new CLI flags in `docs/backtesting/report-schema.md`**

Add a short section after the existing `atlas backtest runs --validate --json` documentation:

```markdown
### Standalone schema checker

```bash
python scripts/check_backtest_report_schema.py
python scripts/check_backtest_report_schema.py --json
python scripts/check_backtest_report_schema.py --fail-on-legacy
```

- `--json` emits a deterministic JSON summary with per-status counts (`valid`, `invalid`, `legacy`, `unreadable`).
- `--fail-on-legacy` exits non-zero when legacy reports are present.
- `--root <path>` scans a custom directory (useful for tests).
```

- [ ] **Step 4: Run planning checker**

```bash
python scripts/check_v0610_planning.py
python -m pytest tests/test_check_v0610_planning.py -q
```
Expected: pass.

---

## Task 4: Run validation gates

- [ ] **Step 1: Run targeted check scripts**

```bash
python scripts/check_release_metadata.py
python scripts/check_version_consistency.py
python scripts/check_trust_center.py
python scripts/check_public_docs_consistency.py
python scripts/check_reviewer_onboarding.py
python scripts/check_reviewer_outreach.py
python scripts/check_backtest_report_schema.py
python scripts/check_backtest_report_schema.py --json
python scripts/check_v0610_planning.py
python scripts/check_template_parity.py
python scripts/check_env_templates.py
python -m compileall src
```

- [ ] **Step 2: Run targeted tests**

```bash
python -m pytest tests/test_check_v0610_planning.py -q
python -m pytest tests/backtest/test_backtest_report_schema.py -q
python -m pytest tests/scripts/test_check_backtest_report_schema.py -q
python -m pytest tests -k "backtest_report_schema or schema_checker or check_backtest_report_schema" -q
```

- [ ] **Step 3: Run full gates**

```bash
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
./scripts/research_check.sh
```

- [ ] **Step 4: Inspect failures, fix real issues, re-run failed gates**

Do not skip tests or weaken assertions.

---

## Task 5: Commit, push, and verify CI

- [ ] **Step 1: Artifact hygiene**

```bash
git status --short
git diff --name-only
```
Stage only intentional checker/test/docs files. Remove any temporary analysis files.

- [ ] **Step 2: Commit**

```bash
git add scripts/check_backtest_report_schema.py tests/scripts/test_check_backtest_report_schema.py docs/releases/v0.6.10-candidates.md docs/releases/v0.6.10-candidates.json docs/backtesting/report-schema.md
git commit -m "feat: improve backtest schema checker UX"
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Verify CI green**

```bash
gh run list --repo usernotfinded/atlas-agent --branch main --limit 10
gh run watch --repo usernotfinded/atlas-agent
```

If CI fails, inspect logs, fix the real issue, re-run local checks, commit/push, and watch again.
