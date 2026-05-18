from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main


def _raise_if_called(*args, **kwargs):
    raise AssertionError("Config/secrets loader must not be called")


def _write_env_atlas(tmp_path: Path) -> None:
    env_atlas = tmp_path / ".env.atlas"
    env_atlas.write_text(
        "OPENAI_API_KEY=sk-LEAKEDSECRET123\n"
        "ANTHROPIC_API_KEY=sk-ANTHROPICSECRET123\n"
        "GOOGLE_API_KEY=GOOGLESECRET123\n"
        "APCA_API_KEY_ID=APCASECRET123\n"
        "ATLAS_SECRET_TOKEN=SECRET_TOKEN_VALUE\n",
        encoding="utf-8",
    )


def _ensure_workspace(tmp_path: Path) -> None:
    (tmp_path / "memory").mkdir(exist_ok=True)
    (tmp_path / "events").mkdir(exist_ok=True)


def _create_research_artifact(tmp_path: Path, monkeypatch) -> str:
    from atlas_agent.research.session import run_research_session

    monkeypatch.chdir(tmp_path)
    artifact = run_research_session(
        symbol="AAPL",
        workspace_path=tmp_path,
        memory_dir=None,
        event_logger=None,
        provider_name="deterministic",
    )
    return artifact.run_id


def _create_plan(tmp_path: Path, monkeypatch, run_id: str) -> str:
    from atlas_agent.research.session import create_paper_plan

    monkeypatch.chdir(tmp_path)
    plan = create_paper_plan(
        workspace_path=tmp_path,
        run_id=run_id,
        event_logger=None,
    )
    return plan.plan_id


def _create_verify(tmp_path: Path, monkeypatch, plan_id: str) -> str:
    from atlas_agent.research.session import verify_paper_plan

    monkeypatch.chdir(tmp_path)
    verification = verify_paper_plan(
        workspace_path=tmp_path,
        plan_id=plan_id,
        event_logger=None,
    )
    return verification.verification_id


def _create_evaluate(tmp_path: Path, monkeypatch, plan_id: str) -> str:
    from atlas_agent.research.session import evaluate_paper_plan

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "ohlcv.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerow({"date": "2026-01-01", "open": "100", "high": "105", "low": "99", "close": "102", "volume": "1000"})
        writer.writerow({"date": "2026-01-02", "open": "102", "high": "106", "low": "101", "close": "104", "volume": "1200"})

    monkeypatch.chdir(tmp_path)
    evaluation = evaluate_paper_plan(
        workspace_path=tmp_path,
        plan_id=plan_id,
        data_path=csv_path,
        event_logger=None,
    )
    return evaluation.evaluation_id


def _create_prompt_packet(tmp_path: Path, monkeypatch, run_id: str) -> str:
    from atlas_agent.research.session import generate_prompt_packet

    monkeypatch.chdir(tmp_path)
    packet = generate_prompt_packet(
        workspace_path=tmp_path,
        run_id=run_id,
        event_logger=None,
    )
    return packet["prompt_packet_id"]


def _create_provider_response(tmp_path: Path, monkeypatch, prompt_id: str) -> str:
    from atlas_agent.research.session import simulate_provider_response

    monkeypatch.chdir(tmp_path)
    result = simulate_provider_response(
        workspace_path=tmp_path,
        prompt_packet_id=prompt_id,
        provider="deterministic-mock",
        event_logger=None,
    )
    return result["provider_response_id"]


def _create_response_review(tmp_path: Path, monkeypatch, response_id: str) -> str:
    from atlas_agent.research.session import review_provider_response

    monkeypatch.chdir(tmp_path)
    result = review_provider_response(
        workspace_path=tmp_path,
        provider_response_id=response_id,
        event_logger=None,
    )
    return result["response_review_id"]



def _assert_no_secrets_in_output(out: str) -> None:
    assert "sk-LEAKEDSECRET" not in out
    assert "ANTHROPICSECRET" not in out
    assert "GOOGLESECRET" not in out
    assert "APCASECRET" not in out
    assert "SECRET_TOKEN_VALUE" not in out
    assert "OPENAI_API_KEY" not in out
    assert ".env.atlas" not in out


def _assert_env_not_polluted() -> None:
    assert os.environ.get("OPENAI_API_KEY", "") != "sk-LEAKEDSECRET123"
    assert os.environ.get("ANTHROPIC_API_KEY", "") != "sk-ANTHROPICSECRET123"
    assert os.environ.get("GOOGLE_API_KEY", "") != "GOOGLESECRET123"
    assert os.environ.get("APCA_API_KEY_ID", "") != "APCASECRET123"
    assert os.environ.get("ATLAS_SECRET_TOKEN", "") != "SECRET_TOKEN_VALUE"


class TestConfiglessResearchProviders:
    def test_providers_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "providers", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchRun:
    def test_run_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "run", "--symbol", "AAPL", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchList:
    def test_list_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "list", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchShow:
    def test_show_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "show", run_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchPlan:
    def test_plan_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "plan", run_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchVerify:
    def test_verify_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "verify", plan_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchEvaluate:
    def test_evaluate_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = data_dir / "ohlcv.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            writer.writerow({"date": "2026-01-01", "open": "100", "high": "105", "low": "99", "close": "102", "volume": "1000"})
            writer.writerow({"date": "2026-01-02", "open": "102", "high": "106", "low": "101", "close": "104", "volume": "1200"})
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchSummary:
    def test_summary_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "summary", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchCheckArtifacts:
    def test_check_artifacts_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "check-artifacts", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchTimeline:
    def test_timeline_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "timeline", "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchPrompt:
    def test_prompt_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "prompt", run_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchSimulateProvider:
    def test_simulate_provider_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchReviewResponse:
    def test_review_response_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "review-response", response_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()


class TestConfiglessResearchDossier:
    def test_dossier_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        _create_verify(tmp_path, monkeypatch, plan_id)
        _create_evaluate(tmp_path, monkeypatch, plan_id)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        _create_response_review(tmp_path, monkeypatch, response_id)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called):
            assert main(["research", "dossier", run_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        _assert_no_secrets_in_output(out)
        _assert_env_not_polluted()
