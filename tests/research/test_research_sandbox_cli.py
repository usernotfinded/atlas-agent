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


class TestImportProviderResponse:
    """Regression tests for import-provider-response --json path."""

    @staticmethod
    def _valid_fixture() -> dict:
        return {
            "summary": "External analysis of market context.",
            "sections": [
                {"title": "Scope", "content": "Review local sandbox request only."},
                {"title": "Risks", "content": "No live trading is authorized."},
            ],
            "safety_checks": [
                {"name": "paper_only", "status": "pass", "notes": "Mode is paper."}
            ],
            "limitations": ["Not financial advice.", "No real market data queried."],
        }

    def test_successful_import_json(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        sandbox_id = out["sandbox_request_id"]

        fixture_path = tmp_path / "imported_response.json"
        fixture_path.write_text(json.dumps(self._valid_fixture()), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(
                [
                    "research",
                    "import-provider-response",
                    sandbox_id,
                    "--file",
                    str(fixture_path),
                    "--json",
                ]
            )

        stdout = capsys.readouterr().out
        data = json.loads(stdout)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_imported"
        assert "provider_response_id" in data
        assert data["source_sandbox_request_id"] == sandbox_id
        assert "artifact_path" in data
        assert isinstance(data["warnings"], list)

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["provider"] == "external-local-import"
        assert artifact["provider_status"] == "imported_untrusted"
        assert artifact["recommendation"] in (
            "provider_response_review_required",
            "manual_review_required",
        )

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in stdout, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_missing_file_fails_safe(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        sandbox_id = out["sandbox_request_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(
                [
                    "research",
                    "import-provider-response",
                    sandbox_id,
                    "--file",
                    str(tmp_path / "nonexistent.json"),
                    "--json",
                ]
            )

        stdout = capsys.readouterr().out
        data = json.loads(stdout)
        assert code == 1
        assert data["ok"] is False
        assert data["status"] == "provider_response_file_not_found"
        assert "Traceback" not in stdout
        assert "/Users/" not in stdout
        assert "/private/var/" not in stdout

    def test_malformed_json_fails_safe(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        sandbox_id = out["sandbox_request_id"]

        fixture_path = tmp_path / "bad.json"
        fixture_path.write_text("{bad json", encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(
                [
                    "research",
                    "import-provider-response",
                    sandbox_id,
                    "--file",
                    str(fixture_path),
                    "--json",
                ]
            )

        stdout = capsys.readouterr().out
        data = json.loads(stdout)
        assert code == 1
        assert data["ok"] is False
        assert data["status"] == "provider_response_malformed"
        assert "Traceback" not in stdout
        assert "/Users/" not in stdout
        assert "/private/var/" not in stdout

    def test_unsafe_content_is_redacted(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "sandbox", prompt_id, "--json"]) == 0

        out = json.loads(capsys.readouterr().out)
        sandbox_id = out["sandbox_request_id"]

        fixture_path = tmp_path / "unsafe.json"
        fixture_path.write_text(
            json.dumps({
                "summary": "Authorization: Bearer abc123",
                "sections": [{"title": "T", "content": "Authorization: Bearer abc123"}],
                "safety_checks": [],
                "limitations": ["Authorization: Bearer abc123"],
            }),
            encoding="utf-8",
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(
                [
                    "research",
                    "import-provider-response",
                    sandbox_id,
                    "--file",
                    str(fixture_path),
                    "--json",
                ]
            )

        stdout = capsys.readouterr().out
        data = json.loads(stdout)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_imported"

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact_text = artifact_path.read_text()

        for frag in ("Authorization", "Bearer"):
            assert frag not in stdout, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_text, f"Forbidden fragment in artifact: {frag}"

        assert "<redacted>" in artifact_text


def _create_sandbox_request(tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, str]:
    """Create research artifact, prompt packet, and sandbox request. Returns (run_id, prompt_id, sandbox_id)."""
    _ensure_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_id = _create_research_artifact(tmp_path, monkeypatch)
    prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
        assert main(["research", "sandbox", prompt_id, "--json"]) == 0

    out = json.loads(capsys.readouterr().out)
    return run_id, prompt_id, out["sandbox_request_id"]


class TestProviderCallPlanConfigless:
    def test_provider_targets_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-targets", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_targets_listed"
        assert len(data["targets"]) >= 1
        target_ids = {t["provider_id"] for t in data["targets"]}
        assert "custom-openai-compatible" in target_ids
        for t in data["targets"]:
            assert t["enabled"] is False
            assert t["network"] is False

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_provider_plan_creates_artifact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_call_plan_created"
        assert "provider_call_plan_id" in data
        assert data["source_sandbox_request_id"] == sandbox_id
        assert data["provider_id"] == "custom-openai-compatible"
        assert data["model_id"] == "gpt-4o"
        assert "artifact_path" in data

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["artifact_type"] == "provider_call_plan"
        assert artifact["mode"] == "paper"
        assert artifact["provider_enabled"] is False
        assert artifact["network_enabled"] is False
        assert artifact["credentials_loaded"] is False
        assert artifact["provider_call_allowed"] is False
        assert artifact["execution_mode"] == "plan_only"
        assert artifact["source_sandbox_request_id"] == sandbox_id

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_provider_plan_list_show_validate_replay(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ]) == 0

        plan_out = json.loads(capsys.readouterr().out)
        plan_id = plan_out["provider_call_plan_id"]

        # list
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-plan-list", "--json"]) == 0
        list_out = json.loads(capsys.readouterr().out)
        assert list_out["ok"] is True
        assert any(i.get("provider_call_plan_id") == plan_id for i in list_out["items"])

        # show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-plan-show", plan_id, "--json"]) == 0
        show_out = json.loads(capsys.readouterr().out)
        assert show_out["ok"] is True
        assert show_out["artifact"]["provider_call_plan_id"] == plan_id

        # validate
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-plan-validate", plan_id, "--json"]) == 0
        validate_out = json.loads(capsys.readouterr().out)
        assert validate_out["ok"] is True
        assert validate_out["valid"] is True
        assert validate_out["failed_checks"] == 0

        # replay
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-plan-replay", plan_id, "--json"]) == 0
        replay_out = json.loads(capsys.readouterr().out)
        assert replay_out["ok"] is True
        assert replay_out["match"] is True

    def test_provider_plan_invalid_provider_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main([
                "research", "provider-plan", sandbox_id,
                "--provider", "nonexistent-provider",
                "--model", "gpt-4o",
                "--json",
            ])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert "Traceback" not in out

    def test_provider_plan_invalid_model_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "Bearer sk-leaked",
                "--json",
            ])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert "Traceback" not in out

    def test_provider_plan_validate_strict_fails_on_tampered(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ]) == 0

        plan_out = json.loads(capsys.readouterr().out)
        plan_id = plan_out["provider_call_plan_id"]

        # Tamper artifact: change provider_enabled to True
        artifact_path = tmp_path / plan_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_enabled"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-plan-validate", plan_id, "--strict", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["valid"] is False
        assert data["failed_checks"] >= 1

    def test_provider_plan_replay_strict_fails_on_tampered(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ]) == 0

        plan_out = json.loads(capsys.readouterr().out)
        plan_id = plan_out["provider_call_plan_id"]

        # Tamper artifact: change model_id
        artifact_path = tmp_path / plan_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "tampered-model"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-plan-replay", plan_id, "--strict", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        # Tampered artifacts fail closed during validation before replay
        assert code == 1
        assert data["ok"] is False
        assert "Traceback" not in out


