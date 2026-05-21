from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_response_review_result import (
    PROVIDER_RESPONSE_REVIEW_RESULT_VERSION,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE,
    build_provider_response_review_result_dict,
    create_provider_response_review_result,
    find_provider_response_review_result_by_id,
    iter_provider_response_review_result_artifacts,
    load_and_validate_provider_response_review_result,
    provider_response_review_result_sha256,
    replay_provider_response_review_result,
    safe_validate_provider_response_review_result_data,
    summarize_provider_response_review_result_state,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION
from atlas_agent.research.provider_response_schema_contract import create_provider_response_schema_contract


def _raise_if_called(*args, **kwargs):
    raise AssertionError("Config/secrets loader must not be called")


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


def _create_sandbox_request(tmp_path: Path, monkeypatch, prompt_id: str) -> str:
    from atlas_agent.research.llm_sandbox import build_llm_sandbox_request_from_prompt_packet

    monkeypatch.chdir(tmp_path)
    result = build_llm_sandbox_request_from_prompt_packet(
        workspace_path=tmp_path,
        prompt_packet_id=prompt_id,
        event_logger=None,
    )
    return result["sandbox_request_id"]


def _create_provider_call_plan(tmp_path: Path, monkeypatch, sandbox_id: str) -> str:
    from atlas_agent.research.provider_call_plan import create_provider_call_plan

    monkeypatch.chdir(tmp_path)
    result = create_provider_call_plan(
        workspace_path=tmp_path,
        sandbox_request_id=sandbox_id,
        provider_id="custom-openai-compatible",
        model_id="gpt-4o",
    )
    return result["provider_call_plan_id"]


def _create_provider_execution_dry_run(tmp_path: Path, monkeypatch, plan_id: str) -> str:
    from atlas_agent.research.provider_execution_dry_run import create_provider_execution_dry_run

    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_dry_run(
        workspace_path=tmp_path,
        provider_call_plan_id=plan_id,
    )
    return result["provider_execution_dry_run_id"]


def _create_provider_execution_state(tmp_path: Path, monkeypatch, dry_run_id: str) -> str:
    from atlas_agent.research.provider_execution_state import create_provider_execution_state

    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_state(
        workspace_path=tmp_path,
        provider_execution_dry_run_id=dry_run_id,
        requested_state="dry_run_only",
    )
    return result["provider_execution_state_id"]


def _create_provider_execution_audit_packet(tmp_path: Path, monkeypatch, state_id: str) -> str:
    from atlas_agent.research.provider_execution_audit_packet import create_provider_execution_audit_packet

    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_audit_packet(
        workspace_path=tmp_path,
        provider_execution_state_id=state_id,
    )
    return result["provider_execution_audit_packet_id"]


def _create_provider_execution_readiness_report(tmp_path: Path, monkeypatch, audit_packet_id: str) -> str:
    from atlas_agent.research.provider_execution_readiness_report import create_provider_execution_readiness_report

    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_readiness_report(
        workspace_path=tmp_path,
        provider_execution_audit_packet_id=audit_packet_id,
    )
    return result["provider_execution_readiness_report_id"]


def _create_provider_preflight_freeze(tmp_path: Path, monkeypatch, readiness_report_id: str) -> str:
    from atlas_agent.research.provider_preflight_freeze import create_provider_preflight_freeze

    monkeypatch.chdir(tmp_path)
    result = create_provider_preflight_freeze(
        workspace_path=tmp_path,
        readiness_report_id=readiness_report_id,
    )
    return result["provider_preflight_freeze_id"]


def _create_provider_opt_in_policy(tmp_path: Path, monkeypatch, freeze_id: str) -> str:
    from atlas_agent.research.provider_opt_in_policy import create_provider_opt_in_policy

    monkeypatch.chdir(tmp_path)
    result = create_provider_opt_in_policy(
        workspace_path=tmp_path,
        freeze_id=freeze_id,
    )
    return result["provider_opt_in_policy_id"]


def _create_provider_credential_boundary(tmp_path: Path, monkeypatch, policy_id: str) -> str:
    from atlas_agent.research.provider_credential_boundary import create_provider_credential_boundary

    monkeypatch.chdir(tmp_path)
    result = create_provider_credential_boundary(
        workspace_path=tmp_path,
        policy_id=policy_id,
    )
    return result["provider_credential_boundary_id"]


def _create_provider_outbound_payload_preview(tmp_path: Path, monkeypatch, boundary_id: str) -> str:
    from atlas_agent.research.provider_outbound_payload_preview import create_provider_outbound_payload_preview

    monkeypatch.chdir(tmp_path)
    result = create_provider_outbound_payload_preview(
        workspace_path=tmp_path,
        boundary_id=boundary_id,
    )
    return result["provider_outbound_payload_preview_id"]


def _create_provider_response_intake_policy(tmp_path: Path, monkeypatch, preview_id: str) -> str:
    from atlas_agent.research.provider_response_intake_policy import create_provider_response_intake_policy

    monkeypatch.chdir(tmp_path)
    result = create_provider_response_intake_policy(
        workspace_path=tmp_path,
        preview_id=preview_id,
    )
    return result["provider_response_intake_policy_id"]


def _create_provider_request_response_pairing(tmp_path: Path, monkeypatch, intake_policy_id: str) -> str:
    from atlas_agent.research.provider_request_response_pairing import create_provider_request_response_pairing

    monkeypatch.chdir(tmp_path)
    result = create_provider_request_response_pairing(
        workspace_path=tmp_path,
        intake_policy_id=intake_policy_id,
    )
    return result["provider_request_response_pairing_id"]


def _full_chain_to_schema_contract(tmp_path: Path, monkeypatch) -> tuple[str, str, str, str, str]:
    run_id = _create_research_artifact(tmp_path, monkeypatch)
    prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
    sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, prompt_id)
    plan_id = _create_provider_call_plan(tmp_path, monkeypatch, sandbox_id)
    dry_run_id = _create_provider_execution_dry_run(tmp_path, monkeypatch, plan_id)
    state_id = _create_provider_execution_state(tmp_path, monkeypatch, dry_run_id)
    audit_id = _create_provider_execution_audit_packet(tmp_path, monkeypatch, state_id)
    readiness_id = _create_provider_execution_readiness_report(tmp_path, monkeypatch, audit_id)
    freeze_id = _create_provider_preflight_freeze(tmp_path, monkeypatch, readiness_id)
    policy_id = _create_provider_opt_in_policy(tmp_path, monkeypatch, freeze_id)
    boundary_id = _create_provider_credential_boundary(tmp_path, monkeypatch, policy_id)
    preview_id = _create_provider_outbound_payload_preview(tmp_path, monkeypatch, boundary_id)
    intake_policy_id = _create_provider_response_intake_policy(tmp_path, monkeypatch, preview_id)
    pairing_id = _create_provider_request_response_pairing(tmp_path, monkeypatch, intake_policy_id)
    schema_result = create_provider_response_schema_contract(tmp_path, pairing_id)
    schema_contract_id = schema_result["provider_response_schema_contract_id"]
    return run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id


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


