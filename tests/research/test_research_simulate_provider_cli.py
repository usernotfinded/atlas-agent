# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_simulate_provider_cli.py
# PURPOSE: Verifies research simulate provider cli behavior and regression
#         expectations.
# DEPS:    json, os, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )


def _create_research_artifact(tmp_path: Path, monkeypatch, symbol: str = "AAPL") -> str:
    from atlas_agent.research.session import run_research_session

    (tmp_path / "memory").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    artifact = run_research_session(
        symbol=symbol,
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


class TestSimulateProviderCreatesArtifact:
    def test_creates_provider_response_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id]) == 0
        out = capsys.readouterr().out
        assert "Simulated provider response created" in out
        assert "Symbol: AAPL" in out
        assert "Provider: deterministic-mock" in out
        assert "Provider Response ID:" in out
        assert ".atlas/research/AAPL/provider_responses/" in out

    def test_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "simulate-provider", prompt_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        artifact_path = tmp_path / out["artifact_path"]
        assert artifact_path.exists()
        data = json.loads(artifact_path.read_text())
        assert data["schema_version"] == "1"
        assert data["provider"] == "deterministic-mock"
        assert data["provider_status"] == "simulated"
        assert data["mode"] == "paper"
        assert data["source_prompt_packet_id"] == prompt_id
        assert data["recommendation"] in ("provider_response_review_ready", "manual_review_required")
        assert "response_sections" in data
        assert "safety_checks" in data
        assert "passed_checks" in data
        assert "failed_checks" in data
        assert "redaction_summary" in data


class TestSimulateProviderJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_created"
        assert data["symbol"] == "AAPL"
        assert data["source_prompt_packet_id"] == prompt_id
        assert "provider_response_id" in data
        assert data["provider"] == "deterministic-mock"
        assert data["recommendation"] in ("provider_response_review_ready", "manual_review_required")
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "simulate-provider", prompt_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestSimulateProviderTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id]) == 0
        out = capsys.readouterr().out
        assert "Simulated provider response created" in out
        assert "Symbol:" in out
        assert "Source Prompt Packet ID:" in out
        assert "Provider Response ID:" in out
        assert "Recommendation:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "simulate-provider", prompt_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "/home/" not in out


class TestSimulateProviderUnsupportedProvider:
    def test_unsupported_provider_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--provider", "openai", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"
        assert "openai" not in data.get("message", "").lower()


class TestSimulateProviderSecretProvider:
    def test_secret_shaped_provider_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--provider", "sk-LEAKEDSECRET123", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "sk-" not in out
        assert "SECRET" not in out
        assert "TOKEN" not in out
        assert "Bearer" not in out
        assert "APCA" not in out


class TestSimulateProviderInvalidPromptId:
    def test_invalid_prompt_id_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", "../secret", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "invalid" in data["status"].lower()


class TestSimulateProviderMissingPrompt:
    def test_missing_prompt_packet_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", "missing-id-12345678", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "not_found" in data["status"].lower() or "artifact" in data.get("message", "").lower()


