from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_call_plan import provider_call_plan_sha256
from atlas_agent.research.provider_execution_audit_packet import provider_execution_audit_packet_sha256


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


class TestProviderExecutionReplayEnvelopeConsistency:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        dry_run_path = tmp_path / dry_run_out["artifact_path"]
        plan_path = tmp_path / ".atlas" / "research" / dry_run_out.get("symbol", "AAPL") / "provider_call_plans" / f"{plan_id}.json"
        return dry_run_id, dry_run_path, plan_path

    def _modify_source_plan_to_cause_mismatch(self, plan_path: Path) -> None:
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_data["model_id"] = "gpt-4o-changed"
        plan_data["artifact_hash"] = provider_call_plan_sha256(plan_data)
        plan_path.write_text(json.dumps(plan_data, indent=2, sort_keys=True), encoding="utf-8")

    def test_replay_unchanged_returns_match_true(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path, _plan_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-replay", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_dry_run_replayed"
        assert data["match"] is True
        assert data["provider_execution_dry_run_id"] == dry_run_id
        assert "checks" in data
        assert "warnings" in data
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_replay_nonstrict_source_hash_mismatch_match_false(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path, plan_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        self._modify_source_plan_to_cause_mismatch(plan_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-replay", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_dry_run_replayed"
        assert data["match"] is False
        assert data["provider_execution_dry_run_id"] == dry_run_id
        assert "checks" in data
        assert "warnings" in data
        assert any("changed" in w.lower() for w in data["warnings"])
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_replay_strict_source_hash_mismatch_exits_nonzero(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path, plan_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        self._modify_source_plan_to_cause_mismatch(plan_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-replay", dry_run_id, "--json", "--strict"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_dry_run_replayed"
        assert data["match"] is False
        assert data["provider_execution_dry_run_id"] == dry_run_id
        assert "checks" in data
        assert "warnings" in data
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_replay_tampered_artifact_still_fails_safely(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, dry_run_path, _plan_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        artifact = json.loads(dry_run_path.read_text())
        artifact["actual_provider_call_made"] = True
        dry_run_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-replay", dry_run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code != 0
        assert data["ok"] is False
        assert "status" in data
        assert data["status"] != "research_provider_execution_dry_run_replayed"
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"


class TestProviderExecutionStateConfigless:
    def _create_state(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0

        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]
        artifact_path = tmp_path / state_out["artifact_path"]
        return dry_run_id, state_id, artifact_path

    def test_state_create_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        _write_env_atlas(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_state_created"
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_state_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, _artifact_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-state-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_state_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, _artifact_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-state-show", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_state_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, _artifact_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-state-validate", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_state_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, _artifact_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-state-replay", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"


class TestProviderExecutionStateTransitions:
    def _create_dry_run(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        dry_run_path = tmp_path / dry_run_out["artifact_path"]
        return dry_run_id, dry_run_path

    def test_default_state_is_disabled(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        from atlas_agent.research.provider_execution_state import _determine_current_state

        current = _determine_current_state(tmp_path, dry_run_id)
        assert current == "disabled"

    def test_disabled_to_dry_run_only_allowed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_state_created"
        assert data["previous_state"] == "disabled"
        assert data["state"] == "dry_run_only"
        assert data["transition_allowed"] is True

    def test_dry_run_only_to_manual_unlock_allowed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "manual_unlock_required", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["state"] == "manual_unlock_required"
        assert data["previous_state"] == "dry_run_only"

    def test_manual_unlock_to_provider_call_allowed_but_not_implemented_allowed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        capsys.readouterr()
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "manual_unlock_required", "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "provider_call_allowed_but_not_implemented", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["state"] == "provider_call_allowed_but_not_implemented"
        assert data["previous_state"] == "manual_unlock_required"

    def test_any_state_to_disabled_allowed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "disabled", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["state"] == "disabled"

    def test_unknown_state_blocked(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)
        from atlas_agent.research.provider_execution_state import evaluate_provider_execution_state_transition

        allowed, blocking = evaluate_provider_execution_state_transition(
            "disabled", "unknown_invalid_state", {"provider_enabled": False, "network_enabled": False, "credentials_loaded": False, "provider_call_allowed": False, "would_call_provider": False, "actual_provider_call_made": False, "execution_mode": "dry_run_only", "mode": "paper"}
        )
        assert allowed is False
        assert "invalid_requested_state" in blocking

    def test_provider_call_allowed_but_not_implemented_still_has_provider_call_allowed_false(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        capsys.readouterr()
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "manual_unlock_required", "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "provider_call_allowed_but_not_implemented", "--json"]) == 0

        out = capsys.readouterr().out
        data = json.loads(out)
        state_id = data["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state-show", state_id, "--json"]) == 0

        show_out = json.loads(capsys.readouterr().out)
        artifact = show_out["artifact"]
        assert artifact["provider_call_allowed"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["future_provider_execution_possible"] is False

    def test_blocked_transition_writes_no_artifact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, _dry_run_path = self._create_dry_run(tmp_path, monkeypatch, capsys)

        # Try to jump from disabled directly to provider_call_allowed_but_not_implemented (blocked)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", "provider_call_allowed_but_not_implemented", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        assert data["transition_allowed"] is False
        assert "blocking_reasons" in data

        # Verify no state artifact was written
        states_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_states"
        assert not states_dir.exists() or len(list(states_dir.glob("*.json"))) == 0


class TestProviderExecutionStateTamper:
    def _create_state(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0

        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]
        artifact_path = tmp_path / state_out["artifact_path"]
        return state_id, artifact_path

    def _tamper_and_test_show(self, tmp_path: Path, monkeypatch, capsys, tamper_fn) -> tuple[int, str, dict]:
        state_id, artifact_path = self._create_state(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        tamper_fn(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-show", state_id, "--json"])

        out = capsys.readouterr().out
        try:
            data = json.loads(out)
        except Exception:
            data = {}
        return code, out, data

    def test_tampered_state_id_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["provider_execution_state_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment leaked: {frag}"

    def test_tampered_provider_enabled_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["provider_enabled"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_network_enabled_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["network_enabled"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_credentials_loaded_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["credentials_loaded"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_provider_call_allowed_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["provider_call_allowed"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_actual_provider_call_made_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["actual_provider_call_made"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_future_provider_execution_possible_true_fails_show(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["future_provider_execution_possible"] = True
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_fields_do_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        state_id, artifact_path = self._create_state(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_state_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        for item in data["items"]:
            if item.get("_invalid"):
                assert item["provider_execution_state_id"] == "<invalid>"
                assert "model_id" not in item or item["model_id"] == "unknown"

    def test_tampered_state_name_fails_validation(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(a):
            a["state"] = "sk-LEAKEDSECRET_state"
        code, out, data = self._tamper_and_test_show(tmp_path, monkeypatch, capsys, tamper)
        assert code == 1
        assert data["ok"] is False


class TestProviderExecutionStateValidation:
    def _create_state(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0

        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]
        artifact_path = tmp_path / state_out["artifact_path"]
        return state_id, artifact_path

    def test_valid_state_validates(self, tmp_path: Path, monkeypatch, capsys) -> None:
        state_id, _artifact_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-validate", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True
        assert data["failed_checks"] == 0

    def test_hash_mismatch_detected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        state_id, artifact_path = self._create_state(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "gpt-4o-changed"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-validate", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        assert any(c["name"] == "artifact_hash_consistent" and not c["passed"] for c in data["checks"])

    def test_strict_validation_returns_nonzero_on_invalid(self, tmp_path: Path, monkeypatch, capsys) -> None:
        state_id, artifact_path = self._create_state(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_enabled"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-validate", state_id, "--json", "--strict"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["valid"] is False


class TestProviderExecutionStateReplay:
    def _create_state(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, Path, Path]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0

        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]
        dry_run_path = tmp_path / dry_run_out["artifact_path"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0

        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]
        state_path = tmp_path / state_out["artifact_path"]
        return dry_run_id, state_id, dry_run_path, state_path

    def test_replay_unchanged_returns_match_true(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _dry_run_id, state_id, _dry_run_path, _state_path = self._create_state(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-replay", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_state_replayed"
        assert data["match"] is True

    def test_replay_modified_source_dry_run_mismatch(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, dry_run_path, _state_path = self._create_state(tmp_path, monkeypatch, capsys)
        from atlas_agent.research.provider_execution_dry_run import provider_execution_dry_run_sha256

        dry_run = json.loads(dry_run_path.read_text())
        dry_run["model_id"] = "gpt-4o-changed"
        dry_run["artifact_hash"] = provider_execution_dry_run_sha256(dry_run)
        dry_run_path.write_text(json.dumps(dry_run, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-replay", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is False

    def test_replay_strict_mismatch_returns_nonzero(self, tmp_path: Path, monkeypatch, capsys) -> None:
        dry_run_id, state_id, dry_run_path, _state_path = self._create_state(tmp_path, monkeypatch, capsys)
        from atlas_agent.research.provider_execution_dry_run import provider_execution_dry_run_sha256

        dry_run = json.loads(dry_run_path.read_text())
        dry_run["model_id"] = "gpt-4o-changed"
        dry_run["artifact_hash"] = provider_execution_dry_run_sha256(dry_run)
        dry_run_path.write_text(json.dumps(dry_run, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state-replay", state_id, "--json", "--strict"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["match"] is False


class TestProviderExecutionStateIntegration:
    def _create_full_chain(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, str, str, str]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        return run_id, prompt_id, sandbox_id, dry_run_id, state_id

    def test_check_artifacts_counts_states(self, tmp_path: Path, monkeypatch, capsys) -> None:
        self._create_full_chain(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["counts"]["provider_execution_states"] >= 1

    def test_check_artifacts_detects_state_tamper(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _run_id, _prompt_id, _sandbox_id, dry_run_id, state_id = self._create_full_chain(tmp_path, monkeypatch, capsys)

        # Tamper the state artifact
        state_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_states").glob("*.json"))[0]
        artifact = json.loads(state_path.read_text())
        artifact["provider_enabled"] = True
        state_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert "provider_execution_state_impossible_boolean" in issue_codes

    def test_timeline_links_state(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id = self._create_full_chain(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = False
        for entry in data.get("entries", []):
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pc in sr.get("provider_call_plans", []):
                        for ped in pc.get("provider_execution_dry_runs", []):
                            states = ped.get("provider_execution_states", [])
                            if any(s.get("provider_execution_state_id") == state_id for s in states):
                                found = True
                                break
        assert found, f"State {state_id} not found in timeline"

    def test_dossier_includes_state_summary(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, _prompt_id, _sandbox_id, _dry_run_id, _state_id = self._create_full_chain(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "dossier", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        # Read dossier artifact from disk to verify internal counts
        dossier_path = tmp_path / data["artifact_path"]
        dossier_data = json.loads(dossier_path.read_text())
        assert dossier_data["artifact_counts"]["provider_execution_states"] >= 1
        summaries = dossier_data.get("summaries", {})
        if "provider_execution_state" in summaries:
            assert summaries["provider_execution_state"]["state_count"] >= 1

    def test_invalid_state_name_does_not_leak_raw_value_json(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        unsafe_value = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", unsafe_value, "--json"])

        assert code != 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in combined, f"Forbidden fragment leaked in output: {frag}"
        assert unsafe_value not in combined
        assert "invalid choice" not in combined.lower()
        assert "traceback" not in combined.lower()
        data = json.loads(captured.out)
        assert data["ok"] is False
        assert data["status"] == "invalid_provider_execution_state_name"
        # No state artifact should have been written
        states_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_states"
        assert not any(states_dir.glob("*.json"))

    def test_invalid_state_name_does_not_leak_raw_value_text(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        unsafe_value = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-state", dry_run_id, "--to", unsafe_value])

        assert code != 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in combined, f"Forbidden fragment leaked in output: {frag}"
        assert unsafe_value not in combined
        assert "invalid choice" not in combined.lower()
        assert "traceback" not in combined.lower()


class TestProviderExecutionAuditPacketConfigless:
    def test_audit_packet_creates_artifact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-audit", state_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_audit_packet_created"
        assert "provider_execution_audit_packet_id" in data
        assert data["source_provider_execution_state_id"] == state_id
        assert data["audit_status"] == "audit_packet_ready"
        assert data["execution_status"] == "provider_execution_blocked"
        assert "artifact_path" in data

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["artifact_type"] == "provider_execution_audit_packet"
        assert artifact["mode"] == "paper"
        assert artifact["audit_status"] == "audit_packet_ready"
        assert artifact["execution_status"] == "provider_execution_blocked"
        assert artifact["provider_enabled"] is False
        assert artifact["network_enabled"] is False
        assert artifact["credentials_loaded"] is False
        assert artifact["provider_call_allowed"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["future_provider_execution_possible"] is False
        assert artifact["trading_signal_generated"] is False
        assert artifact["approval_created"] is False
        assert artifact["pending_order_created"] is False
        assert artifact["broker_touched"] is False
        assert "artifact_chain" in artifact
        assert "safety_gate_summary" in artifact
        assert "no_action_attestations" in artifact
        assert artifact["no_action_attestations"]["provider_called"] is False
        assert artifact["no_action_attestations"]["network_request_made"] is False
        assert artifact["no_action_attestations"]["api_key_read"] is False

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_audit_packet_list_show_validate_replay(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        audit_out = json.loads(capsys.readouterr().out)
        audit_id = audit_out["provider_execution_audit_packet_id"]

        # list
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert any(i.get("provider_execution_audit_packet_id") == audit_id for i in data.get("items", []))

        # show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-show", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["artifact"]["provider_execution_audit_packet_id"] == audit_id

        # validate
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-validate", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True

        # replay
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-replay", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_audit_packet_replay_mismatch_after_tamper(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        audit_out = json.loads(capsys.readouterr().out)
        audit_id = audit_out["provider_execution_audit_packet_id"]

        # Tamper the source state artifact
        state_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_states").glob("*.json"))[0]
        artifact = json.loads(state_path.read_text())
        artifact["model_id"] = "tampered-model"
        state_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-replay", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is False

    def test_audit_packet_tampered_booleans_detected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        audit_out = json.loads(capsys.readouterr().out)
        audit_id = audit_out["provider_execution_audit_packet_id"]

        # Tamper the audit packet artifact
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["provider_enabled"] = True
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-validate", audit_id, "--strict", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["valid"] is False
        issue_codes = {c["name"] for c in data.get("checks", [])}
        assert "boolean_safety_flags_false" in issue_codes

    def test_check_artifacts_counts_audit_packets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["counts"]["provider_execution_audit_packets"] >= 1

    def test_timeline_links_audit_packet(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        audit_out = json.loads(capsys.readouterr().out)
        audit_id = audit_out["provider_execution_audit_packet_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = False
        for entry in data.get("entries", []):
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pc in sr.get("provider_call_plans", []):
                        for ped in pc.get("provider_execution_dry_runs", []):
                            for s in ped.get("provider_execution_states", []):
                                audits = s.get("provider_execution_audit_packets", [])
                                if any(a.get("provider_execution_audit_packet_id") == audit_id for a in audits):
                                    found = True
                                    break
        assert found, f"Audit packet {audit_id} not found in timeline"

    def test_dossier_includes_audit_packet_summary(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "dossier", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        dossier_path = tmp_path / data["artifact_path"]
        dossier_data = json.loads(dossier_path.read_text())
        assert dossier_data["artifact_counts"]["provider_execution_audit_packets"] >= 1

    def test_tampered_audit_packet_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        # Tamper the audit packet artifact ID with forbidden fragments
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["provider_execution_audit_packet_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["artifact_hash"] = provider_execution_audit_packet_sha256(artifact)
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        # Output must be denylist-clean
        out_text = json.dumps(data)
        assert "APCA" not in out_text
        assert "SECRET" not in out_text
        assert "TOKEN" not in out_text
        assert "sk-" not in out_text
        assert "broker.example.com" not in out_text
        # Raw tampered value absent
        assert "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com" not in out_text
        # Invalid artifacts use safe static values
        items = data.get("items", [])
        assert len(items) >= 1
        for item in items:
            assert item.get("provider_execution_audit_packet_id") != "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"

    def test_tampered_audit_packet_id_does_not_leak_through_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        # Tamper the audit packet artifact ID with forbidden fragments
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["provider_execution_audit_packet_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact["artifact_hash"] = provider_execution_audit_packet_sha256(artifact)
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        # Output must be denylist-clean
        out_text = json.dumps(data)
        assert "APCA" not in out_text
        assert "SECRET" not in out_text
        assert "TOKEN" not in out_text
        assert "sk-" not in out_text
        assert "broker.example.com" not in out_text
        # Raw tampered value absent
        assert "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com" not in out_text

    def test_tampered_model_id_does_not_leak_through_list_or_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        # Tamper model_id with forbidden fragment
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact["artifact_hash"] = provider_execution_audit_packet_sha256(artifact)
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        out_text = json.dumps(data)
        assert "sk-" not in out_text
        assert "LEAKEDSECRET" not in out_text

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        out_text = json.dumps(data)
        assert "sk-" not in out_text
        assert "LEAKEDSECRET" not in out_text

    def test_nested_no_action_attestations_approval_created_true_is_invalid(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        audit_out = json.loads(capsys.readouterr().out)
        audit_id = audit_out["provider_execution_audit_packet_id"]

        # Tamper nested no_action_attestations
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["no_action_attestations"]["approval_created"] = True
        artifact["artifact_hash"] = provider_execution_audit_packet_sha256(artifact)
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        # show should fail safely (ok=false or raise)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-show", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        # Should return ok=False or not include raw tampered content
        assert data.get("ok") is False or "artifact" not in data

        # validate should return valid=False
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-audit-validate", audit_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        issue_codes = {c["name"] for c in data.get("checks", [])}
        assert "boolean_safety_flags_false" in issue_codes

        # check-artifacts should report an issue
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert "provider_execution_audit_packet_impossible_boolean" in issue_codes

    def test_valid_chain_check_artifacts_no_missing_source_state(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = {i["code"] for i in data.get("issues", [])}
        assert "missing_source_state" not in issue_codes
        assert data["counts"]["provider_execution_states"] >= 1
        assert data["counts"]["provider_execution_audit_packets"] >= 1

    def test_audit_packet_list_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-audit-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_audit_packets_listed"
        assert len(data.get("items", [])) >= 1

    def test_audit_packet_timeline_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
        dry_run_out = json.loads(capsys.readouterr().out)
        dry_run_id = dry_run_out["provider_execution_dry_run_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
        state_out = json.loads(capsys.readouterr().out)
        state_id = state_out["provider_execution_state_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "timeline", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_timeline"


def _output_has_forbidden_fragments(text: str) -> list[str]:
    found = []
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            found.append(frag)
    return found


def _create_full_chain_to_audit_packet(tmp_path: Path, monkeypatch, capsys) -> tuple[str, str, str, str, str, str]:
    """Create full chain up to audit packet. Returns (run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id)."""
    _ensure_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_id, prompt_id, sandbox_id, plan_id = _create_provider_call_plan(tmp_path, monkeypatch, capsys)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
        assert main(["research", "provider-execution-dry-run", plan_id, "--json"]) == 0
    dry_run_out = json.loads(capsys.readouterr().out)
    dry_run_id = dry_run_out["provider_execution_dry_run_id"]

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
        assert main(["research", "provider-execution-state", dry_run_id, "--to", "dry_run_only", "--json"]) == 0
    state_out = json.loads(capsys.readouterr().out)
    state_id = state_out["provider_execution_state_id"]

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
        assert main(["research", "provider-execution-audit", state_id, "--json"]) == 0
    audit_out = json.loads(capsys.readouterr().out)
    audit_id = audit_out["provider_execution_audit_packet_id"]

    return run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id


class TestProviderExecutionReadinessReportConfigless:
    def test_readiness_report_creates_artifact(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-readiness", audit_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_readiness_report_created"
        assert "provider_execution_readiness_report_id" in data
        assert data["source_provider_execution_audit_packet_id"] == audit_id
        assert data["readiness_score"] >= 0 and data["readiness_score"] <= 100
        assert data["execution_status"] == "provider_execution_blocked"
        assert "artifact_path" in data

        artifact_path = tmp_path / data["artifact_path"]
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["artifact_type"] == "provider_execution_readiness_report"
        assert artifact["mode"] == "paper"
        assert artifact["provider_enabled"] is False
        assert artifact["network_enabled"] is False
        assert artifact["credentials_loaded"] is False
        assert artifact["provider_call_allowed"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["future_provider_execution_possible"] is False
        assert artifact["trading_signal_generated"] is False
        assert artifact["approval_created"] is False
        assert artifact["pending_order_created"] is False
        assert artifact["broker_touched"] is False
        assert "artifact_chain" in artifact
        assert "chain_diagnostics" in artifact
        assert "hash_diagnostics" in artifact
        assert "safety_gate_summary" in artifact
        assert "no_action_attestations" in artifact
        assert artifact["no_action_attestations"]["provider_called"] is False
        assert artifact["no_action_attestations"]["network_request_made"] is False
        assert artifact["no_action_attestations"]["api_key_read"] is False
        assert "human_review_checklist" in artifact
        assert "machine_readiness_checks" in artifact
        assert "future_opt_in_requirements" in artifact

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_readiness_report_list_show_validate_replay(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        # list
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert any(i.get("provider_execution_readiness_report_id") == readiness_id for i in data.get("items", []))

        # show
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["artifact"]["provider_execution_readiness_report_id"] == readiness_id

        # validate
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-validate", readiness_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True
        assert data["failed_checks"] == 0

        # replay
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-replay", readiness_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_readiness_report_list_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-readiness-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_readiness_reports_listed"

    def test_readiness_report_timeline_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "timeline", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_timeline"

    def test_chain_doctor_on_valid_run(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-chain-doctor", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_chain_doctor"
        assert data["run_id"] == run_id
        assert data["chain_health"] == "complete"
        assert data["readiness_status"] == "chain_review_ready"
        assert "missing_artifacts" in data
        assert "invalid_artifacts" in data
        assert "blocking_reasons" in data
        # Provider execution should be blocked
        assert "provider_execution_not_implemented" in data["blocking_reasons"]

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_chain_doctor_on_missing_run(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-chain-doctor", "nonexistent_run_id", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is False
        assert data["chain_health"] == "invalid"
        assert "research_artifact_not_found" in data["blocking_reasons"]

    def test_chain_doctor_does_not_write_artifacts(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id = _create_research_artifact(tmp_path, monkeypatch)

        before = list((tmp_path / ".atlas" / "research").rglob("*"))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-chain-doctor", run_id, "--json"])
        after = list((tmp_path / ".atlas" / "research").rglob("*"))

        assert code == 0
        # Doctor must not create any new artifacts
        assert set(after) == set(before), "Chain doctor created artifacts unexpectedly"

    def test_check_artifacts_counts_readiness_reports(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["counts"]["provider_execution_readiness_reports"] >= 1

    def test_dossier_includes_readiness_report(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "dossier", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        dossier_path = tmp_path / data["artifact_path"]
        dossier_data = json.loads(dossier_path.read_text())
        assert dossier_data["artifact_counts"]["provider_execution_readiness_reports"] >= 1
        linked_types = {a["type"] for a in dossier_data.get("linked_artifacts", [])}
        assert "provider_execution_readiness_report" in linked_types
        assert "provider_execution_readiness_report" in dossier_data.get("summaries", {})

    def test_happy_path_readiness_not_invalid(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-execution-readiness", audit_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_execution_readiness_report_created"
        assert data["readiness_status"] != "chain_invalid"
        assert data["readiness_score"] > 0
        assert data["readiness_score"] >= 90
        assert data["execution_status"] == "provider_execution_blocked"

        artifact_path = tmp_path / data["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        assert artifact["provider_call_allowed"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["trading_signal_generated"] is False
        assert artifact["approval_created"] is False
        assert artifact["pending_order_created"] is False
        assert artifact["broker_touched"] is False
        assert artifact["chain_health"] == "complete"
        assert artifact["readiness_status"] == "chain_review_ready"

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"
            assert frag not in artifact_path.read_text(), f"Forbidden fragment in artifact: {frag}"

    def test_safety_gate_summary_includes_all_mandatory_flags(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        artifact_path = tmp_path / readiness_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())

        sgs = artifact["safety_gate_summary"]
        required_flags = [
            "provider_enabled",
            "network_enabled",
            "credentials_loaded",
            "provider_call_allowed",
            "actual_provider_call_made",
            "future_provider_execution_possible",
            "trading_signal_generated",
            "approval_created",
            "pending_order_created",
            "broker_touched",
        ]
        for flag in required_flags:
            assert flag in sgs, f"Missing safety_gate_summary flag: {flag}"
            assert sgs[flag] is False, f"Safety flag {flag} should be False, got {sgs[flag]}"

    def test_missing_top_level_safety_flag_forces_invalid(self, tmp_path: Path, monkeypatch, capsys) -> None:
        from atlas_agent.research.provider_execution_readiness_report import provider_execution_readiness_report_sha256
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]
        artifact_path = tmp_path / readiness_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())

        # Remove a mandatory top-level safety flag
        del artifact["broker_touched"]
        # Recompute hash so validation doesn't fail on hash mismatch
        artifact["artifact_hash"] = provider_execution_readiness_report_sha256(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-validate", readiness_id, "--strict", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["valid"] is False

    def test_tampered_broker_touched_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        from atlas_agent.research.provider_execution_readiness_report import provider_execution_readiness_report_sha256
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]
        artifact_path = tmp_path / readiness_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())

        artifact["broker_touched"] = True
        artifact["artifact_hash"] = provider_execution_readiness_report_sha256(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_approval_created_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        from atlas_agent.research.provider_execution_readiness_report import provider_execution_readiness_report_sha256
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]
        artifact_path = tmp_path / readiness_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())

        artifact["approval_created"] = True
        artifact["artifact_hash"] = provider_execution_readiness_report_sha256(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_trading_signal_generated_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        from atlas_agent.research.provider_execution_readiness_report import provider_execution_readiness_report_sha256
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]
        artifact_path = tmp_path / readiness_out["artifact_path"]
        artifact = json.loads(artifact_path.read_text())

        artifact["trading_signal_generated"] = True
        artifact["artifact_hash"] = provider_execution_readiness_report_sha256(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"


class TestProviderExecutionReadinessReportTamper:
    def _create_readiness_report(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]
        artifact_path = tmp_path / readiness_out["artifact_path"]
        return readiness_id, artifact_path

    def test_tampered_readiness_report_id_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_readiness_report_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_model_id_does_not_leak(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["model_id"] = "sk-LEAKEDSECRET"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in output: {found}"

    def test_tampered_provider_enabled_true_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_enabled"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_readiness_score_out_of_range_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["readiness_score"] = 150
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-validate", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        assert any(c["name"] == "readiness_score_in_range" and not c["passed"] for c in data["checks"])

    def test_tampered_nested_no_action_attestations_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["no_action_attestations"]["approval_created"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_readiness_status_invalid_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["readiness_status"] = "approved_for_execution"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-show", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 1
        assert data["ok"] is False

    def test_tampered_source_audit_packet_hash_mismatch_detected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["source_audit_packet_hash"] = "tampered_hash_12345"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-validate", readiness_id, "--strict", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2  # strict returns nonzero
        assert data["ok"] is True
        assert data["valid"] is False

    def test_tampered_artifact_hash_mismatch_detected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["readiness_score"] = 42
        # Do not recompute hash — simulate tamper
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-validate", readiness_id, "--strict", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["valid"] is False
        assert any(c["name"] == "artifact_hash_consistent" and not c["passed"] for c in data["checks"])

    def test_tampered_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        readiness_id, artifact_path = self._create_readiness_report(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_execution_readiness_report_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in list output: {found}"

    def test_tampered_id_does_not_leak_through_timeline(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        # Tamper the readiness report
        readiness_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_readiness_reports").glob("*.json"))[0]
        artifact = json.loads(readiness_path.read_text())
        artifact["provider_execution_readiness_report_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        readiness_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in timeline output: {found}"


class TestProviderExecutionReadinessReportReplay:
    def test_replay_match_on_untouched(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-replay", readiness_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_replay_mismatch_on_modified_source_audit_packet(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        # Modify source audit packet
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["latest_state"] = "tampered_state"
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-replay", readiness_id, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is False

    def test_replay_strict_returns_nonzero_on_mismatch(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        # Modify source audit packet
        audit_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_audit_packets").glob("*.json"))[0]
        artifact = json.loads(audit_path.read_text())
        artifact["latest_state"] = "tampered_state"
        audit_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-execution-readiness-replay", readiness_id, "--strict", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 2
        assert data["ok"] is True
        assert data["match"] is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in replay output: {found}"


class TestProviderExecutionReadinessReportIntegration:
    def test_timeline_links_readiness_report(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "timeline", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        # Find the readiness report nested in timeline
        found = False
        for entry in data.get("entries", []):
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pcp in sr.get("provider_call_plans", []):
                        for ped in pcp.get("provider_execution_dry_runs", []):
                            for pes in ped.get("provider_execution_states", []):
                                for peap in pes.get("provider_execution_audit_packets", []):
                                    for perr in peap.get("provider_execution_readiness_reports", []):
                                        found = True
                                        assert "provider_execution_readiness_report_id" in perr
        assert found, "Readiness report not found in timeline"

    def test_check_artifacts_detects_readiness_report_tamper(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        # Tamper readiness report
        readiness_path = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_execution_readiness_reports").glob("*.json"))[0]
        artifact = json.loads(readiness_path.read_text())
        artifact["provider_call_allowed"] = True
        readiness_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = [i["code"] for i in data["issues"]]
        assert "provider_execution_readiness_report_impossible_boolean" in issue_codes

    def test_valid_chain_no_missing_source_audit_packet(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        capsys.readouterr()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        issue_codes = [i["code"] for i in data["issues"]]
        assert "missing_source_audit_packet" not in issue_codes
        assert "source_audit_packet_hash_mismatch" not in issue_codes

    def test_dossier_missing_readiness_report_warning_only(self, tmp_path: Path, monkeypatch, capsys) -> None:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)
        # Do NOT create readiness report

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "dossier", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        dossier_path = tmp_path / data["artifact_path"]
        dossier_data = json.loads(dossier_path.read_text())
        # Missing readiness report should be in missing_links but not fail the dossier
        assert "no_provider_execution_readiness_report" in dossier_data.get("missing_links", [])
        # Dossier should still be created successfully
        assert dossier_data["recommendation"] in ("research_dossier_ready", "manual_review_required")


class TestProviderPreflightFreezeConfigless:
    def _create_freeze(self, tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
        run_id, prompt_id, sandbox_id, dry_run_id, state_id, audit_id = _create_full_chain_to_audit_packet(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            assert main(["research", "provider-execution-readiness", audit_id, "--json"]) == 0
        readiness_out = json.loads(capsys.readouterr().out)
        readiness_id = readiness_out["provider_execution_readiness_report_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-preflight-freeze", readiness_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_preflight_freeze_created"
        freeze_id = data["provider_preflight_freeze_id"]
        artifact_path = tmp_path / data["artifact_path"]
        return freeze_id, artifact_path

    def test_freeze_creates_artifact_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["artifact_type"] == "provider_preflight_freeze"
        assert artifact["mode"] == "paper"
        assert artifact["provider_enabled"] is False
        assert artifact["network_enabled"] is False
        assert artifact["credentials_loaded"] is False
        assert artifact["provider_call_allowed"] is False
        assert artifact["actual_provider_call_made"] is False
        assert artifact["future_provider_execution_possible"] is False
        assert artifact["trading_signal_generated"] is False
        assert artifact["approval_created"] is False
        assert artifact["pending_order_created"] is False
        assert artifact["broker_touched"] is False

    def test_freeze_artifact_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)
        artifact_text = artifact_path.read_text()
        found = _output_has_forbidden_fragments(artifact_text)
        assert not found, f"Forbidden fragments found in freeze artifact: {found}"

    def test_denylist_manifest_does_not_store_raw_fragments(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        denylist = artifact.get("denylist_manifest", {})
        assert denylist.get("denylist_profile") == "atlas_standard_forbidden_fragments_v1"
        assert isinstance(denylist.get("forbidden_fragment_count"), int)
        assert denylist.get("forbidden_fragment_count") >= 1
        assert denylist.get("forbidden_fragments_raw_stored") is False
        assert denylist.get("output_safety_expected") is True
        assert denylist.get("artifact_safety_expected") is True
        assert denylist.get("raw_exception_output_allowed") is False
        assert denylist.get("absolute_path_output_allowed") is False
        assert denylist.get("unsafe_value_echo_allowed") is False
        # Ensure no field contains raw forbidden strings
        denylist_text = json.dumps(denylist)
        raw_found = _output_has_forbidden_fragments(denylist_text)
        assert not raw_found, f"Raw forbidden fragments found in denylist_manifest: {raw_found}"

    def test_freeze_show_exits_zero(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-preflight-freeze-show", freeze_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_preflight_freeze_loaded"
        assert "artifact" in data
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in show output: {found}"

    def test_freeze_validate_returns_valid(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-preflight-freeze-validate", freeze_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True
        assert data["failed_checks"] == 0
        check_names = [c["name"] for c in data.get("checks", [])]
        assert "denylist_manifest_safe" in check_names
        denylist_check = next(c for c in data["checks"] if c["name"] == "denylist_manifest_safe")
        assert denylist_check["passed"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in validate output: {found}"

    def test_freeze_replay_returns_match(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-preflight-freeze-replay", freeze_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in replay output: {found}"

    def test_check_artifacts_counts_freeze(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "check-artifacts", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        counts = data.get("counts", {})
        assert counts.get("provider_preflight_freezes", 0) >= 1
        issue_codes = [i["code"] for i in data.get("issues", [])]
        assert "provider_preflight_freeze_malformed" not in issue_codes
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in check-artifacts output: {found}"

    def test_freeze_tampered_boolean_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["provider_call_allowed"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-preflight-freeze-validate", freeze_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        issue_codes = [i["code"] for i in data.get("issues", [])]
        # validate returns checks, not issues directly; check for failed boolean check
        check_names = {c["name"]: c["passed"] for c in data.get("checks", [])}
        assert check_names.get("boolean_safety_flags_false") is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in tamper output: {found}"

    def test_freeze_tampered_denylist_raw_stored_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        freeze_id, artifact_path = self._create_freeze(tmp_path, monkeypatch, capsys)
        artifact = json.loads(artifact_path.read_text())
        artifact["denylist_manifest"]["forbidden_fragments_raw_stored"] = True
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=None):
            code = main(["research", "provider-preflight-freeze-validate", freeze_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is False
        check_names = {c["name"]: c["passed"] for c in data.get("checks", [])}
        assert check_names.get("denylist_manifest_safe") is False
        found = _output_has_forbidden_fragments(out)
        assert not found, f"Forbidden fragments leaked in tamper output: {found}"

    def test_freeze_list_configless(self, tmp_path: Path, monkeypatch, capsys) -> None:
        self._create_freeze(tmp_path, monkeypatch, capsys)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-preflight-freeze-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert len(data.get("items", [])) >= 1