class TestProviderResponseReviewResultConfigless:
    def test_review_result_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result", schema_contract_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_review_result_created"
        assert "provider_response_review_result_id" in data
        assert data["manual_review_gate_open"] is False
        assert data["provider_response_trusted"] is False

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_review_result_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_review_result_list"
        assert len(data["items"]) >= 1

    def test_review_result_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-show", review_result_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_review_result_shown"
        assert data["provider_response_review_result_id"] == review_result_id

    def test_review_result_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-validate", review_result_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True

    def test_review_result_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-replay", review_result_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_review_result_summary_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-summary", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["manual_review_gate_open"] is False
        assert data["review_result_present"] is False
        assert data["provider_response_trusted"] is False

    def test_review_result_doctor_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result-doctor", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_review_result_doctor"
        assert data["manual_review_gate_open"] is False
        assert data["review_result_present"] is False
        assert data["provider_response_trusted"] is False


class TestProviderResponseReviewResultCreation:
    def test_valid_review_result_creates_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_response_review_result_created"
        assert result["manual_review_gate_open"] is False
        assert result["provider_response_trusted"] is False
        review_result_id = result["provider_response_review_result_id"]
        artifact_path = tmp_path / result["artifact_path"]
        assert artifact_path.exists()

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "provider_response_review_result"
        assert data["contract_version"] == PROVIDER_RESPONSE_REVIEW_RESULT_VERSION
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert "reviewer_identity_policy" in data
        assert "review_notes_policy" in data
        assert "review_bounds_policy" in data
        assert "review_redaction_policy" in data
        assert "review_validation_policy" in data
        assert "trust_upgrade_policy" in data
        assert "trading_separation_policy" in data
        assert "broker_separation_policy" in data
        assert "review_event_policy" in data
        assert "future_response_requirements" in data
        assert data["review_result_present"] is False
        assert data["manual_review_gate_open"] is False
        assert data["manual_review_completed"] is False
        assert data["reviewer_identity_recorded"] is False
        assert data["review_notes_stored"] is False
        assert data["review_notes_bounded"] is True
        assert data["review_notes_redacted"] is True
        assert data["review_decision_allows_use"] is False
        assert data["review_decision_allows_trust_upgrade"] is False
        assert data["review_decision_allows_trading_interpretation"] is False
        assert data["review_decision_allows_order_creation"] is False
        assert data["review_decision_allows_order_approval"] is False
        assert data["review_decision_allows_broker_call"] is False
        assert data["provider_response_received"] is False
        assert data["provider_response_trusted"] is False
        assert data["provider_response_imported"] is False
        assert data["provider_response_reviewed"] is False
        assert data["provider_response_can_create_orders"] is False
        assert data["provider_response_can_approve_orders"] is False
        assert data["provider_response_can_call_broker"] is False
        assert data["raw_response_body_stored"] is False
        assert data["raw_prompt_body_stored"] is False
        assert data["provider_enabled"] is False
        assert data["network_enabled"] is False
        assert data["credentials_loaded"] is False

    def test_create_json_envelope_includes_all_false_safety_flags(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-review-result", schema_contract_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_review_result_created"

        required_false_fields = [
            "review_result_present",
            "manual_review_gate_open",
            "manual_review_completed",
            "reviewer_identity_recorded",
            "review_notes_stored",
            "review_decision_allows_use",
            "review_decision_allows_trust_upgrade",
            "review_decision_allows_trading_interpretation",
            "review_decision_allows_order_creation",
            "review_decision_allows_order_approval",
            "review_decision_allows_broker_call",
            "provider_response_received",
            "provider_response_trusted",
            "provider_response_imported",
            "provider_response_reviewed",
            "provider_response_can_create_orders",
            "provider_response_can_approve_orders",
            "provider_response_can_call_broker",
            "provider_call_allowed",
            "actual_provider_call_made",
            "outbound_request_sent",
            "trading_signal_generated",
            "approval_created",
            "pending_order_created",
            "broker_touched",
        ]
        for field in required_false_fields:
            assert field in data, f"Missing field in create JSON envelope: {field}"
            assert data[field] is False, f"Field {field} should be False, got {data[field]}"

        assert data["review_notes_bounded"] is True
        assert data["review_notes_redacted"] is True

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"

    def test_artifact_path_is_correct(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)

        assert ".atlas/research/" in result["artifact_path"]
        assert "provider_response_review_results" in result["artifact_path"]
        assert result["artifact_path"].endswith(".json")

    def test_output_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            main(["research", "provider-response-review-result-list", "--json"])

        out = capsys.readouterr().out
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"


class TestProviderResponseReviewResultArtifactDenylist:
    def test_artifact_does_not_contain_raw_forbidden_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text(encoding="utf-8")

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"Forbidden fragment in artifact: {frag}"

    def test_artifact_does_not_store_raw_denylist_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        denylist = data.get("denylist_metadata", {})
        assert denylist.get("forbidden_fragments_raw_stored") is False

    def test_artifact_does_not_include_authorization_bearer(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text(encoding="utf-8")

        assert "Authorization" not in text
        assert "Bearer" not in text

    def test_artifact_does_not_include_absolute_paths(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text(encoding="utf-8")

        assert "/Users/" not in text
        assert "/private/var/" not in text

    def test_artifact_does_not_include_raw_request_body(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert "raw_request_body" not in data

    def test_artifact_does_not_include_raw_response_body(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert "raw_response_body" not in data

    def test_artifact_does_not_include_raw_prompt_text(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert "raw_prompt_text" not in data
        assert "raw_prompt_body" not in data

    def test_artifact_does_not_include_raw_review_notes(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert "raw_review_notes" not in data

    def test_artifact_does_not_include_provider_trace_ids(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert "provider_trace_id" not in data
        assert "x_request_id" not in data
        assert "request_id" not in data
        assert "response_id" not in data


class TestProviderResponseReviewResultSummary:
    def test_summary_on_valid_run_reports_review_result_contract_recorded(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        result = summarize_provider_response_review_result_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_response_review_result_summary"
        assert result["review_result_status"] == "review_result_contract_recorded"
        assert result["review_result_state"] == "review_contract_recorded_no_response_present"
        assert result["review_decision"] == "no_decision_recorded"
        assert result["review_result_present"] is False
        assert result["manual_review_gate_open"] is False
        assert result["provider_response_trusted"] is False

    def test_summary_before_review_result_exists_reports_safe_missing(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )

        result = summarize_provider_response_review_result_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "missing_provider_response_review_result"
        assert result["provider_response_review_result_id"] is None
        assert result["review_result_present"] is False
        assert result["manual_review_gate_open"] is False
        assert result["provider_response_trusted"] is False

    def test_summary_on_missing_run_fails_safe(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = summarize_provider_response_review_result_state(tmp_path, "run-99999999")
        assert result["ok"] is True
        assert result["status"] == "missing_provider_response_review_result"

    def test_summary_does_not_write_artifacts_or_events(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        events_before = list((tmp_path / "events").glob("*.jsonl"))
        results_before = list((tmp_path / ".atlas" / "research").rglob("provider_response_review_results/*.json"))
        count_before = len(results_before)

        summarize_provider_response_review_result_state(tmp_path, run_id)

        events_after = list((tmp_path / "events").glob("*.jsonl"))
        results_after = list((tmp_path / ".atlas" / "research").rglob("provider_response_review_results/*.json"))
        assert len(results_after) == count_before
        assert len(events_after) == len(events_before)


class TestProviderResponseReviewResultDoctor:
    def test_doctor_on_valid_run_reports_review_contract_recorded_no_response_present(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_response_review_result_doctor"
        assert result["review_health"] in (
            "review_contract_recorded_no_response_present",
            "incomplete_expected",
            "blocked_until_response_artifact_exists",
        )
        assert result["review_result_present"] is False
        assert result["manual_review_gate_open"] is False
        assert result["provider_response_trusted"] is False
        assert "future_provider_response_artifact" in result["missing_artifacts"]

    def test_doctor_reports_missing_future_response_as_expected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, run_id)
        assert "future_provider_response_artifact" in result["missing_artifacts"]
        assert any("Future provider response artifact is not yet present" in w for w in result["warnings"])

    def test_doctor_reports_manual_review_gate_closed(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, run_id)
        assert "manual_review_gate_required" in result["blocking_reasons"]

    def test_doctor_reports_no_actual_review_result_present(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, run_id)
        assert "review_result_not_present" in result["blocking_reasons"]

    def test_doctor_before_review_result_exists_reports_safe_missing(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_response_review_result_doctor"
        assert result["review_health"] == "review_result_missing"

    def test_doctor_on_missing_run_fails_safe(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        result = doctor_provider_response_review_result(tmp_path, "run-99999999")
        assert result["ok"] is True
        assert result["status"] == "research_provider_response_review_result_doctor"
        assert result["review_health"] == "review_result_missing"

    def test_doctor_does_not_write_artifacts_or_events(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        events_before = list((tmp_path / "events").glob("*.jsonl"))
        results_before = list((tmp_path / ".atlas" / "research").rglob("provider_response_review_results/*.json"))
        count_before = len(results_before)

        from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
        doctor_provider_response_review_result(tmp_path, run_id)

        events_after = list((tmp_path / "events").glob("*.jsonl"))
        results_after = list((tmp_path / ".atlas" / "research").rglob("provider_response_review_results/*.json"))
        assert len(results_after) == count_before
        assert len(events_after) == len(events_before)

    def test_doctor_output_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            main(["research", "provider-response-review-result-doctor", run_id, "--json"])

        out = capsys.readouterr().out
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"


class TestProviderResponseReviewResultSafetyTamper:
    def _tamper_artifact(self, tmp_path: Path, monkeypatch) -> tuple[Path, dict[str, Any]]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        return artifact_path, data

    def test_tampered_lineage_fails_validation(self, tmp_path: Path, monkeypatch) -> None:
        artifact_path, data = self._tamper_artifact(tmp_path, monkeypatch)
        data["source_provider_response_schema_contract_id"] = "tampered-id"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error is not None
        assert cleaned is None

    def _tamper_boolean_and_assert(
        self, tmp_path: Path, monkeypatch, field: str, value: bool
    ) -> None:
        artifact_path, data = self._tamper_artifact(tmp_path, monkeypatch)
        data[field] = value
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error is not None, f"Expected error for {field}={value}"
        assert cleaned is None

    def test_impossible_boolean_review_result_present_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_result_present", True)

    def test_impossible_boolean_manual_review_gate_open_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "manual_review_gate_open", True)

    def test_impossible_boolean_manual_review_completed_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "manual_review_completed", True)

    def test_impossible_boolean_reviewer_identity_recorded_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "reviewer_identity_recorded", True)

    def test_impossible_boolean_review_notes_stored_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_notes_stored", True)

    def test_impossible_boolean_review_decision_allows_use_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_decision_allows_use", True)

    def test_impossible_boolean_review_decision_allows_trust_upgrade_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_decision_allows_trust_upgrade", True)

    def test_impossible_boolean_review_decision_allows_order_creation_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_decision_allows_order_creation", True)

    def test_impossible_boolean_review_decision_allows_order_approval_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_decision_allows_order_approval", True)

    def test_impossible_boolean_review_decision_allows_broker_call_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_decision_allows_broker_call", True)

    def test_impossible_boolean_provider_response_trusted_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "provider_response_trusted", True)

    def test_impossible_boolean_provider_response_can_create_orders_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "provider_response_can_create_orders", True)

    def test_impossible_boolean_trading_signal_generated_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "trading_signal_generated", True)

    def test_impossible_boolean_approval_created_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "approval_created", True)

    def test_impossible_boolean_pending_order_created_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "pending_order_created", True)

    def test_impossible_boolean_broker_touched_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "broker_touched", True)

    def test_impossible_boolean_review_notes_bounded_false_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_notes_bounded", False)

    def test_impossible_boolean_review_notes_redacted_false_fails(self, tmp_path: Path, monkeypatch) -> None:
        self._tamper_boolean_and_assert(tmp_path, monkeypatch, "review_notes_redacted", False)

    def test_forbidden_positive_claim_in_policy_fails(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        unsafe_values = [
            "provider calls enabled",
            "Authorization",
            "Bearer",
            "API_KEY",
            "sk-LEAKEDSECRET",
            "buy",
            "sell",
            "submit order",
            "provider response trusted",
            "manual review gate open",
            "auto execute",
            "create order",
            "approve order",
            "call broker",
        ]
        for value in unsafe_values:
            data["review_result_status"] = value
            cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
            assert error is not None, f"Expected error for status={value}"
            assert cleaned is None
            data["review_result_status"] = "review_result_contract_recorded"


class TestProviderResponseReviewResultReplayValidation:
    def test_valid_review_result_validates(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]

        artifact = load_and_validate_provider_response_review_result(
            tmp_path / result["artifact_path"], tmp_path
        )
        assert artifact["provider_response_review_result_id"] == review_result_id

    def test_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["artifact_hash"] = "tampered_hash"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_hash_mismatch"
        assert cleaned is None

    def test_source_schema_contract_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_response_schema_contract_id"] = "schema-99999999"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_schema_contract_missing"
        assert cleaned is None

    def test_source_schema_contract_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_schema_contract_hash"] = "tampered_hash"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_schema_contract_hash_mismatch"
        assert cleaned is None

    def test_source_pairing_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_request_response_pairing_id"] = "pairing-99999999"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_pairing_missing"
        assert cleaned is None

    def test_source_pairing_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_pairing_hash"] = "tampered_hash"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_pairing_hash_mismatch"
        assert cleaned is None

    def test_source_response_intake_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_response_intake_policy_id"] = "policy-99999999"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_response_intake_missing"
        assert cleaned is None

    def test_source_response_intake_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_response_intake_policy_hash"] = "tampered_hash"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_response_intake_hash_mismatch"
        assert cleaned is None

    def test_source_payload_preview_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_outbound_payload_preview_id"] = "preview-99999999"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_payload_preview_missing"
        assert cleaned is None

    def test_source_payload_preview_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_payload_preview_hash"] = "tampered_hash"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path=tmp_path)
        assert error == "provider_response_review_result_source_payload_preview_hash_mismatch"
        assert cleaned is None

    def test_replay_match_envelope(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]

        replay = replay_provider_response_review_result(tmp_path, review_result_id)
        assert replay["ok"] is True
        assert replay["match"] is True

    def test_replay_mismatch_envelope(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        review_result_id = result["provider_response_review_result_id"]
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["review_result_status"] = "manual_review_required"
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        replay = replay_provider_response_review_result(tmp_path, review_result_id)
        assert replay["ok"] is True
        assert replay["match"] is False


class TestProviderResponseReviewResultTimelineCheckDossier:
    def test_check_artifacts_counts_provider_response_review_results(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        assert result["counts"]["provider_response_review_results"] >= 1

    def test_check_artifacts_detects_review_result_tampering(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        data["review_result_present"] = True
        data["artifact_hash"] = provider_response_review_result_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in result["issues"]}
        assert "provider_response_review_result_impossible_boolean" in issue_codes

    def test_timeline_links_review_result(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.research.session import build_research_timeline
        result = build_research_timeline(tmp_path, run_id_filter=run_id)
        entries = result["entries"]
        assert len(entries) >= 1
        found = False
        for entry in entries:
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pcp in sr.get("provider_call_plans", []):
                        for ped in pcp.get("provider_execution_dry_runs", []):
                            for s in ped.get("provider_execution_states", []):
                                for a in s.get("provider_execution_audit_packets", []):
                                    for r in a.get("provider_execution_readiness_reports", []):
                                        for f in r.get("provider_preflight_freezes", []):
                                            for pol in f.get("provider_opt_in_policies", []):
                                                for b in pol.get("provider_credential_boundaries", []):
                                                    for pp in b.get("provider_outbound_payload_previews", []):
                                                        for intake in pp.get("provider_response_intake_policies", []):
                                                            for pairing in intake.get("provider_request_response_pairings", []):
                                                                for contract in pairing.get("provider_response_schema_contracts", []):
                                                                    if contract.get("provider_response_review_results"):
                                                                        found = True
        assert found, "Timeline did not link review result under schema contract"

    def test_timeline_preserves_real_lineage_and_false_safety_flags(self, tmp_path: Path, monkeypatch) -> None:
        import json as json_mod
        from atlas_agent.research.session import build_research_timeline

        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        result = build_research_timeline(tmp_path, run_id_filter=run_id)

        out = json_mod.dumps(result, indent=2, sort_keys=True)
        assert "Circular reference detected" not in out
        assert "Traceback" not in out

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in timeline JSON: {frag}"

        entries = result.get("entries", [])
        assert len(entries) >= 1
        review_result_entry: dict[str, Any] | None = None
        for entry in entries:
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pcp in sr.get("provider_call_plans", []):
                        for ped in pcp.get("provider_execution_dry_runs", []):
                            for s in ped.get("provider_execution_states", []):
                                for a in s.get("provider_execution_audit_packets", []):
                                    for r in a.get("provider_execution_readiness_reports", []):
                                        for f in r.get("provider_preflight_freezes", []):
                                            for pol in f.get("provider_opt_in_policies", []):
                                                for b in pol.get("provider_credential_boundaries", []):
                                                    for pp in b.get("provider_outbound_payload_previews", []):
                                                        for ip in pp.get("provider_response_intake_policies", []):
                                                            pairings = ip.get("provider_request_response_pairings", [])
                                                            for pairing in pairings:
                                                                contracts = pairing.get("provider_response_schema_contracts", [])
                                                                for contract in contracts:
                                                                    for rr in contract.get("provider_response_review_results", []):
                                                                        if rr.get("provider_response_review_result_id"):
                                                                            review_result_entry = rr
        assert review_result_entry is not None, "Timeline did not include review result under schema contract"

        expected_lineage_fields = (
            "provider_response_review_result_id",
            "source_provider_response_schema_contract_id",
            "source_provider_request_response_pairing_id",
        )
        for field in expected_lineage_fields:
            assert review_result_entry.get(field), f"{field} missing from review result timeline entry"
            assert review_result_entry.get(field) is not None

        expected_false_fields = (
            "provider_call_allowed",
            "actual_provider_call_made",
        )
        for field in expected_false_fields:
            assert field in review_result_entry, f"{field} missing from review result timeline entry"
            assert review_result_entry[field] is False

    def test_dossier_includes_review_result_summary(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        create_provider_response_review_result(tmp_path, schema_contract_id)

        from atlas_agent.events.log import EventLogger
        from atlas_agent.research.session import build_dossier

        event_logger = EventLogger(tmp_path / "events")
        result = build_dossier(tmp_path, run_id, event_logger=event_logger)

        assert result["artifact_counts"]["provider_response_review_results"] >= 1
        assert "provider_response_review_result" in result["summaries"]
        assert result["summaries"]["provider_response_review_result"]["review_result_count"] >= 1


class TestProviderResponseReviewResultInvalidLeakage:
    """Regression tests: invalid/tampered review result artifacts must not leak raw fields through list/timeline/check-artifacts."""

    def _tamper_and_list(self, tmp_path: Path, monkeypatch, capsys, tamper_fn) -> tuple[dict[str, Any], str, int]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id, intake_policy_id, pairing_id, schema_contract_id = _full_chain_to_schema_contract(
            tmp_path, monkeypatch
        )
        result = create_provider_response_review_result(tmp_path, schema_contract_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        tamper_fn(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        code = main(["research", "provider-response-review-result-list", "--json"])
        out = capsys.readouterr().out
        return json.loads(out), out, code

    def test_invalid_artifact_does_not_leak_raw_values_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(data):
            data["provider_response_review_result_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
            data["artifact_hash"] = provider_response_review_result_sha256(data)

        data, out, code = self._tamper_and_list(tmp_path, monkeypatch, capsys, tamper)
        assert code == 0
        assert data["ok"] is True
        assert "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com" not in out
        assert "APCA" not in out
        assert "SECRET" not in out
        assert "TOKEN" not in out
        assert "sk-" not in out
        assert "broker.example.com" not in out
        invalid_items = [i for i in data["items"] if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["provider_response_review_result_id"] == "<invalid>"
        assert invalid_items[0]["provider_id"] == "unknown"
        assert invalid_items[0]["model_id"] == "unknown"
        assert invalid_items[0]["review_result_status"] == "invalid"
        assert invalid_items[0]["review_result_state"] == "invalid"
        assert invalid_items[0]["review_decision"] == "invalid"
        assert invalid_items[0].get("error_code") == "invalid_provider_response_review_result_artifact"
