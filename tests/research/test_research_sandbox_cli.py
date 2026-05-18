from __future__ import annotations

import json
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


def _create_prompt_packet(tmp_path: Path, monkeypatch, run_id: str) -> str:
    from atlas_agent.research.session import generate_prompt_packet

    monkeypatch.chdir(tmp_path)
    packet = generate_prompt_packet(
        workspace_path=tmp_path,
        run_id=run_id,
        event_logger=None,
    )
    return packet["prompt_packet_id"]


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


class TestSandboxConfigless:
    def test_sandbox_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_sandbox_request_created"
        assert "sandbox_request_id" in data
        assert "artifact_path" in data

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_sandbox_artifact_has_safety_boundaries(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()

        artifact = json.loads(artifact_path.read_text())
        assert artifact["schema_version"] == "1"
        assert artifact["provider"] == "llm-sandbox"
        assert artifact["mode"] == "paper"
        assert "system_boundary" in artifact
        sb = artifact["system_boundary"]
        assert sb["paper_only"] is True
        assert sb["analysis_only"] is True
        assert sb["no_api_network_call"] is True
        assert sb["no_live_trading_authorization"] is True
        assert "explicit_boundaries" in artifact
        assert len(artifact["explicit_boundaries"]) > 0

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"


class TestSandboxInvalidInput:
    def test_invalid_prompt_packet_id(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", "nonexistent123", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert data["status"] == "research_artifact_not_found"

    def test_malformed_prompt_packet(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        # Corrupt the prompt packet
        prompt_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        prompt_path.write_text("{bad json", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert data["status"] == "research_artifact_malformed"


class TestSandboxTamperedLineage:
    """Regression tests: tampered prompt packet fields must fail closed without leaking values."""

    def _tamper_prompt_packet(self, tmp_path: Path, monkeypatch, run_id: str, **overrides) -> str:
        """Create a prompt packet, apply overrides, return its ID."""
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_path.read_text())
        data.update(overrides)
        prompt_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return prompt_id

    def test_tampered_source_run_id_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = self._tamper_prompt_packet(
            tmp_path, monkeypatch, run_id,
            source_run_id="APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com",
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert data["status"] == "invalid_source_run_id"

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment leaked in output: {frag}"

        sandbox_dir = tmp_path / ".atlas" / "research" / "AAPL" / "sandbox_requests"
        assert not any(sandbox_dir.glob("*.json")), "Sandbox artifact must not be created on invalid lineage"

    def test_tampered_prompt_packet_id_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = self._tamper_prompt_packet(
            tmp_path, monkeypatch, run_id,
            prompt_packet_id="bad/id!@#$",
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert data["status"] == "invalid_prompt_packet_id"

        sandbox_dir = tmp_path / ".atlas" / "research" / "AAPL" / "sandbox_requests"
        assert not any(sandbox_dir.glob("*.json")), "Sandbox artifact must not be created on invalid lineage"

    def test_tampered_symbol_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = self._tamper_prompt_packet(
            tmp_path, monkeypatch, run_id,
            symbol="../../etc/passwd",
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert data["status"] == "invalid_research_symbol"

        sandbox_dir = tmp_path / ".atlas" / "research" / "AAPL" / "sandbox_requests"
        assert not any(sandbox_dir.glob("*.json")), "Sandbox artifact must not be created on invalid lineage"

    def test_unsupported_schema_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = self._tamper_prompt_packet(
            tmp_path, monkeypatch, run_id,
            schema_version="999",
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_artifact_schema"

        sandbox_dir = tmp_path / ".atlas" / "research" / "AAPL" / "sandbox_requests"
        assert not any(sandbox_dir.glob("*.json")), "Sandbox artifact must not be created on invalid lineage"

    def test_malformed_json_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        prompt_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        prompt_path.write_text("{bad json", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "sandbox", prompt_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert data["status"] == "research_artifact_malformed"

        sandbox_dir = tmp_path / ".atlas" / "research" / "AAPL" / "sandbox_requests"
        assert not any(sandbox_dir.glob("*.json")), "Sandbox artifact must not be created on invalid lineage"


class TestSandboxTimeline:
    def test_timeline_includes_sandbox_request(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0
            sandbox_id = json.loads(capsys.readouterr().out)["sandbox_request_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "timeline", "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        entry = out["entries"][0]
        prompt = entry["prompts"][0]
        assert prompt["prompt_packet_id"] == prompt_id
        assert len(prompt.get("sandbox_requests", [])) == 1
        assert prompt["sandbox_requests"][0]["sandbox_request_id"] == sandbox_id


class TestSandboxCheckArtifacts:
    def test_check_artifacts_counts_sandbox_requests(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0
            capsys.readouterr()  # clear buffer

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "check-artifacts", "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        assert out["counts"]["sandbox_requests"] >= 1


class TestSandboxDossier:
    def test_dossier_includes_sandbox_request(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0
            capsys.readouterr()  # clear buffer

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "dossier", run_id, "--json"]) == 0

        cli_out = json.loads(capsys.readouterr().out)
        assert cli_out["ok"] is True
        # Read artifact directly for workflow_status / artifact_counts
        artifact_path = tmp_path / cli_out["artifact_path"]
        assert artifact_path.exists()
        dossier = json.loads(artifact_path.read_text())
        assert dossier["workflow_status"]["sandbox_requests"] is True
        assert dossier["artifact_counts"]["sandbox_requests"] >= 1
