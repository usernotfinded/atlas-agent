# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_review_response_cli.py
# PURPOSE: Verifies research review response cli behavior and regression
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


class TestReviewResponseCreatesArtifact:
    def test_creates_response_review_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id]) == 0
        out = capsys.readouterr().out
        assert "Provider response review created" in out
        assert "Symbol: AAPL" in out
        assert "Provider: deterministic-review" in out
        assert "Response Review ID:" in out
        assert ".atlas/research/AAPL/response_reviews/" in out

    def test_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "review-response", response_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        artifact_path = tmp_path / out["artifact_path"]
        assert artifact_path.exists()
        data = json.loads(artifact_path.read_text())
        assert data["schema_version"] == "1"
        assert data["provider"] == "deterministic-review"
        assert data["mode"] == "paper"
        assert data["source_provider_response_id"] == response_id
        assert data["recommendation"] in ("provider_response_review_ready", "manual_review_required")
        assert "checks" in data
        assert "passed_checks" in data
        assert "failed_checks" in data
        assert "redaction_summary" in data


class TestReviewResponseJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_response_review_created"
        assert data["symbol"] == "AAPL"
        assert data["source_provider_response_id"] == response_id
        assert "response_review_id" in data
        assert data["provider"] == "deterministic-review"
        assert data["recommendation"] in ("provider_response_review_ready", "manual_review_required")
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "review-response", response_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestReviewResponseTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id]) == 0
        out = capsys.readouterr().out
        assert "Provider response review created" in out
        assert "Symbol:" in out
        assert "Source Provider Response ID:" in out
        assert "Response Review ID:" in out
        assert "Recommendation:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "review-response", response_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "/home/" not in out


class TestReviewResponseInvalidProviderResponseId:
    def test_invalid_provider_response_id_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", "../secret", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "invalid" in data["status"].lower()


class TestReviewResponseMissingProviderResponse:
    def test_missing_provider_response_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", "missing-id-12345678", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "not_found" in data["status"].lower() or "artifact" in data.get("message", "").lower()


class TestReviewResponseMalformedProviderResponse:
    def test_malformed_provider_response_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        response_file.write_text("not json {[", encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "malformed" in data["status"].lower() or "malformed" in data.get("message", "").lower()


class TestReviewResponseUnsupportedSchema:
    def test_unsupported_schema_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["schema_version"] = "999"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "unsupported" in result["status"].lower() or "unsupported" in result["message"].lower()


class TestReviewResponseUnsafeProviderResponseSymbol:
    def test_unsafe_symbol_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["symbol"] = "/Users/natan/secret"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower() or "symbol" in result.get("message", "").lower()
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        assert not reviews_dir.exists() or not any(reviews_dir.iterdir())
        unsafe_dir = tmp_path / ".atlas" / "research" / "Users"
        assert not unsafe_dir.exists()


class TestReviewResponseRedaction:
    def test_redacts_unsafe_provider_response_fields(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["response_summary"] = (
            "Analysis done in /Users/natan/secret. Auth: Bearer abc123. Token: sk-LEAKEDSECRET123. "
            "Broker: broker.example.com. Key: APCA-API-KEY-ID. SECRET=value TOKEN=value PASSWORD=value API_KEY=value"
        )
        data["response_sections"] = {"scope_review": "Thesis with /private/var/folders/leak"}
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 0
        out = capsys.readouterr().out

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"

        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        files = list(reviews_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        artifact = json.loads(artifact_text)

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_text, f"Forbidden fragment found in artifact: {frag}"


class TestReviewResponseSafety:
    def test_detects_live_trading_language(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["response_summary"] = "This response mentions submit live order and guaranteed profit."
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        artifact_path = tmp_path / result["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        assert artifact["recommendation"] == "manual_review_required"
        assert artifact["failed_checks"] > 0
        assert "submit live order" not in out.lower()
        artifact_text = artifact_path.read_text()
        assert "submit live order" not in artifact_text.lower()


class TestReviewResponseNoApiKeyReads:
    def test_env_keys_not_leaked(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key-1234567890")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-google-key-1234567890")
        monkeypatch.setenv("APCA_API_KEY_ID", "APCA-test-key-123")
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        assert "sk-openai-test-key" not in out
        assert "sk-ant-test-key" not in out
        assert "AIza-test-google-key" not in out
        assert "APCA-test-key" not in out

        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        files = list(reviews_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        assert "sk-openai-test-key" not in artifact_text
        assert "sk-ant-test-key" not in artifact_text
        assert "AIza-test-google-key" not in artifact_text
        assert "APCA-test-key" not in artifact_text


class TestReviewResponseNoExecutionPath:
    def test_no_broker_or_approval_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
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
            assert main(["research", "review-response", response_id]) == 0
        mock_route.assert_not_called()
        mock_approval.assert_not_called()
        mock_broker.assert_not_called()


class TestReviewResponseNoPendingOrders:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id]) == 0
        pending_dir = tmp_path / "pending_orders"
        if pending_dir.exists():
            assert not any(pending_dir.iterdir())


class TestReviewResponseEventLogging:
    def test_event_logged_with_safe_payload(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        review_events = [e for e in events if e.get("event_type") == "research_response_review_created"]
        assert len(review_events) == 1
        payload = review_events[0].get("payload", {})
        assert "response_review_id" in payload
        assert "source_provider_response_id" in payload
        assert "artifact_path" in payload
        assert "symbol" in payload
        assert "mode" in payload
        assert "schema_version" in payload
        assert "checks" not in payload
        assert "response_summary" not in payload


class TestReviewResponseUnsafeLineageIds:
    def test_unsafe_source_run_id_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["source_run_id"] = "/Users/natan/secret"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        captured = capsys.readouterr()
        out = captured.out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower()
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        assert not reviews_dir.exists() or not any(reviews_dir.iterdir())
        combined = out + captured.err
        for frag in ("/Users/", "natan", "secret", "sk-", "Authorization", "Bearer", "APCA", "SECRET", "TOKEN", "PASSWORD", "API_KEY"):
            assert frag not in combined, f"Forbidden fragment leaked: {frag}"

    def test_unsafe_source_prompt_packet_id_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["source_prompt_packet_id"] = "sk-LEAKEDSECRET"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        captured = capsys.readouterr()
        out = captured.out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower()
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        assert not reviews_dir.exists() or not any(reviews_dir.iterdir())
        combined = out + captured.err
        for frag in ("sk-", "LEAKEDSECRET", "SECRET", "TOKEN", "PASSWORD", "Authorization", "Bearer", "APCA"):
            assert frag not in combined, f"Forbidden fragment leaked: {frag}"


class TestReviewResponseArtifactDenylist:
    def test_artifact_fulltext_denylist_covers_lineage_metadata(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["source_run_id"] = "APCA-SECRET-TOKEN"
        data["source_prompt_packet_id"] = "broker.example.com"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        assert not reviews_dir.exists() or not any(reviews_dir.iterdir())


class TestReviewResponseEventDenylist:
    def test_event_payload_denylist_on_tampered_lineage(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        data = json.loads(response_file.read_text())
        data["source_run_id"] = "sk-TAMPEREDRUNID"
        response_file.write_text(json.dumps(data), encoding="utf-8")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "review-response", response_id, "--json"]) == 1
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        if event_files:
            events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
            review_events = [e for e in events if e.get("event_type") == "research_response_review_created"]
            assert len(review_events) == 0, "No response review event should be emitted for tampered lineage"
