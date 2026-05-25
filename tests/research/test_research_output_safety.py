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

    @staticmethod
    def _package_to_tag(package_version: str) -> str:
        """Map PEP 440 package version to public tag version."""
        import re
        m = re.match(r"^(\d+\.\d+\.\d+)rc(\d+)$", package_version)
        if m:
            return f"v{m.group(1)}-rc{m.group(2)}"
        return f"v{package_version}"

    def test_readme_current_status_matches_package_version(self) -> None:
        from atlas_agent import __version__

        expected_tag = self._package_to_tag(__version__)
        readme = Path("README.md").read_text(encoding="utf-8")
        # Only check the current status heading, not historical mentions
        for line in readme.splitlines():
            if line.strip().startswith("## Current Status"):
                assert expected_tag in line, f"README current status should reference {expected_tag}"
                return
        pytest.skip("No Current Status heading found in README.md")

    def test_release_checklist_smoke_example_matches_package_version(self) -> None:
        from atlas_agent import __version__

        expected_tag = self._package_to_tag(__version__)
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


FORBIDDEN_FRAGMENTS = [
    "/Users/",
    "/private/var/",
    "Authorization",
    "Bearer",
    "APCA",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "API_KEY",
    "sk-",
    "broker.example.com",
]


def _assert_no_forbidden_fragments(text: str) -> None:
    for frag in FORBIDDEN_FRAGMENTS:
        assert frag not in text, f"Forbidden fragment '{frag}' found in output: {text[:200]}"


class TestResearchGenericFallbackSafety:
    """Ensure generic research CLI failures do not leak raw exception text."""

    def test_generic_run_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.run_research_session", side_effect=RuntimeError("Authorization: Bearer abc123 /Users/natan/secret sk-LEAKEDSECRET")):
                code = main(["research", "run", "--symbol", "AAPL", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "LEAKEDSECRET" not in out
        assert "natan" not in out
        assert "secret" not in out.lower()

    def test_generic_run_failure_text_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.run_research_session", side_effect=RuntimeError("Authorization: Bearer abc123 /Users/natan/secret sk-LEAKEDSECRET")):
                code = main(["research", "run", "--symbol", "AAPL"])
        assert code == 1
        out = capsys.readouterr().out
        assert "research command failed" in out.lower()
        _assert_no_forbidden_fragments(out)
        assert "LEAKEDSECRET" not in out
        assert "natan" not in out
        assert "secret" not in out.lower()

    def test_generic_list_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.iter_research_artifacts", side_effect=RuntimeError("/private/var/tmp/raw.json SECRET_TOKEN")):
                code = main(["research", "list", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "SECRET_TOKEN" not in out

    def test_generic_show_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.find_research_artifact_by_run_id", side_effect=RuntimeError("broker.example.com Authorization: Bearer abc123")):
                code = main(["research", "show", "safeid", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "broker.example.com" not in out

    def test_generic_plan_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.create_paper_plan", side_effect=RuntimeError("raw CSV body /Users/natan/data.csv SECRET")):
                code = main(["research", "plan", "safeid", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "raw CSV body" not in out

    def test_generic_verify_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.verify_paper_plan", side_effect=RuntimeError("memory snippet APCA_TOKEN_PASSWORD")):
                code = main(["research", "verify", "safeid", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "APCA_TOKEN_PASSWORD" not in out

    def test_generic_evaluate_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.evaluate_paper_plan", side_effect=RuntimeError("broker response sk-SECRET API_KEY")):
                code = main(["research", "evaluate", "safeid", "--data", "data/sample/ohlcv.csv", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "broker response" not in out

    def test_generic_summary_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.summarize_research_workspace", side_effect=RuntimeError("/Users/natan/secret.json APCA")):
                code = main(["research", "summary", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "secret.json" not in out

    def test_generic_check_artifacts_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.check_research_artifacts", side_effect=RuntimeError("Authorization: Bearer token /private/var")):
                code = main(["research", "check-artifacts", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "Authorization" not in out

    def test_generic_timeline_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.research.session.build_research_timeline", side_effect=RuntimeError("sk-LEAKEDSECRET /Users/natan")):
                code = main(["research", "timeline", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)


class TestResearchMarketLegacySafety:
    """Ensure research market legacy command fails safely without leaking secrets."""

    def test_market_legacy_json_static_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "market", "--symbol", "AAPL", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "legacy_command_disabled"
        assert "legacy" in data["message"].lower()
        _assert_no_forbidden_fragments(out)

    def test_market_legacy_text_static_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "market", "--symbol", "AAPL"])
        assert code == 1
        out = capsys.readouterr().out
        assert "legacy" in out.lower()
        _assert_no_forbidden_fragments(out)


class TestResearchSandboxFallbackSafety:
    """Ensure sandbox CLI failures do not leak raw exception text."""

    def test_generic_sandbox_failure_json_no_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch(
                "atlas_agent.research.llm_sandbox.build_llm_sandbox_request_from_prompt_packet",
                side_effect=RuntimeError("Authorization: Bearer sk-LEAKEDSECRET /Users/natan/secret APCA_API_KEY_ID PASSWORD TOKEN broker.example.com"),
            ):
                code = main(["research", "sandbox", "fakepacket", "--json"])
        assert code == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "research_error"
        assert data["message"] == "Research command failed."
        _assert_no_forbidden_fragments(out)
        assert "LEAKEDSECRET" not in out
        assert "LEAKEDSECRET" not in out
