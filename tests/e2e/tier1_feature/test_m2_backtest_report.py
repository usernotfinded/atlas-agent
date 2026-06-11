"""E2E tier1 tests for backtest and report CLI commands.

These tests exercise the 'atlas backtest run' and 'atlas report generate'
CLI commands against the local sample data file (data/sample/ohlcv.csv)
which contains only DEMO-SYMBOL rows.

No network calls. No real credentials. No provider or broker API calls.
"""
import json
import os
import subprocess
import tempfile

import pytest

from atlas_agent.backtest.report_schema import REPORT_SCHEMA_VERSION, validate_backtest_report


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["atlas", *args],
        capture_output=True,
        text=True,
    )


# ─────────────────────── backtest run ────────────────────────


def test_f2_backtest_valid_data():
    """Backtest with valid sample data succeeds."""
    result = _run(
        "backtest", "run",
        "--data", "data/sample/ohlcv.csv",
        "--symbol", "DEMO-SYMBOL",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "Backtest complete" in result.stdout or "backtest result" in result.stdout


def test_f2_backtest_missing_data_file():
    """Backtest with a symbol that has no data rows fails gracefully."""
    result = _run(
        "backtest", "run",
        "--data", "data/sample/ohlcv.csv",
        "--symbol", "NOSUCH-SYM",
    )
    assert result.returncode != 0


def test_f2_backtest_determinism():
    """Two identical backtest runs produce identical stdout output."""
    args = [
        "backtest", "run",
        "--data", "data/sample/ohlcv.csv",
        "--symbol", "DEMO-SYMBOL",
    ]
    run1 = _run(*args)
    run2 = _run(*args)
    assert run1.returncode == 0
    assert run2.returncode == 0
    # Strip run-id and timestamps which change per run
    def _stable(out: str) -> list[str]:
        return [
            line for line in out.strip().splitlines()
            if not line.startswith("Report saved to:")
            and not line.startswith("Markdown saved to:")
            and "bt-" not in line
        ]
    assert _stable(run1.stdout) == _stable(run2.stdout)


def test_f2_backtest_invalid_csv_format():
    """Backtest with a malformed CSV fails gracefully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("invalid,csv,data\n1,2,3\n")
        path = f.name
    try:
        result = _run("backtest", "run", "--data", path, "--symbol", "DEMO-SYMBOL")
        assert result.returncode != 0
    finally:
        os.unlink(path)


# ──────────────── backtest run --report ──────────────────────


def test_f2_backtest_report_json():
    """Backtest with --report json emits valid JSON with disclaimer and schema."""
    result = _run(
        "backtest", "run",
        "--data", "data/sample/ohlcv.csv",
        "--symbol", "DEMO-SYMBOL",
        "--report", "json",
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    data = json.loads(result.stdout)
    assert data["report_type"] == "backtest_research_summary"
    assert data["schema_version"] == REPORT_SCHEMA_VERSION
    assert "disclaimer" in data
    assert "not investment advice" in data["disclaimer"].lower()
    validate_backtest_report(data)


def test_f2_backtest_report_markdown():
    """Backtest with --report markdown emits Markdown with disclaimer."""
    result = _run(
        "backtest", "run",
        "--data", "data/sample/ohlcv.csv",
        "--symbol", "DEMO-SYMBOL",
        "--report", "markdown",
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "# Backtest Research Summary" in result.stdout
    assert "DEMO-SYMBOL" in result.stdout
    assert "not investment advice" in result.stdout.lower()


# ──────────────── atlas report generate ──────────────────────


def test_f3_report_generate_json_format():
    """'atlas report generate --format json' succeeds with empty-data output."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_path = f.name
    try:
        result = _run(
            "report", "generate",
            "--format", "json",
            "--output", output_path,
        )
        assert result.returncode == 0, f"stderr={result.stderr}"
        with open(output_path, "r") as jf:
            data = json.load(jf)
            assert isinstance(data, dict)
            assert "disclaimer" in data
    finally:
        os.unlink(output_path)


def test_f3_report_generate_markdown_format():
    """'atlas report generate --format markdown' succeeds."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        output_path = f.name
    try:
        result = _run(
            "report", "generate",
            "--format", "markdown",
            "--output", output_path,
        )
        assert result.returncode == 0, f"stderr={result.stderr}"
        with open(output_path, "r") as mf:
            content = mf.read()
            assert len(content) > 0
            assert "research summary" in content.lower()
    finally:
        os.unlink(output_path)


def test_f3_report_generate_invalid_format():
    """'atlas report generate' rejects invalid format."""
    result = _run(
        "report", "generate",
        "--format", "pdf",
    )
    assert result.returncode != 0


def test_f3_report_generate_missing_run_id():
    """'atlas report generate --run-id <invalid>' fails with clear error."""
    result = _run(
        "report", "generate",
        "--run-id", "invalid_run_123",
        "--format", "json",
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


def test_f3_report_generate_stdout():
    """'atlas report generate --format text --output stdout' outputs to stdout."""
    result = _run(
        "report", "generate",
        "--format", "text",
        "--output", "stdout",
    )
    assert result.returncode == 0
    assert len(result.stdout.strip()) > 0
    assert "research summary" in result.stdout.lower()
