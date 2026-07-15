# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/cli/test_skills_cli.py
# PURPOSE: Verifies skills cli behavior and regression expectations.
# DEPS:    pathlib, unittest, pytest, json, atlas_agent.
# ==============================================================================

"""CLI end-to-end tests for skill candidate commands."""
# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import json

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parents[2]


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


class TestSkillCandidateCreate:
    def test_create_candidate_from_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n\nSome data.\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "create-candidate", "--input", str(input_file), "--kind", "report"])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_create_candidate_dry_run_no_provider_calls(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "note.md"
        input_file.write_text("Note content", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "create-candidate", "--input", str(input_file)])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_create_candidate_missing_input(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        missing = tmp_path / "missing.md"

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "create-candidate", "--input", str(missing)])
        assert code == 0
        out = capsys.readouterr().out
        assert "created" in out.lower()

    def test_create_candidate_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert '"candidate_id"' in out


class TestSkillCandidateLifecycle:
    def test_full_lifecycle(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        # Create
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        create_out = capsys.readouterr().out
        import json
        data = json.loads(create_out)
        candidate_id = data["candidate_id"]

        # List
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "list-candidates", "--json"])
        assert code == 0
        list_out = capsys.readouterr().out
        assert candidate_id in list_out

        # Show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "show-candidate", candidate_id, "--json"])
        assert code == 0
        show_out = capsys.readouterr().out
        assert candidate_id in show_out

        # Submit
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "submit-candidate", candidate_id])
        assert code == 0

        # Approve
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "approve-candidate", candidate_id])
        assert code == 0

        # Promote
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "promote-candidate", candidate_id])
        assert code == 0
        promote_out = capsys.readouterr().out
        assert "promoted" in promote_out.lower()

        # List library
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "list-library", "--json"])
        assert code == 0
        lib_out = capsys.readouterr().out
        lib_data = json.loads(lib_out)
        assert len(lib_data) == 1
        assert lib_data[0]["source_candidate_id"] == candidate_id

    def test_reject_candidate(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        candidate_id = data["candidate_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "submit-candidate", candidate_id])

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "reject-candidate", candidate_id, "--reason", "incomplete"])
        assert code == 0
        out = capsys.readouterr().out
        assert "rejected" in out.lower()

    def test_archive_candidate(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        candidate_id = data["candidate_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "submit-candidate", candidate_id])
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "approve-candidate", candidate_id])

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "archive-candidate", candidate_id, "--reason", "stale"])
        assert code == 0
        out = capsys.readouterr().out
        assert "archived" in out.lower()

    def test_promote_rejects_non_approved(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        candidate_id = data["candidate_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "promote-candidate", candidate_id])
        assert code == 2
        out = capsys.readouterr().out
        assert "Error" in out


class TestSkillCandidateListFilters:
    def test_list_candidates_filter_by_status(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["skills", "create-candidate", "--input", str(input_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        candidate_id = data["candidate_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "list-candidates", "--status", "draft", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert candidate_id in out

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["skills", "list-candidates", "--status", "approved", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert candidate_id not in out