class TestSimulateProviderMalformedPrompt:
    def test_malformed_prompt_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        prompt_file.write_text("not json {[", encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "malformed" in data["status"].lower() or "malformed" in data.get("message", "").lower()


class TestSimulateProviderUnsupportedSchema:
    def test_unsupported_schema_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["schema_version"] = "999"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "unsupported" in result["status"].lower() or "unsupported" in result["message"].lower()


class TestSimulateProviderUnsafePromptSymbol:
    def test_unsafe_symbol_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["symbol"] = "/Users/natan/secret"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower() or "symbol" in result.get("message", "").lower()
        responses_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses"
        assert not responses_dir.exists() or not any(responses_dir.iterdir())
        unsafe_dir = tmp_path / ".atlas" / "research" / "Users"
        assert not unsafe_dir.exists()


class TestSimulateProviderRedaction:
    FORBIDDEN_FRAGMENTS = [
        "Authorization",
        "Bearer",
        "APCA",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "API_KEY",
        "sk-",
        "/Users/",
        "/private/var/",
        "broker.example.com",
    ]

    def test_redacts_unsafe_prompt_fields(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["user_context"]["summary"] = (
            "Analysis done in /Users/natan/secret. Auth: Bearer abc123. Token: sk-LEAKEDSECRET123. "
            "Broker: broker.example.com. Key: APCA-API-KEY-ID. SECRET=value TOKEN=value PASSWORD=value API_KEY=value"
        )
        data["user_context"]["thesis"] = "Thesis with /private/var/folders/leak"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out

        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"

        responses_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses"
        files = list(responses_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        artifact = json.loads(artifact_text)

        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_text, f"Forbidden fragment found in artifact: {frag}"

        # Forbidden fragments must not leak; count may be zero when sanitization
        # prevented them from entering the response upstream.


class TestSimulateProviderResponseSafety:
    def test_detects_live_trading_language(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        # Inject unsafe text into user_context so it propagates into response
        data["user_context"]["summary"] = "This is a summary that mentions submit live order and guaranteed profit."
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        artifact_path = tmp_path / result["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        # The response should have failed safety checks and set recommendation
        assert artifact["recommendation"] == "manual_review_required"
        assert artifact["failed_checks"] > 0
        # The phrase should not appear in output or artifact
        assert "submit live order" not in out.lower()
        artifact_text = artifact_path.read_text()
        assert "submit live order" not in artifact_text.lower()


class TestSimulateProviderNoApiKeyReads:
    def test_env_keys_not_leaked(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key-1234567890")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-google-key-1234567890")
        monkeypatch.setenv("APCA_API_KEY_ID", "APCA-test-key-123")
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        assert "sk-openai-test-key" not in out
        assert "sk-ant-test-key" not in out
        assert "AIza-test-google-key" not in out
        assert "APCA-test-key" not in out

        responses_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses"
        files = list(responses_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        assert "sk-openai-test-key" not in artifact_text
        assert "sk-ant-test-key" not in artifact_text
        assert "AIza-test-google-key" not in artifact_text
        assert "APCA-test-key" not in artifact_text


class TestSimulateProviderNoExecutionPath:
    def test_no_broker_or_approval_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with (
            patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config),
            patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route,
            patch(
                "atlas_agent.execution.approval.ApprovalManager.create_pending_order"
            ) as mock_approval,
            patch(
                "atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker"
            ) as mock_broker,
        ):
            assert main(["research", "simulate-provider", prompt_id]) == 0
        mock_route.assert_not_called()
        mock_approval.assert_not_called()
        mock_broker.assert_not_called()


class TestSimulateProviderNoPendingOrders:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id]) == 0
        pending_dir = tmp_path / "pending_orders"
        if pending_dir.exists():
            assert not any(pending_dir.iterdir())


class TestSimulateProviderEventLogging:
    def test_event_logged_with_safe_payload(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        response_events = [e for e in events if e.get("event_type") == "research_provider_response_created"]
        assert len(response_events) == 1
        payload = response_events[0].get("payload", {})
        assert "provider_response_id" in payload
        assert "source_prompt_packet_id" in payload
        assert "artifact_path" in payload
        assert "symbol" in payload
        assert "mode" in payload
        assert "schema_version" in payload
        assert "response_sections" not in payload
        assert "response_summary" not in payload
        assert "safety_checks" not in payload


class TestSimulateProviderTamperedMetadata:
    FORBIDDEN_FRAGMENTS = [
        "Authorization",
        "Bearer",
        "APCA",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "API_KEY",
        "sk-",
        "/Users/",
        "/private/var/",
        "broker.example.com",
    ]

    def test_tampered_source_run_id_path_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["source_run_id"] = "/Users/natan/secret"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        responses_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses"
        assert not responses_dir.exists() or not any(responses_dir.iterdir())
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment leaked in CLI output: {frag}"

    def test_tampered_source_run_id_sk_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["source_run_id"] = "sk-LEAKEDSECRET"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        responses_dir = tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses"
        assert not responses_dir.exists() or not any(responses_dir.iterdir())
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment leaked in CLI output: {frag}"

    def test_tampered_prompt_provider_sanitized(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["provider"] = "sk-LEAKEDSECRET Authorization Bearer APCA SECRET TOKEN PASSWORD API_KEY /Users/natan/secret broker.example.com"
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is True
        artifact_path = tmp_path / result["artifact_path"]
        artifact_text = artifact_path.read_text()
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_text, f"Forbidden fragment found in artifact: {frag}"
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"
        artifact = json.loads(artifact_text)
        # Provider metadata must be sanitized to safe value
        assert artifact["metadata"]["source_provider"] == "unknown"

    def test_artifact_full_text_denylist(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["user_context"]["summary"] = (
            "Analysis with Authorization Bearer APCA SECRET TOKEN PASSWORD API_KEY "
            "sk-LEAKEDSECRET123 /Users/natan/secret /private/var/folders/leak broker.example.com"
        )
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        artifact_path = tmp_path / result["artifact_path"]
        artifact_text = artifact_path.read_text()
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_text, f"Forbidden fragment found in artifact: {frag}"
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"

    def test_event_payload_denylist(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        data = json.loads(prompt_file.read_text())
        data["user_context"]["summary"] = (
            "Analysis with Authorization Bearer APCA SECRET TOKEN PASSWORD API_KEY "
            "sk-LEAKEDSECRET123 /Users/natan/secret /private/var/folders/leak broker.example.com"
        )
        prompt_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "simulate-provider", prompt_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        response_events = [e for e in events if e.get("event_type") == "research_provider_response_created"]
        assert len(response_events) == 1
        event_text = json.dumps(response_events[0])
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in event_text, f"Forbidden fragment found in event payload: {frag}"
