from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main


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


def _create_plan(tmp_path: Path, monkeypatch, run_id: str) -> str:
    from atlas_agent.research.session import create_paper_plan

    monkeypatch.chdir(tmp_path)
    artifact = create_paper_plan(
        workspace_path=tmp_path,
        run_id=run_id,
        event_logger=None,
    )
    return artifact.plan_id


def _create_verify(tmp_path: Path, monkeypatch, plan_id: str) -> str:
    from atlas_agent.research.session import verify_paper_plan

    monkeypatch.chdir(tmp_path)
    artifact = verify_paper_plan(
        workspace_path=tmp_path,
        plan_id=plan_id,
        event_logger=None,
    )
    return artifact.verification_id


def _create_evaluate(tmp_path: Path, monkeypatch, plan_id: str) -> str:
    import csv
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
    artifact = evaluate_paper_plan(
        workspace_path=tmp_path,
        plan_id=plan_id,
        data_path=csv_path,
        event_logger=None,
    )
    return artifact.evaluation_id


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


class TestDossierCreatesArtifact:
    def test_creates_dossier_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        _create_verify(tmp_path, monkeypatch, plan_id)
        _create_evaluate(tmp_path, monkeypatch, plan_id)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        _create_response_review(tmp_path, monkeypatch, response_id)

        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research dossier created" in out
        assert "Symbol: AAPL" in out
        assert "Source Run ID:" in out
        assert "Dossier ID:" in out
        assert "Recommendation:" in out
        assert ".atlas/research/AAPL/dossiers/" in out

    def test_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        _create_verify(tmp_path, monkeypatch, plan_id)
        _create_evaluate(tmp_path, monkeypatch, plan_id)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        _create_response_review(tmp_path, monkeypatch, response_id)

        monkeypatch.chdir(tmp_path)
        main(["research", "dossier", run_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        artifact_path = tmp_path / out["artifact_path"]
        assert artifact_path.exists()
        data = json.loads(artifact_path.read_text())
        assert data["schema_version"] == "1"
        assert data["provider"] == "deterministic-dossier"
        assert data["mode"] == "paper"
        assert data["source_run_id"] == run_id
        assert data["recommendation"] in ("research_dossier_ready", "manual_review_required")
        assert "workflow_status" in data
        assert "artifact_counts" in data
        assert "linked_artifacts" in data
        assert "summaries" in data
        assert "safety_summary" in data
        assert "missing_links" in data
        assert "redaction_summary" in data


class TestDossierJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_dossier_created"
        assert data["symbol"] == "AAPL"
        assert data["source_run_id"] == run_id
        assert "dossier_id" in data
        assert data["provider"] == "deterministic-dossier"
        assert data["recommendation"] in ("research_dossier_ready", "manual_review_required")
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        main(["research", "dossier", run_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestDossierTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research dossier created" in out
        assert "Symbol:" in out
        assert "Source Run ID:" in out
        assert "Dossier ID:" in out
        assert "Recommendation:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        main(["research", "dossier", run_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "/home/" not in out


class TestDossierInvalidRunId:
    def test_invalid_run_id_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", "../secret", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "invalid" in data["status"].lower()


class TestDossierMissingResearch:
    def test_missing_research_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", "missing-id-12345678", "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "not_found" in data["status"].lower() or "artifact" in data.get("message", "").lower()


class TestDossierMalformedResearch:
    def test_malformed_research_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        research_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        research_file.write_text("not json {[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "malformed" in data["status"].lower() or "malformed" in data.get("message", "").lower()


class TestDossierUnsupportedSchema:
    def test_unsupported_schema_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        research_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(research_file.read_text())
        data["schema_version"] = "999"
        research_file.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "unsupported" in result["status"].lower() or "unsupported" in result["message"].lower()


class TestDossierUnsafeSymbol:
    def test_unsafe_symbol_fails_closed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        research_file = list((tmp_path / ".atlas" / "research" / "AAPL").glob("*.json"))[0]
        data = json.loads(research_file.read_text())
        data["symbol"] = "/Users/natan/secret"
        research_file.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 1
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is False
        assert "invalid" in result["status"].lower() or "symbol" in result.get("message", "").lower()
        dossiers_dir = tmp_path / ".atlas" / "research" / "AAPL" / "dossiers"
        assert not dossiers_dir.exists() or not any(dossiers_dir.iterdir())
        unsafe_dir = tmp_path / ".atlas" / "research" / "Users"
        assert not unsafe_dir.exists()


class TestDossierRedaction:
    def test_redacts_unsafe_linked_artifact_fields(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        _create_verify(tmp_path, monkeypatch, plan_id)
        _create_evaluate(tmp_path, monkeypatch, plan_id)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        _create_response_review(tmp_path, monkeypatch, response_id)

        # Tamper fields that build_dossier actually copies into linked_artifacts / summaries
        plan_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "plans").glob("*.json"))[0]
        plan_data = json.loads(plan_file.read_text())
        plan_data["artifact_path"] = ".atlas/research/AAPL/plans/plan-with-/Users/natan/secret-path.json"
        plan_file.write_text(json.dumps(plan_data), encoding="utf-8")

        verify_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "verifications").glob("*.json"))[0]
        verify_data = json.loads(verify_file.read_text())
        verify_data["recommendation"] = "Bearer sk-VERIFYLEAKEDSECRET"
        verify_file.write_text(json.dumps(verify_data), encoding="utf-8")

        prompt_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "prompts").glob("*.json"))[0]
        prompt_data = json.loads(prompt_file.read_text())
        prompt_data["artifact_path"] = ".atlas/research/AAPL/prompts/prompt-with-/private/var/secret-path.json"
        prompt_file.write_text(json.dumps(prompt_data), encoding="utf-8")

        response_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "provider_responses").glob("*.json"))[0]
        response_data = json.loads(response_file.read_text())
        response_data["provider"] = "broker.example.com"
        response_data["artifact_path"] = ".atlas/research/AAPL/provider_responses/resp-with-APCALEAKED.json"
        response_file.write_text(json.dumps(response_data), encoding="utf-8")

        review_file = list((tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews").glob("*.json"))[0]
        review_data = json.loads(review_file.read_text())
        review_data["artifact_path"] = ".atlas/research/AAPL/response_reviews/review-with-SECRET_TOKEN.json"
        review_file.write_text(json.dumps(review_data), encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 0
        out = capsys.readouterr().out

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment found in CLI output: {frag}"

        dossiers_dir = tmp_path / ".atlas" / "research" / "AAPL" / "dossiers"
        files = list(dossiers_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        artifact = json.loads(artifact_text)

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in artifact_text, f"Forbidden fragment found in artifact: {frag}"

        # Verify event payload is also sanitized
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        dossier_events = [e for e in events if e.get("event_type") == "research_dossier_created"]
        assert len(dossier_events) == 1
        payload_text = json.dumps(dossier_events[0].get("payload", {}))
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in payload_text, f"Forbidden fragment found in event payload: {frag}"


class TestDossierIncompleteChain:
    def test_incomplete_chain_manual_review(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        artifact_path = tmp_path / result["artifact_path"]
        artifact = json.loads(artifact_path.read_text())
        assert artifact["recommendation"] == "manual_review_required"
        assert "incomplete_chain" in artifact["warnings"]
        assert "no_plan" in artifact["missing_links"]
        assert "no_prompt_packet" in artifact["missing_links"]
        assert "no_provider_response" in artifact["missing_links"]
        assert "no_response_review" in artifact["missing_links"]


class TestDossierNoApiKeyReads:
    def test_env_keys_not_leaked(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key-1234567890")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-google-key-1234567890")
        monkeypatch.setenv("APCA_API_KEY_ID", "APCA-test-key-123")
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        assert "sk-openai-test-key" not in out
        assert "sk-ant-test-key" not in out
        assert "AIza-test-google-key" not in out
        assert "APCA-test-key" not in out

        dossiers_dir = tmp_path / ".atlas" / "research" / "AAPL" / "dossiers"
        files = list(dossiers_dir.glob("*.json"))
        assert len(files) == 1
        artifact_text = files[0].read_text()
        assert "sk-openai-test-key" not in artifact_text
        assert "sk-ant-test-key" not in artifact_text
        assert "AIza-test-google-key" not in artifact_text
        assert "APCA-test-key" not in artifact_text


class TestDossierNoExecutionPath:
    def test_no_broker_or_approval_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        with (
            patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route,
            patch(
                "atlas_agent.execution.approval.ApprovalManager.create_pending_order"
            ) as mock_approval,
            patch(
                "atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker"
            ) as mock_broker,
        ):
            assert main(["research", "dossier", run_id]) == 0
        mock_route.assert_not_called()
        mock_approval.assert_not_called()
        mock_broker.assert_not_called()


class TestDossierNoConfigSecretsLoaded:
    def test_does_not_call_atlas_config_or_read_env_atlas(self, tmp_path: Path, capsys, monkeypatch) -> None:
        # Write a .env.atlas with obvious secrets in the workspace
        env_atlas = tmp_path / ".env.atlas"
        env_atlas.write_text(
            "OPENAI_API_KEY=sk-LEAKEDSECRET123\n"
            "APCA_API_KEY_ID=APCASECRET123\n"
            "ATLAS_SECRET_TOKEN=SECRET_TOKEN_VALUE\n",
            encoding="utf-8",
        )

        run_id = _create_research_artifact(tmp_path, monkeypatch)
        plan_id = _create_plan(tmp_path, monkeypatch, run_id)
        _create_verify(tmp_path, monkeypatch, plan_id)
        _create_evaluate(tmp_path, monkeypatch, plan_id)
        prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
        response_id = _create_provider_response(tmp_path, monkeypatch, prompt_id)
        _create_response_review(tmp_path, monkeypatch, response_id)

        monkeypatch.chdir(tmp_path)

        def _raise_if_called(*args, **kwargs):
            raise AssertionError("AtlasConfig.from_env must not be called")

        with (
            patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called),
            patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called),
        ):
            assert main(["research", "dossier", run_id, "--json"]) == 0

        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["ok"] is True
        assert result["status"] == "research_dossier_created"

        # No secrets leaked in CLI output
        assert "sk-LEAKEDSECRET" not in out
        assert "APCASECRET" not in out
        assert "SECRET_TOKEN_VALUE" not in out
        assert "OPENAI_API_KEY" not in out
        assert ".env.atlas" not in out

        # No secrets leaked in artifact
        artifact_path = tmp_path / result["artifact_path"]
        artifact_text = artifact_path.read_text()
        assert "sk-LEAKEDSECRET" not in artifact_text
        assert "APCASECRET" not in artifact_text
        assert "SECRET_TOKEN_VALUE" not in artifact_text
        assert "OPENAI_API_KEY" not in artifact_text
        assert ".env.atlas" not in artifact_text

        # No secrets in event payload
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        dossier_events = [e for e in events if e.get("event_type") == "research_dossier_created"]
        assert len(dossier_events) == 1
        payload_text = json.dumps(dossier_events[0].get("payload", {}))
        assert "sk-LEAKEDSECRET" not in payload_text
        assert "APCASECRET" not in payload_text
        assert "SECRET_TOKEN_VALUE" not in payload_text


class TestDossierNoPendingOrders:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id]) == 0
        pending_dir = tmp_path / "pending_orders"
        if pending_dir.exists():
            assert not any(pending_dir.iterdir())


class TestDossierEventLogging:
    def test_event_logged_with_safe_payload(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        assert main(["research", "dossier", run_id, "--json"]) == 0
        event_files = list((tmp_path / "events").glob("*.jsonl"))
        assert event_files
        events = [json.loads(line) for line in event_files[0].read_text().strip().splitlines()]
        dossier_events = [e for e in events if e.get("event_type") == "research_dossier_created"]
        assert len(dossier_events) == 1
        payload = dossier_events[0].get("payload", {})
        assert "dossier_id" in payload
        assert "source_run_id" in payload
        assert "artifact_path" in payload
        assert "symbol" in payload
        assert "mode" in payload
        assert "schema_version" in payload
        assert "artifact_counts" in payload
        assert "checks" not in payload
        assert "response_summary" not in payload
