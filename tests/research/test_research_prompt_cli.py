# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_prompt_cli.py
# PURPOSE: Verifies research prompt cli behavior and regression expectations.
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


class TestResearchPromptCreatesArtifact:
    def test_prompt_creates_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research prompt packet created" in out
        assert "Symbol: AAPL" in out
        assert f"Source Run ID: {run_id}" in out
        assert "Prompt Packet ID:" in out
        assert ".atlas/research/AAPL/prompts/" in out

    def test_prompt_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "prompt", run_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        packet_path = tmp_path / out["artifact_path"]
        assert packet_path.exists()
        data = json.loads(packet_path.read_text())
        assert data["schema_version"] == "1"
        assert data["source_run_id"] == run_id
        assert data["mode"] == "paper"
        assert data["provider"] == "deterministic"
        assert "prompt_packet_id" in data
        assert "system_boundary" in data
        assert "user_context" in data
        assert "allowed_uses" in data
        assert "forbidden_uses" in data
        assert "redaction_summary" in data
        assert "warnings" in data
        assert "metadata" in data

    def test_system_boundary_values(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "prompt", run_id])
        prompt_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        files = list(prompt_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        sb = data["system_boundary"]
        assert sb["paper_only"] is True
        assert sb["analysis_only"] is True
        assert sb["no_trading_advice"] is True
        assert sb["no_live_trading_authorization"] is True
        assert sb["no_broker_submit"] is True
        assert sb["no_pending_orders"] is True
        assert sb["no_approvals"] is True
        assert sb["no_api_network_call_required"] is True

    def test_source_artifact_not_modified(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        before = source_file.read_text()
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "prompt", run_id])
        after = source_file.read_text()
        assert before == after


class TestResearchPromptJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_prompt_packet_created"
        assert data["symbol"] == "AAPL"
        assert data["source_run_id"] == run_id
        assert "prompt_packet_id" in data
        assert "artifact_path" in data
        assert "warnings" in data
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "prompt", run_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestResearchPromptTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research prompt packet created" in out
        assert "Symbol:" in out
        assert "Source Run ID:" in out
        assert "Prompt Packet ID:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "prompt", run_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "/home/" not in out


