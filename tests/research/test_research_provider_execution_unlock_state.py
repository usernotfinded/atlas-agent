from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_execution_unlock_state import (
    PROVIDER_EXECUTION_UNLOCK_STATE_VERSION,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE,
    build_provider_execution_unlock_state_dict,
    create_provider_execution_unlock_state,
    doctor_provider_execution_unlock_state,
    find_provider_execution_unlock_state_by_id,
    iter_provider_execution_unlock_state_artifacts,
    load_and_validate_provider_execution_unlock_state,
    provider_execution_unlock_state_sha256,
    replay_provider_execution_unlock_state,
    safe_validate_provider_execution_unlock_state_data,
    summarize_provider_execution_unlock_state,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION
from atlas_agent.research.provider_response_review_result import create_provider_response_review_result


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


def _create_provider_response_schema_contract(tmp_path: Path, monkeypatch, pairing_id: str) -> str:
    from atlas_agent.research.provider_response_schema_contract import create_provider_response_schema_contract

    monkeypatch.chdir(tmp_path)
    result = create_provider_response_schema_contract(
        workspace_path=tmp_path,
        pairing_id=pairing_id,
    )
    return result["provider_response_schema_contract_id"]


def _create_provider_response_review_result(tmp_path: Path, monkeypatch, schema_contract_id: str) -> str:
    monkeypatch.chdir(tmp_path)
    result = create_provider_response_review_result(
        workspace_path=tmp_path,
        schema_contract_id=schema_contract_id,
    )
    return result["provider_response_review_result_id"]


def _full_chain_to_review_result(tmp_path: Path, monkeypatch) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    run_id = _create_research_artifact(tmp_path, monkeypatch)
    prompt_id = _create_prompt_packet(tmp_path, monkeypatch, run_id)
    sandbox_id = _create_sandbox_request(tmp_path, monkeypatch, prompt_id)
    plan_id = _create_provider_call_plan(tmp_path, monkeypatch, sandbox_id)
    dry_run_id = _create_provider_execution_dry_run(tmp_path, monkeypatch, plan_id)
    state_id = _create_provider_execution_state(tmp_path, monkeypatch, dry_run_id)
    audit_packet_id = _create_provider_execution_audit_packet(tmp_path, monkeypatch, state_id)
    readiness_report_id = _create_provider_execution_readiness_report(tmp_path, monkeypatch, audit_packet_id)
    freeze_id = _create_provider_preflight_freeze(tmp_path, monkeypatch, readiness_report_id)
    policy_id = _create_provider_opt_in_policy(tmp_path, monkeypatch, freeze_id)
    boundary_id = _create_provider_credential_boundary(tmp_path, monkeypatch, policy_id)
    preview_id = _create_provider_outbound_payload_preview(tmp_path, monkeypatch, boundary_id)
    intake_id = _create_provider_response_intake_policy(tmp_path, monkeypatch, preview_id)
    pairing_id = _create_provider_request_response_pairing(tmp_path, monkeypatch, intake_id)
    schema_contract_id = _create_provider_response_schema_contract(tmp_path, monkeypatch, pairing_id)
    review_result_id = _create_provider_response_review_result(tmp_path, monkeypatch, schema_contract_id)
    return (
        run_id, prompt_id, sandbox_id, plan_id, dry_run_id, state_id,
        audit_packet_id, readiness_report_id, freeze_id, policy_id,
        boundary_id, preview_id, intake_id, pairing_id, schema_contract_id,
        review_result_id,
    )


# ---------------------------------------------------------------------------
# Configless safety
# ---------------------------------------------------------------------------

class TestConfiglessSafety:
    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_create_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state", review_result_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_list_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-list", "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_show_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        result = create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-show", result["provider_execution_unlock_state_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_validate_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        result = create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-validate", result["provider_execution_unlock_state_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_replay_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        result = create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-replay", result["provider_execution_unlock_state_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_summary_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-summary", run_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_doctor_unlock_state_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)
        create_provider_execution_unlock_state(tmp_path, review_result_id)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-doctor", run_id, "--json"]):
            assert main() == 0


# ---------------------------------------------------------------------------
# Unlock state creation
# ---------------------------------------------------------------------------

class TestUnlockStateCreation:
    def test_create_unlock_state_creates_artifact(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_execution_unlock_state_created"
        assert result["provider_execution_unlock_state_id"]
        assert result["source_provider_response_review_result_id"] == review_result_id
        assert result["unlock_state_status"] == "unlock_state_recorded"
        assert result["unlock_state"] == "manual_unlock_required"
        assert result["current_state"] == "disabled"
        assert Path(tmp_path / result["artifact_path"]).exists()

    def test_unlock_state_includes_all_policy_structures(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert "required_prerequisites" in data
        assert "satisfied_prerequisites" in data
        assert "missing_prerequisites" in data
        assert "blocking_reasons" in data
        assert "unlock_transition_policy" in data
        assert "manual_unlock_policy" in data
        assert "credential_unlock_policy" in data
        assert "provider_adapter_unlock_policy" in data
        assert "network_unlock_policy" in data
        assert "request_send_unlock_policy" in data
        assert "response_import_unlock_policy" in data
        assert "trust_upgrade_policy" in data
        assert "trading_separation_policy" in data
        assert "broker_separation_policy" in data
        assert "rollback_policy" in data

    def test_manual_unlock_required_is_true(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["manual_unlock_required"] is True
        assert data["manual_unlock_granted"] is False
        assert data["provider_execution_unlocked"] is False
        assert data["provider_adapter_present"] is False
        assert data["provider_call_allowed"] is False
        assert data["actual_provider_call_made"] is False
        assert data["outbound_request_sent"] is False
        assert data["provider_response_trusted"] is False

    def test_artifact_path_is_correct(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        assert ".atlas/research/AAPL/provider_execution_unlock_states/" in result["artifact_path"]

    def test_output_is_denylist_clean(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        text = json.dumps(result)
        assert "Authorization" not in text
        assert "Bearer" not in text
        assert "/Users/" not in text


# ---------------------------------------------------------------------------
# Artifact denylist
# ---------------------------------------------------------------------------

class TestArtifactDenylist:
    def test_artifact_does_not_contain_forbidden_fragments(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text()

        assert "Authorization" not in text
        assert "Bearer" not in text
        assert "API_KEY" not in text
        assert "sk-" not in text
        assert "/Users/" not in text
        assert "broker.example.com" not in text

    def test_artifact_does_not_store_raw_denylist_fragments(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["denylist_metadata"]["forbidden_fragments_raw_stored"] is False

    def test_artifact_does_not_include_request_or_response_body(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert "raw_request_body" not in data
        assert "raw_response_body" not in data
        assert "raw_prompt_body" not in data
        assert "raw_review_notes" not in data


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_reports_unlock_state_recorded(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        result = summarize_provider_execution_unlock_state(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_execution_unlock_state_summary"
        assert result["provider_execution_unlocked"] is False
        assert result["provider_call_allowed"] is False
        assert result["manual_unlock_granted"] is False
        assert result["provider_execution_unlock_state_id"] is not None

    def test_summary_before_unlock_state_exists_reports_missing(self, tmp_path, monkeypatch):
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        result = summarize_provider_execution_unlock_state(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "missing_provider_execution_unlock_state"
        assert result["provider_execution_unlock_state_id"] is None

    def test_summary_on_missing_run_fails_safely(self, tmp_path):
        result = summarize_provider_execution_unlock_state(tmp_path, "missing-run-123")

        assert result["ok"] is True
        assert result["status"] == "missing_provider_execution_unlock_state"


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class TestDoctor:
    def test_doctor_reports_manual_unlock_required(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        result = doctor_provider_execution_unlock_state(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_execution_unlock_state_doctor"
        assert result["provider_execution_unlocked"] is False
        assert result["provider_call_allowed"] is False
        assert result["manual_unlock_granted"] is False
        assert "manual_unlock_required" in result["unlock_health"] or "blocked" in result["unlock_health"]

    def test_doctor_reports_missing_future_prerequisites(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        result = doctor_provider_execution_unlock_state(tmp_path, run_id)

        missing = result.get("missing_prerequisites", [])
        assert any("provider_adapter" in m for m in missing)
        assert any("credential_loader" in m for m in missing)
        assert any("network_policy" in m for m in missing)

    def test_doctor_before_unlock_state_exists_reports_missing(self, tmp_path, monkeypatch):
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        result = doctor_provider_execution_unlock_state(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_execution_unlock_state_doctor"
        assert result["unlock_health"] == "unlock_state_missing"

    def test_doctor_on_missing_run_fails_safely(self, tmp_path):
        result = doctor_provider_execution_unlock_state(tmp_path, "missing-run-123")

        assert result["ok"] is True
        assert result["status"] == "research_provider_execution_unlock_state_doctor"
        assert result["unlock_health"] == "unlock_state_missing"

    def test_doctor_output_is_denylist_clean(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        result = doctor_provider_execution_unlock_state(tmp_path, run_id)
        text = json.dumps(result)

        assert "Authorization" not in text
        assert "Bearer" not in text
        assert "/Users/" not in text


# ---------------------------------------------------------------------------
# Safety / tamper
# ---------------------------------------------------------------------------

class TestSafetyTamper:
    def test_tampered_unlock_state_id_fails(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlock_state_id"] = "../tampered"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "invalid_provider_execution_unlock_state_lineage"

    def test_tampered_source_review_result_id_fails(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_provider_response_review_result_id"] = "../tampered"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "invalid_provider_execution_unlock_state_lineage"

    def test_impossible_boolean_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlocked"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_impossible_boolean"

    def test_manual_unlock_granted_true_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["manual_unlock_granted"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_impossible_boolean"

    def test_forbidden_unlock_claim_in_policy_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["unlock_transition_policy"]["manual_unlock_grants_provider_call_in_this_batch"] = "Authorization"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_malformed"

    def test_no_raw_artifact_serialization_on_tamper(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlocked"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, _ = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None


# ---------------------------------------------------------------------------
# Replay / validation
# ---------------------------------------------------------------------------

class TestReplayValidation:
    def test_valid_unlock_state_replay_matches(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        replay = replay_provider_execution_unlock_state(tmp_path, result["provider_execution_unlock_state_id"])

        assert replay["ok"] is True
        assert replay["match"] is True

    def test_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["symbol"] = "TAMPERED"
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        replay = replay_provider_execution_unlock_state(tmp_path, result["provider_execution_unlock_state_id"])
        assert replay["match"] is False

    def test_source_review_result_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        # Delete review result
        from atlas_agent.research.provider_response_review_result import find_provider_response_review_result_by_id
        rr_path = find_provider_response_review_result_by_id(tmp_path, review_result_id)
        if rr_path:
            rr_path.unlink()

        replay = replay_provider_execution_unlock_state(tmp_path, result["provider_execution_unlock_state_id"])
        assert replay["match"] is False

    def test_replay_returns_safety_flags(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        replay = replay_provider_execution_unlock_state(tmp_path, result["provider_execution_unlock_state_id"])

        assert replay["provider_execution_unlocked"] is False
        assert replay["provider_call_allowed"] is False
        assert replay["manual_unlock_granted"] is False


# ---------------------------------------------------------------------------
# Timeline / check / dossier integration
# ---------------------------------------------------------------------------

class TestTimelineCheckDossier:
    def test_check_artifacts_counts_unlock_states(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import check_research_artifacts

        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        result = check_research_artifacts(tmp_path)

        assert result["counts"]["provider_execution_unlock_states"] >= 1

    def test_check_artifacts_detects_unlock_state_tampering(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import check_research_artifacts

        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlocked"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        check_result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in check_result["issues"]}
        assert "provider_execution_unlock_state_impossible_boolean" in issue_codes

    def test_timeline_links_unlock_state(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import build_research_timeline

        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        timeline = build_research_timeline(tmp_path, run_id_filter=run_id)

        entries = timeline.get("entries", [])
        assert len(entries) > 0
        # Navigate through nested timeline to find unlock states
        found_unlock_state = False
        for entry in entries:
            for prompt in entry.get("prompts", []):
                for sr in prompt.get("sandbox_requests", []):
                    for pcp in sr.get("provider_call_plans", []):
                        for ped in pcp.get("provider_execution_dry_runs", []):
                            for pes in ped.get("provider_execution_states", []):
                                for peap in pes.get("provider_execution_audit_packets", []):
                                    for perr in peap.get("provider_execution_readiness_reports", []):
                                        for ppf in perr.get("provider_preflight_freezes", []):
                                            for pop in ppf.get("provider_opt_in_policies", []):
                                                for pcb in pop.get("provider_credential_boundaries", []):
                                                    for pp in pcb.get("provider_outbound_payload_previews", []):
                                                        for pip in pp.get("provider_response_intake_policies", []):
                                                            for prrp in pip.get("provider_request_response_pairings", []):
                                                                for prsc in prrp.get("provider_response_schema_contracts", []):
                                                                    for prrr in prsc.get("provider_response_review_results", []):
                                                                        for pues in prrr.get("provider_execution_unlock_states", []):
                                                                            if pues.get("provider_execution_unlock_state_id"):
                                                                                found_unlock_state = True
                                                                                assert pues.get("provider_execution_unlocked") is False
                                                                                assert pues.get("provider_call_allowed") is False
        assert found_unlock_state

    def test_dossier_includes_unlock_state_summary(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import build_dossier

        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        create_provider_execution_unlock_state(tmp_path, review_result_id)
        dossier = build_dossier(tmp_path, run_id)

        counts = dossier.get("artifact_counts", {})
        assert counts.get("provider_execution_unlock_states", 0) >= 1

        linked = dossier.get("linked_artifacts", [])
        unlock_state_linked = [a for a in linked if a.get("type") == "provider_execution_unlock_state"]
        assert len(unlock_state_linked) >= 1


# ---------------------------------------------------------------------------
# List / find
# ---------------------------------------------------------------------------

class TestListFind:
    def test_list_returns_unlock_states(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        items = iter_provider_execution_unlock_state_artifacts(tmp_path)

        ids = {i["provider_execution_unlock_state_id"] for i in items if not i.get("_invalid")}
        assert result["provider_execution_unlock_state_id"] in ids

    def test_find_by_id_returns_path(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        path = find_provider_execution_unlock_state_by_id(tmp_path, result["provider_execution_unlock_state_id"])

        assert path is not None
        assert path.exists()

    def test_find_by_invalid_id_returns_none(self, tmp_path):
        path = find_provider_execution_unlock_state_by_id(tmp_path, "nonexistent-id-123")
        assert path is None


# ---------------------------------------------------------------------------
# Invalid artifact leakage
# ---------------------------------------------------------------------------

class TestInvalidArtifactLeakage:
    def test_invalid_unlock_state_uses_safe_sentinel(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        # Corrupt JSON
        artifact_path.write_text("{not valid json")

        items = iter_provider_execution_unlock_state_artifacts(tmp_path)
        invalid_items = [i for i in items if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["provider_execution_unlock_state_id"] == "<invalid>"
        assert invalid_items[0]["unlock_state_status"] == "invalid"

    def test_malformed_unlock_state_skipped_in_list(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        artifact_path.write_text("{not valid json")

        items = iter_provider_execution_unlock_state_artifacts(tmp_path)
        valid_items = [i for i in items if not i.get("_invalid")]
        assert len(valid_items) == 0


# ---------------------------------------------------------------------------
# Load and validate
# ---------------------------------------------------------------------------

class TestLoadValidate:
    def test_load_and_validate_succeeds(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = load_and_validate_provider_execution_unlock_state(artifact_path, tmp_path)

        assert data["provider_execution_unlock_state_id"] == result["provider_execution_unlock_state_id"]

    def test_load_and_validate_fails_on_tamper(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlocked"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        from atlas_agent.research.session import ResearchSessionError
        with pytest.raises(ResearchSessionError):
            load_and_validate_provider_execution_unlock_state(artifact_path, tmp_path)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_unsupported_schema_rejected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["schema_version"] = "999"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "unsupported_provider_execution_unlock_state_schema"


# ---------------------------------------------------------------------------
# Boolean safety flags completeness
# ---------------------------------------------------------------------------

class TestBooleanSafetyFlags:
    def test_all_must_be_false_flags_are_false(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
            assert data.get(flag) is False, f"Expected {flag} to be False"

    def test_unlock_state_recorded_is_true(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["unlock_state_recorded"] is True
        assert data["manual_unlock_required"] is True


# ---------------------------------------------------------------------------
# Source hash validation
# ---------------------------------------------------------------------------

class TestSourceHashValidation:
    def test_source_review_result_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_review_result_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_source_review_result_hash_mismatch"

    def test_source_schema_contract_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_schema_contract_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_source_schema_contract_hash_mismatch"

    def test_source_pairing_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_pairing_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_source_pairing_hash_mismatch"

    def test_source_intake_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_response_intake_policy_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_source_response_intake_hash_mismatch"

    def test_source_payload_preview_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_payload_preview_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_execution_unlock_state_source_payload_preview_hash_mismatch"


# ---------------------------------------------------------------------------
# CLI edge cases
# ---------------------------------------------------------------------------

class TestCliEdgeCases:
    def test_create_unlock_state_with_missing_review_result(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state", "missing-id-123", "--json"]):
            assert main() == 1

    def test_show_unlock_state_with_missing_id(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-show", "missing-id-123", "--json"]):
            assert main() == 1

    def test_replay_unlock_state_with_missing_id(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-replay", "missing-id-123", "--json"]):
            assert main() == 1

    def test_validate_unlock_state_strict_exits_nonzero(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_execution_unlocked"] = True
        data["artifact_hash"] = provider_execution_unlock_state_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-validate", result["provider_execution_unlock_state_id"], "--json", "--strict"]):
            assert main() == 2

    def test_replay_unlock_state_strict_exits_nonzero(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["symbol"] = "TAMPERED"
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        with patch("sys.argv", ["atlas", "research", "provider-execution-unlock-state-replay", result["provider_execution_unlock_state_id"], "--json", "--strict"]):
            assert main() == 2


# ---------------------------------------------------------------------------
# Policy content
# ---------------------------------------------------------------------------

class TestPolicyContent:
    def test_unlock_transition_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["unlock_transition_policy"]

        assert policy["automatic_unlock_allowed"] is False
        assert policy["manual_unlock_required"] is True
        assert policy["unlock_requires_separate_future_policy"] is True
        assert policy["unlock_transition_can_create_orders"] is False
        assert policy["unlock_transition_can_call_broker"] is False

    def test_credential_unlock_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["credential_unlock_policy"]

        assert policy["credential_loader_required_in_future"] is True
        assert policy["credential_loader_implemented"] is False
        assert policy["credentials_loaded"] is False
        assert policy["dotenv_loading_allowed"] is False

    def test_provider_adapter_unlock_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["provider_adapter_unlock_policy"]

        assert policy["provider_adapter_required_in_future"] is True
        assert policy["provider_adapter_present"] is False
        assert policy["provider_adapter_enabled"] is False
        assert policy["provider_sdk_import_allowed"] is False

    def test_trust_upgrade_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["trust_upgrade_policy"]

        assert policy["trust_upgrade_required_before_any_future_use"] is True
        assert policy["trust_upgrade_implemented"] is False
        assert policy["trust_upgrade_performed"] is False
        assert policy["manual_review_does_not_imply_trust"] is True
        assert policy["unlock_state_does_not_imply_trust"] is True

    def test_trading_separation_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["trading_separation_policy"]

        assert policy["unlock_state_is_not_trading_signal"] is True
        assert policy["unlock_state_cannot_create_pending_order"] is True
        assert policy["unlock_state_cannot_approve_order"] is True
        assert policy["unlock_state_cannot_submit_order"] is True
        assert policy["unlock_state_cannot_call_broker"] is True

    def test_broker_separation_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["broker_separation_policy"]

        assert policy["broker_live_bridge_allowed"] is False
        assert policy["broker_adapter_access_allowed"] is False
        assert policy["order_routing_allowed"] is False
        assert policy["approval_manager_access_allowed"] is False
        assert policy["risk_manager_access_allowed"] is False

    def test_rollback_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id,
        ) = _full_chain_to_review_result(tmp_path, monkeypatch)

        result = create_provider_execution_unlock_state(tmp_path, review_result_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["rollback_policy"]

        assert policy["unlock_revocation_required_in_future"] is True
        assert policy["unlock_revoked_in_this_batch"] is False
        assert policy["rollback_to_disabled_required"] is True
        assert policy["rollback_can_call_broker"] is False
