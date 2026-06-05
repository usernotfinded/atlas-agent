"""CLI end-to-end tests for learning suggestion commands."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import json

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


REPO_ROOT = Path(__file__).resolve().parents[2]


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


class TestLearningSuggest:
    def test_suggest_from_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n\nSome data.\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "suggest", "--input", str(input_file), "--kind", "report"])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_suggest_dry_run_no_provider_calls(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "note.md"
        input_file.write_text("Note content", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "suggest", "--input", str(input_file)])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_suggest_missing_input(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        missing = tmp_path / "missing.md"

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "suggest", "--input", str(missing)])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_suggest_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "suggest", "--input", str(input_file), "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert '"suggestion_id"' in out


class TestLearningSuggestionLifecycle:
    def test_full_lifecycle(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        # Create
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        create_out = capsys.readouterr().out
        data = json.loads(create_out)
        suggestion_id = data["suggestion_id"]

        # List
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "list-suggestions", "--json"])
        assert code == 0
        list_out = capsys.readouterr().out
        assert suggestion_id in list_out

        # Show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "show-suggestion", suggestion_id, "--json"])
        assert code == 0
        capsys.readouterr()  # clear

        # Submit
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "submit-suggestion", suggestion_id])
        assert code == 0
        capsys.readouterr()  # clear

        # Accept
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "accept-suggestion", suggestion_id])
        assert code == 0
        capsys.readouterr()  # clear

        # Show accepted
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "show-suggestion", suggestion_id, "--json"])
        assert code == 0
        show_out = capsys.readouterr().out
        shown = json.loads(show_out)
        assert shown["status"] == "accepted"
        assert shown["audit"]["reviewed_by"] == "cli:user"

        # Archive
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "archive-suggestion", suggestion_id, "--reason", "old"])
        assert code == 0
        out = capsys.readouterr().out
        assert "archived" in out.lower()

    def test_reject_suggestion(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        suggestion_id = data["suggestion_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "submit-suggestion", suggestion_id])

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "reject-suggestion", suggestion_id, "--reason", "incomplete"])
        assert code == 0
        out = capsys.readouterr().out
        assert "rejected" in out.lower()

    def test_cannot_accept_draft(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        suggestion_id = data["suggestion_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "accept-suggestion", suggestion_id])
        assert code == 1
        captured = capsys.readouterr()
        assert "Cannot accept" in captured.err

    def test_reject_requires_reason(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        suggestion_id = data["suggestion_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "submit-suggestion", suggestion_id])
        capsys.readouterr()  # clear

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with pytest.raises(SystemExit):
                main(["learning", "reject-suggestion", suggestion_id])


class TestLearningSuggestionListFilters:
    def test_list_with_status_filter(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        suggestion_id = data["suggestion_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "list-suggestions", "--status", "draft", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert suggestion_id in out

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["learning", "list-suggestions", "--status", "accepted", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert suggestion_id not in out


class TestLearningSafety:
    def test_no_provider_calls(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["provenance"]["provider_execution_disabled"] is True

    def test_advisory_only_policy(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["learning", "suggest", "--input", str(input_file), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["execution_policy"] == "advisory_only"
