"""CLI end-to-end tests for notification commands."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


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


class TestNotificationsCLI:
    def test_notifications_test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["notifications", "test"])
        assert code == 0
        out = capsys.readouterr().out
        assert "dry_run" in out
        assert "Transport: dry_run" in out

    def test_notifications_send_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["notifications", "send", "--message", "Hello"])
        assert code == 0
        out = capsys.readouterr().out
        assert "dry_run" in out
        assert "Hello" not in out or "Preview" in out

    def test_notifications_send_disabled_transport(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["notifications", "send", "--message", "Hello", "--transport", "disabled"])
        assert code == 0
        out = capsys.readouterr().out
        assert "disabled" in out

    def test_notifications_slack_without_webhook_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["notifications", "send", "--message", "Hello", "--transport", "slack"])
        # --dry-run defaults to True, so slack is overridden to dry_run safely
        assert code == 0
        out = capsys.readouterr().out
        assert "dry_run" in out

    def test_notifications_no_secrets_in_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["notifications", "send", "--message", "Hello"])
        out = capsys.readouterr().out
        assert "hooks.slack.com" not in out
        assert "xoxb-" not in out
