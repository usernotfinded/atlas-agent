from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main


def _config(tmp_path: Path):
    from atlas_agent.config import AtlasConfig

    cfg = AtlasConfig(
        workspace_dir=tmp_path,
        data_dir=tmp_path / "data",
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        events_dir=tmp_path / "events",
        reports_dir=tmp_path / "reports",
        pending_orders_dir=tmp_path / "pending_orders",
    )
    return cfg


class TestResearchInvalidSymbolLeakRegression:
    """Ensure invalid symbol errors do not leak raw user input."""

    def test_invalid_symbol_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "/Users/natan/secret", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "invalid_research_symbol"
        assert data["message"] == "Invalid research symbol."
        raw = out.lower()
        assert "/users/" not in raw
        assert "/private/var/" not in raw
        assert "natan" not in raw
        assert "secret" not in raw

    def test_invalid_symbol_text_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "/Users/natan/secret"])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research symbol" in out.lower()
        raw = out.lower()
        assert "/users/" not in raw
        assert "/private/var/" not in raw
        assert "natan" not in raw
        assert "secret" not in raw


class TestResearchUnsupportedProviderLeakRegression:
    """Ensure unsupported provider errors do not leak raw provider strings."""

    def test_unsupported_provider_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "AAPL", "--provider", "sk-LEAKEDSECRET123456", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"
        assert data["message"] == "Unsupported research provider."
        raw = out
        assert "sk-LEAKEDSECRET123456" not in raw
        assert "LEAKEDSECRET" not in raw
        assert "SECRET" not in raw
        assert "TOKEN" not in raw
        assert "PASSWORD" not in raw
        assert "Authorization" not in raw
        assert "Bearer" not in raw
        assert "APCA" not in raw

    def test_unsupported_provider_text_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "AAPL", "--provider", "sk-LEAKEDSECRET123456"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsupported research provider" in out.lower()
        raw = out
        assert "sk-LEAKEDSECRET123456" not in raw
        assert "LEAKEDSECRET" not in raw
        assert "SECRET" not in raw
        assert "TOKEN" not in raw
        assert "PASSWORD" not in raw
        assert "Authorization" not in raw
        assert "Bearer" not in raw
        assert "APCA" not in raw

    def test_unsupported_provider_plan_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        from atlas_agent.research.session import run_research_session

        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name=None,
        )
        run_id = artifact.run_id
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", run_id, "--provider", "sk-LEAKEDSECRET123456", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"
        assert "sk-LEAKEDSECRET123456" not in out

    def test_unsupported_provider_verify_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        from atlas_agent.research.session import run_research_session, create_paper_plan

        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name=None,
        )
        plan = create_paper_plan(
            workspace_path=tmp_path,
            run_id=artifact.run_id,
            event_logger=None,
            provider_name=None,
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", plan.plan_id, "--provider", "sk-LEAKEDSECRET123456", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"
        assert "sk-LEAKEDSECRET123456" not in out

    def test_unsupported_provider_evaluate_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        from atlas_agent.research.session import run_research_session, create_paper_plan

        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name=None,
        )
        plan = create_paper_plan(
            workspace_path=tmp_path,
            run_id=artifact.run_id,
            event_logger=None,
            provider_name=None,
        )
        data_path = tmp_path / "data" / "ohlcv.csv"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("date,open,high,low,close,volume\n2024-01-01,1,2,1,1.5,100\n")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main([
                "research", "evaluate", plan.plan_id,
                "--data", str(data_path),
                "--provider", "sk-LEAKEDSECRET123456",
                "--json",
            ])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"
        assert "sk-LEAKEDSECRET123456" not in out


class TestVersionHygiene:
    """Ensure current-version references are not stale."""

    def test_readme_current_status_matches_package_version(self) -> None:
        from atlas_agent import __version__

        expected_tag = f"v{__version__}"
        readme = Path("README.md").read_text(encoding="utf-8")
        # Only check the current status heading, not historical mentions
        for line in readme.splitlines():
            if line.strip().startswith("## Current Status"):
                assert expected_tag in line, f"README current status should reference {expected_tag}"
                return
        pytest.skip("No Current Status heading found in README.md")

    def test_release_checklist_smoke_example_matches_package_version(self) -> None:
        from atlas_agent import __version__

        expected_tag = f"v{__version__}"
        checklist = Path("docs/release-checklist.md").read_text(encoding="utf-8")
        found = False
        for line in checklist.splitlines():
            if "smoke_release_tag.sh" in line:
                if expected_tag in line:
                    found = True
                # Only enforce on lines that look like the primary example (not --full mode)
                elif "--full" not in line and "smoke_release_tag.sh" in line:
                    assert expected_tag in line, f"release-checklist smoke example should use {expected_tag}, got: {line}"
                    found = True
        assert found, f"No smoke_release_tag.sh example found in release-checklist.md"