FORBIDDEN_FRAGMENTS = (
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
)


def _output_has_forbidden_fragments(text: str) -> list[str]:
    found = []
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            found.append(frag)
    return found


class TestProviderCallPlanTamperLeakage:
    def _create_plan(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ]) == 0

        plan_out = json.loads(capsys.readouterr().out)
        plan_id = plan_out["provider_call_plan_id"]
        artifact_path = tmp_path / plan_out["artifact_path"]
        return plan_id, artifact_path

    def test_tampered_plan_id_does_not_leak_through_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        plan_id, artifact_path = self._create_plan(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_call_plan_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-plan-show", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_model_id_does_not_leak_through_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        plan_id, artifact_path = self._create_plan(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-plan-show", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_fields_do_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        plan_id, artifact_path = self._create_plan(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_call_plan_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-plan-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in list output: {found}"
        # Invalid item should be a safe sentinel
        items = data["items"]
        assert any(i.get("_invalid") for i in items)
        for item in items:
            if item.get("_invalid"):
                assert item["provider_call_plan_id"] == "<invalid>"
                assert item["symbol"] == "<invalid>"
                assert item["provider_id"] == "unknown"
                assert item["model_id"] == "unknown"

    def test_tampered_fields_do_not_leak_through_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        plan_id, artifact_path = self._create_plan(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_call_plan_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in timeline output: {found}"

    def test_check_artifacts_detects_model_id_tamper(self, tmp_path: Path, monkeypatch, capsys) -> None:
        plan_id, artifact_path = self._create_plan(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "tampered-model"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in check-artifacts output: {found}"
        # Should have an issue indicating tamper/hash/model problem
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert issue_codes, f"Expected issues for tampered artifact, got none. Output: {out}"
        expected_codes = {
            "provider_call_plan_hash_mismatch",
            "invalid_provider_call_plan_model",
            "invalid_provider_call_plan_lineage",
        }
        assert issue_codes & expected_codes, f"Expected one of {expected_codes}, got {issue_codes}"


class TestProviderCallPlanConfiglessTraps:
    def _create_plan(self, tmp_path: Path, monkeypatch, capsys) -> str:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main([
                "research", "provider-plan", sandbox_id,
                "--provider", "custom-openai-compatible",
                "--model", "gpt-4o",
                "--json",
            ]) == 0

        plan_out = json.loads(capsys.readouterr().out)
        return plan_out["provider_call_plan_id"]

    def test_provider_plan_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        plan_id = self._create_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-plan-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_plan_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        plan_id = self._create_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-plan-show", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_plan_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        plan_id = self._create_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-plan-validate", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_plan_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        plan_id = self._create_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-plan-replay", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True


# ---------------------------------------------------------------------------
# Provider Execution Dry-Run Tests
# ---------------------------------------------------------------------------


def _create_provider_call_plan(tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, str, str]:
    """Create full chain up to provider call plan. Returns (run_id, prompt_id, sandbox_id, plan_id)."""
    _ensure_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_id, prompt_id, sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, capsys)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
        assert main([
            "research", "provider-plan", sandbox_id,
            "--provider", "custom-openai-compatible",
            "--model", "gpt-4o",
            "--json",
        ]) == 0

    plan_out = json.loads(capsys.readouterr().out)
    return run_id, prompt_id, sandbox_id, plan_out["provider_call_plan_id"]


class TestProviderExecutionDryRunConfigless:
    def test_provider_execution_dry_run_creates_artifact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main([
                "research", "provider-execution-dry-run", plan_id, "--json",
            ])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_dry_run_created"
        assert "provider_execution_dry_run_id" in data
        assert data["source_provider_call_plan_id"] == plan_id
        assert data["provider_id"] == "custom-openai-compatible"
        assert data["model_id"] == "gpt-4o"
        assert "artifact_path" in data

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["artifact_type"] == "provider_execution_dry_run"
        assert artifact["mode"] == "paper"
        assert artifact["execution_mode"] == "dry_run_only"
        assert artifact["provider_enabled"] is False
        assert artifact["network_enabled"] is False
        assert artifact["credentials_loaded"] is False
        assert artifact["provider_call_allowed"] is False
        assert artifact["would_call_provider"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["source_provider_call_plan_id"] == plan_id

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_provider_execution_list_show_validate_replay(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        # list
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-list", "--json"]) == 0
        list_out = json.loads(capsys.readouterr().out)
        assert list_out["ok"] is True
        assert any(i.get("provider_execution_dry_run_id") == dry_run_id for i in list_out["items"])

        # show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-show", dry_run_id, "--json"]) == 0
        show_out = json.loads(capsys.readouterr().out)
        assert show_out["ok"] is True
        assert show_out["artifact"]["provider_execution_dry_run_id"] == dry_run_id

        # validate
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-validate", dry_run_id, "--json"]) == 0
        validate_out = json.loads(capsys.readouterr().out)
        assert validate_out["ok"] is True
        assert validate_out["valid"] is True
        assert validate_out["failed_checks"] == 0

        # replay
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-replay", dry_run_id, "--json"]) == 0
        replay_out = json.loads(capsys.readouterr().out)
        assert replay_out["ok"] is True
        assert replay_out["match"] is True

    def test_provider_execution_invalid_plan_id_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-dry-run", "nonexistent-plan-id", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert "Traceback" not in out


class TestProviderExecutionDryRunTamperLeakage:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        artifact_path = tmp_path / dry_run_out["artifact_path"]
        return dry_run_id, artifact_path

    def test_tampered_dry_run_id_does_not_leak_through_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_dry_run_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_model_id_does_not_leak_through_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_fields_do_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_dry_run_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in list output: {found}"
        items = data["items"]
        assert any(i.get("_invalid") for i in items)
        for item in items:
            if item.get("_invalid"):
                assert item["provider_execution_dry_run_id"] == "<invalid>"
                assert item["symbol"] == "<invalid>"
                assert item["provider_id"] == "unknown"
                assert item["model_id"] == "unknown"

    def test_tampered_fields_do_not_leak_through_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_dry_run_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in timeline output: {found}"

    def test_check_artifacts_detects_dry_run_tamper(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "tampered-model"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in check-artifacts output: {found}"
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert issue_codes, f"Expected issues for tampered artifact, got none. Output: {out}"
        expected_codes = {
            "provider_execution_dry_run_hash_mismatch",
            "invalid_provider_execution_dry_run_model",
            "invalid_provider_execution_dry_run_lineage",
        }
        assert issue_codes & expected_codes, f"Expected one of {expected_codes}, got {issue_codes}"


class TestProviderExecutionDryRunBooleanTamper:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        artifact_path = tmp_path / dry_run_out["artifact_path"]
        return dry_run_id, artifact_path

    def test_actual_provider_call_made_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_provider_call_allowed_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_call_allowed"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_network_enabled_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["network_enabled"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_credentials_loaded_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["credentials_loaded"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_would_call_provider_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["would_call_provider"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_provider_enabled_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_enabled"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_source_call_plan_id_with_forbidden_fragments_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["source_provider_call_plan_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_dry_run_id_with_forbidden_fragments_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_dry_run_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_model_id_sk_leaked_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_hash_drift_after_summary_tamper_detected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["dry_run_summary"] = "TAMPERED SUMMARY"
        # Do NOT recompute hash — simulate tamper
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert "provider_execution_dry_run_hash_mismatch" in issue_codes


class TestProviderExecutionDryRunConfiglessTraps:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> str:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        return dry_run_out["provider_execution_dry_run_id"]

    def test_provider_execution_dry_run_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-dry-run", plan_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_execution_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        dry_run_id = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_execution_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        dry_run_id = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_execution_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        dry_run_id = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-validate", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

    def test_provider_execution_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        dry_run_id = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-replay", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True


class TestProviderExecutionDryRunArtifactPath:
    def test_artifact_path_exact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        artifact_path = dry_run_out["artifact_path"]
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        symbol = dry_run_out.get("source_provider_call_plan_id")  # not symbol, we need to get it from artifact
        # Actually get symbol from the created artifact
        artifact = json.loads((tmp_path / artifact_path).read_text())
        symbol = artifact["symbol"]
        expected = f".atlas/research/{symbol}/provider_execution_dry_runs/{dry_run_id}.json"
        assert artifact_path == expected, f"Expected {expected}, got {artifact_path}"


class TestProviderExecutionDryRunTamperBooleanActualCall:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        artifact_path = tmp_path / dry_run_out["artifact_path"]
        return dry_run_id, artifact_path

    def _tamper_and_test(self, tmp_path: Path, monkeypatch, capsys, command: str, *args) -> tuple[int, str, dict]:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", command, *args])

        out = capsys.readouterr().out
        try:
            data = json.loads(out)
        except Exception:
            data = {}
        return code, out, data

    def test_actual_provider_call_made_true_detected_by_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_actual_provider_call_made_true_detected_by_validate(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-validate", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        failed_names = {c["name"] for c in data.get("checks", []) if not c.get("passed", True)}
        assert "actual_provider_call_made_false" in failed_names or "no_impossible_booleans" in failed_names

    def test_actual_provider_call_made_true_detected_by_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        items = data["items"]
        assert any(i.get("_invalid") for i in items)
        for item in items:
            if item.get("_invalid"):
                assert item["provider_execution_dry_run_id"] == "<invalid>"

    def test_actual_provider_call_made_true_detected_by_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        # Tampered dry-runs should not appear in timeline (no source_plan_id from invalid items)
        # Or appear as warnings
        warnings = data.get("warnings", [])
        warn_codes = {w.get("code", "") for w in warnings}
        assert "orphan_provider_execution_dry_run" in warn_codes or not any(
            ped.get("provider_execution_dry_run_id") == dry_run_id
            for e in data.get("entries", [])
            for p in e.get("prompts", [])
            for sr in p.get("sandbox_requests", [])
            for pc in sr.get("provider_call_plans", [])
            for ped in pc.get("provider_execution_dry_runs", [])
        )

    def test_actual_provider_call_made_true_detected_by_check_artifacts(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert "provider_execution_dry_run_impossible_boolean" in issue_codes


class TestProviderExecutionDryRunNoRawDictSerialization:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        artifact_path = tmp_path / dry_run_out["artifact_path"]
        return dry_run_id, artifact_path

    def test_show_never_emits_raw_loaded_dict(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-show", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        artifact = data["artifact"]
        # Should only contain cleaned fields
        assert "provider_execution_dry_run_id" in artifact
        assert "artifact_hash" in artifact
        # The raw dict could contain unexpected fields if not cleaned; verify key count is bounded
        # A valid cleaned artifact has exactly the fields we defined
        expected_keys = {
            "schema_version", "artifact_type", "contract_version",
            "provider_execution_dry_run_id", "source_provider_call_plan_id",
            "source_sandbox_request_id", "source_prompt_packet_id", "source_run_id",
            "symbol", "mode", "provider_id", "model_id",
            "provider_enabled", "network_enabled", "credentials_loaded",
            "provider_call_allowed", "would_call_provider", "actual_provider_call_made",
            "execution_mode", "request_shape", "dry_run_summary", "input_hash",
            "source_call_plan_hash", "constraints", "forbidden_actions",
            "redaction_summary", "artifact_path", "warnings", "metadata",
            "artifact_hash", "created_at",
        }
        assert set(artifact.keys()) == expected_keys

    def test_list_never_emits_raw_loaded_dict(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        # Tamper to make it invalid
        artifact = json.loads(artifact_path.read_text())
        artifact["actual_provider_call_made"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for item in data["items"]:
            # No raw tampered dict should be serialized
            if item.get("_invalid"):
                assert item["provider_execution_dry_run_id"] == "<invalid>"
                assert "actual_provider_call_made" not in item

    def test_timeline_never_emits_raw_loaded_dict(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, artifact_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for entry in data.get("entries", []):
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pc in sr.get("provider_call_plans", []):
                        for ped in pc.get("provider_execution_dry_runs", []):
                            # Only safe metadata fields
                            assert "provider_execution_dry_run_id" in ped
                            assert "artifact_path" in ped
                            # No raw loaded artifact dict
                            assert "actual_provider_call_made" not in ped