class TestResearchPromptInvalidRunId:
    def test_invalid_run_id_exits_nonzero(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", "../secret", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "invalid" in data["status"].lower()

    def test_empty_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", "", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False


class TestResearchPromptNotFound:
    def test_missing_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", "missing-id-12345678", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "not_found" in data["status"].lower() or "artifact" in data.get("message", "").lower()


class TestResearchPromptUnsupportedSchema:
    def test_unsupported_schema_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["schema_version"] = "999"
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "unsupported" in result["status"].lower() or "unsupported" in result["message"].lower()


class TestResearchPromptMalformedSource:
    def test_malformed_source_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        source_file.write_text("not json {[")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "malformed" in result["status"].lower() or "malformed" in result.get("message", "").lower()


class TestResearchPromptRedaction:
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

    def test_redacts_unsafe_source_fields(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["summary"] = (
            "Analysis done in /Users/natan/secret. Auth: Bearer abc123. Token: sk-LEAKEDSECRET123. "
            "Broker: broker.example.com. Key: APCA-API-KEY-ID. SECRET=value TOKEN=value PASSWORD=value API_KEY=value"
        )
        data["thesis"] = "Thesis with /private/var/folders/leak"
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 0
        out = capsys.readouterr().out

        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"

        prompt_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        files = list(prompt_dir.glob("*.json"))
        assert len(files) == 1
        packet_text = files[0].read_text()
        packet = json.loads(packet_text)

        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in packet_text, f"Forbidden fragment found in artifact: {frag}"

        assert packet["redaction_summary"]["redacted_fragments_count"] > 0

    def test_event_payload_no_forbidden_fragments(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["summary"] = "Authorization: Bearer abc123. SECRET=value TOKEN=value APCA sk-LEAKED"
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        prompt_events = [e for e in events if e.get("event_type") == "research_prompt_packet_created"]
        assert len(prompt_events) == 1
        payload = prompt_events[0].get("payload", {})
        payload_text = json.dumps(payload)
        for frag in self.FORBIDDEN_FRAGMENTS:
            assert frag not in payload_text, f"Forbidden fragment found in event payload: {frag}"
        assert "user_context" not in payload
        assert "summary" not in payload
        assert "thesis" not in payload


class TestResearchPromptUnsafeSourceSymbol:
    def test_tampered_unsafe_source_symbol_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["symbol"] = "/Users/natan/secret"
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower() or "symbol" in result.get("message", "").lower()
        # No prompt artifact should be created
        prompts_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        assert not prompts_dir.exists() or not any(prompts_dir.iterdir())
        # Unsafe path should not be created
        unsafe_dir = tmp_path / ".atlas" / "research" / "Users"
        assert not unsafe_dir.exists()

    def test_unsafe_symbol_no_path_leak(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["symbol"] = "AAPL/../../secret"
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        # No raw unsafe symbol in output
        assert "../../secret" not in out
        assert "/Users/" not in out
        assert "natan" not in out.lower()
        # No prompt artifact created
        prompts_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        assert not prompts_dir.exists() or not any(prompts_dir.iterdir())


class TestResearchPromptTruncation:
    def test_truncation_when_context_too_long(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        source_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(source_file.read_text())
        data["summary"] = "A" * 5000
        data["thesis"] = "B" * 5000
        data["market_context"] = "C" * 5000
        data["paper_only_plan"] = "D" * 5000
        source_file.write_text(json.dumps(data))
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--max-context-chars", "500"]) == 0
        prompt_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        files = list(prompt_dir.glob("*.json"))
        assert len(files) == 1
        packet = json.loads(files[0].read_text())
        assert packet["redaction_summary"]["truncated"] is True
        total = sum(
            len(v) if isinstance(v, str) else sum(len(x) for x in v if isinstance(x, str))
            for v in packet["user_context"].values()
        )
        assert total <= 500


class TestResearchPromptInvalidMaxContextChars:
    def test_zero(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--max-context-chars", "0", "--json"]) == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is False

    def test_negative(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--max-context-chars", "-1", "--json"]) == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is False

    def test_too_large(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--max-context-chars", "99999", "--json"]) == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is False


class TestResearchPromptNoApiKeyReads:
    def test_env_keys_not_leaked(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key-1234567890")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-google-key-1234567890")
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        assert "sk-openai-test-key" not in out
        assert "sk-ant-test-key" not in out
        assert "AIza-test-google-key" not in out

        prompt_dir = tmp_path / ".atlas" / "research" / "AAPL" / "prompts"
        files = list(prompt_dir.glob("*.json"))
        assert len(files) == 1
        packet_text = files[0].read_text()
        assert "sk-openai-test-key" not in packet_text
        assert "sk-ant-test-key" not in packet_text
        assert "AIza-test-google-key" not in packet_text


class TestResearchPromptNoExecutionPath:
    def test_no_broker_or_approval_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
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
            assert main(["research", "prompt", run_id]) == 0
        mock_route.assert_not_called()
        mock_approval.assert_not_called()
        mock_broker.assert_not_called()


class TestResearchPromptNoPendingOrders:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id]) == 0
        pending_dir = tmp_path / "pending_orders"
        if pending_dir.exists():
            assert not any(pending_dir.iterdir())


class TestResearchPromptEventLogging:
    def test_event_logged_with_safe_payload(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "prompt", run_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        prompt_events = [e for e in events if e.get("event_type") == "research_prompt_packet_created"]
        assert len(prompt_events) == 1
        payload = prompt_events[0].get("payload", {})
        assert "prompt_packet_id" in payload
        assert "source_run_id" in payload
        assert "artifact_path" in payload
        assert "symbol" in payload
        assert "mode" in payload
        assert "schema_version" in payload
        assert "user_context" not in payload
        assert "summary" not in payload
        assert "thesis" not in payload
