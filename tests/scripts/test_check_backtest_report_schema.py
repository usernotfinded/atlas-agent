import json
import subprocess
import sys
from pathlib import Path

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


def test_all_valid_reports(tmp_path: Path):
    _write_report(tmp_path, "run-a", _valid_report("run-a"))
    _write_report(tmp_path, "run-b", _valid_report("run-b"))
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 0
    assert "OK   " in result.stdout
    assert "valid=2" in result.stdout
    assert "invalid=0" in result.stdout


def test_invalid_report_fails(tmp_path: Path):
    invalid = _valid_report("invalid-run")
    invalid["status"] = "bogus"
    _write_report(tmp_path, "invalid-run", invalid)
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 1
    assert "FAIL " in result.stdout
    assert "invalid=" in result.stdout


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


def test_unreadable_report_fails(tmp_path: Path):
    _write_report(tmp_path, "broken-run", "not json {{\n")
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 1
    assert "unreadable=1" in result.stdout


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


def test_json_output(tmp_path: Path):
    _write_report(tmp_path, "valid-run", _valid_report("valid-run"))
    _write_report(tmp_path, "legacy-run", {"legacy": True})
    result = _run(["--root", str(tmp_path), "--json"])
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["counts"]["valid"] == 1
    assert data["counts"]["legacy"] == 1
    assert data["counts"]["invalid"] == 0
    assert data["counts"]["unreadable"] == 0
    assert "skipped" not in data["counts"]
    assert "reports" in data
    assert "errors" in data
    assert data["errors"] == []


def test_json_determinism(tmp_path: Path):
    _write_report(tmp_path, "b-run", _valid_report("b-run"))
    _write_report(tmp_path, "a-run", _valid_report("a-run"))
    first = _run(["--root", str(tmp_path), "--json"]).stdout
    second = _run(["--root", str(tmp_path), "--json"]).stdout
    assert first == second
    data = json.loads(first)
    paths = [r["path"] for r in data["reports"]]
    assert paths == sorted(paths)


def test_missing_root(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    result = _run(["--root", str(missing)])
    assert result.returncode == 0
    assert "total=0" in result.stdout


def test_empty_root(tmp_path: Path):
    result = _run(["--root", str(tmp_path)])
    assert result.returncode == 0
    assert "total=0" in result.stdout
