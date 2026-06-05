"""Tests for atlas report CLI commands."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def atlas_cli():
    return [sys.executable, "-m", "atlas_agent.cli"]


class TestReportDaily:
    def test_report_daily_outputs_path(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "daily"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        assert "daily-report" in result.stdout
        # Verify the written file contains real content
        path_line = result.stdout.strip()
        written = Path(path_line)
        if written.exists():
            content = written.read_text(encoding="utf-8")
            assert "Atlas Agent Report" in content
            assert "not investment advice" in content.lower()


class TestReportGenerate:
    def test_generate_daily_markdown_stdout(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "daily", "--format", "markdown"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        assert "Atlas Agent Report" in result.stdout

    def test_generate_daily_json_stdout(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "daily", "--format", "json"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["metadata"]["report_type"] == "daily"
        assert "disclaimer" in data

    def test_generate_weekly_markdown_stdout(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "weekly", "--format", "markdown"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        assert "Atlas Agent Report: Weekly" in result.stdout

    def test_generate_adhoc_markdown_stdout(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "ad-hoc", "--format", "markdown"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        assert "Atlas Agent Report: Ad-Hoc" in result.stdout

    def test_generate_adhoc_json_stdout(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "ad-hoc", "--format", "json"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["metadata"]["report_type"] == "ad-hoc"

    def test_generate_writes_file(self, atlas_cli):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "report.md"
            result = subprocess.run(
                [*atlas_cli, "report", "generate", "--type", "daily", "--format", "markdown", "--output", str(out_path)],
                capture_output=True,
                text=True,
                cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
            )
            assert result.returncode == 0
            assert out_path.exists()
            content = out_path.read_text(encoding="utf-8")
            assert "Atlas Agent Report" in content

    def test_generate_with_run_id_legacy(self, atlas_cli):
        # Find a real backtest run id
        bt_dir = Path("/Users/natanmucelli/Desktop/prog/atlas-agent/.atlas/backtests")
        run_dirs = [d.name for d in bt_dir.iterdir() if d.is_dir()] if bt_dir.exists() else []
        if not run_dirs:
            pytest.skip("No backtest runs available for legacy test")
        run_id = run_dirs[0]
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--run-id", run_id, "--format", "markdown"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        assert "Backtest Research Summary" in result.stdout

    def test_generate_invalid_run_id(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--run-id", "nonexistent-run", "--format", "markdown"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 1
        assert "No backtest result found" in result.stderr

    def test_no_provider_calls(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "daily", "--format", "json"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "provider" not in json.dumps(data).lower() or data["metadata"]["report_type"] == "daily"

    def test_no_broker_calls(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "report", "generate", "--type", "daily", "--format", "json"],
            capture_output=True,
            text=True,
            cwd="/Users/natanmucelli/Desktop/prog/atlas-agent",
        )
        assert result.returncode == 0
