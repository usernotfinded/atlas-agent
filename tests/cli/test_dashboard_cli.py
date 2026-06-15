"""CLI end-to-end tests for dashboard commands."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _isolate_dashboard_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def _write_backtest_result(tmp_path: Path) -> None:
    run_dir = tmp_path / ".atlas" / "backtests" / "run1"
    run_dir.mkdir(parents=True)
    result = {
        "run_id": "run1",
        "status": "completed",
        "config": {"symbol": "AAPL"},
        "metrics": {"total_return_pct": 5.2},
    }
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")


class TestDashboardCLI:
    def test_dashboard_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["dashboard", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert '"workspace"' in out
        assert '"dashboard_mode"' in out
        assert '"read_only"' in out
        assert '"system_health"' in out

    def test_dashboard_markdown_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        _write_backtest_result(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["dashboard", "--format", "markdown"])
        assert code == 0
        out = capsys.readouterr().out
        assert "# Atlas Agent Dashboard" in out
        assert "## System Health" in out
        assert "**Export Timestamp:**" in out
        assert "| Metric | Value |" in out
        assert "| :--- | ---: |" in out
        assert "This dashboard is read-only" in out

    def test_dashboard_html_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        _write_backtest_result(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["dashboard"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Dashboard generated" in out
        html_path = tmp_path / ".atlas" / "dashboard" / "index.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Atlas Agent Dashboard" in html
        assert "Export timestamp:" in html
        assert '<table class="summary-table">' in html
        assert "Safety status:" in html
        assert "This dashboard is read-only." in html
        assert "This dashboard does not execute trades." in html
        assert "This dashboard does not call providers or brokers." in html
        assert "This dashboard is not financial advice." in html
        assert "Missing Data" in html
        assert "Warnings" in html
        assert "<form" not in html.lower()
        assert "<button" not in html.lower()
        assert "<script" not in html.lower()
        assert "cdn." not in html.lower()

    def test_dashboard_no_mutation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["dashboard", "--json"])
        out = capsys.readouterr().out
        assert "read_only" in out
        # Ensure no new dirs outside .atlas were created
        assert not (tmp_path / "memory" / "portfolio.md").exists()
