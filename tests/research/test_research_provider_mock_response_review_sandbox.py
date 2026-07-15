# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_provider_mock_response_review_sandbox.py
# PURPOSE: Verifies research provider mock response review sandbox behavior and
#         regression expectations.
# DEPS:    json, pathlib, typing, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_mock_response_review_sandbox import (
    PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE,
    _UNSAFE_POSITIVE_CLAIM_PHRASES,
    _has_unsafe_positive_claims,
    build_provider_mock_response_review_sandbox_dict,
    create_provider_mock_response_review_sandbox,
    doctor_provider_mock_response_review_sandbox,
    find_provider_mock_response_review_sandbox_by_id,
    iter_provider_mock_response_review_sandbox_artifacts,
    load_and_validate_provider_mock_response_review_sandbox,
    load_provider_mock_response_review_sandbox,
    provider_mock_response_review_sandbox_sha256,
    replay_provider_mock_response_review_sandbox,
    safe_validate_provider_mock_response_review_sandbox_data,
    summarize_provider_mock_response_review_sandbox,
    validate_provider_mock_response_review_sandbox_artifact,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    build_dossier,
    build_research_timeline,
    check_research_artifacts,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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
    from atlas_agent.research.provider_response_review_result import create_provider_response_review_result

    monkeypatch.chdir(tmp_path)
    result = create_provider_response_review_result(
        workspace_path=tmp_path,
        schema_contract_id=schema_contract_id,
    )
    return result["provider_response_review_result_id"]


def _create_provider_execution_unlock_state(tmp_path: Path, monkeypatch, review_result_id: str) -> str:
    from atlas_agent.research.provider_execution_unlock_state import create_provider_execution_unlock_state

    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_unlock_state(
        workspace_path=tmp_path,
        review_result_id=review_result_id,
    )
    return result["provider_execution_unlock_state_id"]


def _create_provider_adapter_interface_contract(tmp_path: Path, monkeypatch, unlock_state_id: str) -> str:
    from atlas_agent.research.provider_adapter_interface_contract import create_provider_adapter_interface_contract

    monkeypatch.chdir(tmp_path)
    result = create_provider_adapter_interface_contract(
        workspace_path=tmp_path,
        unlock_state_id=unlock_state_id,
    )
    return result["provider_adapter_interface_contract_id"]


def _create_provider_mock_response_simulation(tmp_path: Path, monkeypatch, adapter_interface_contract_id: str) -> str:
    from atlas_agent.research.provider_mock_response_simulation import create_provider_mock_response_simulation

    monkeypatch.chdir(tmp_path)
    result = create_provider_mock_response_simulation(
        workspace_path=tmp_path,
        adapter_interface_contract_id=adapter_interface_contract_id,
    )
    return result["provider_mock_response_simulation_id"]


def _create_provider_mock_response_import_candidate(tmp_path: Path, monkeypatch, simulation_id: str) -> str:
    from atlas_agent.research.provider_mock_response_import_candidate import create_provider_mock_response_import_candidate

    monkeypatch.chdir(tmp_path)
    result = create_provider_mock_response_import_candidate(
        workspace_path=tmp_path,
        simulation_id=simulation_id,
    )
    return result["provider_mock_response_import_candidate_id"]


def _full_chain_to_review_sandbox(tmp_path: Path, monkeypatch) -> tuple[str, str, str, str]:
    monkeypatch.chdir(tmp_path)
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
    unlock_state_id = _create_provider_execution_unlock_state(tmp_path, monkeypatch, review_result_id)
    adapter_contract_id = _create_provider_adapter_interface_contract(tmp_path, monkeypatch, unlock_state_id)
    simulation_id = _create_provider_mock_response_simulation(tmp_path, monkeypatch, adapter_contract_id)
    import_candidate_id = _create_provider_mock_response_import_candidate(tmp_path, monkeypatch, simulation_id)
    return run_id, adapter_contract_id, simulation_id, import_candidate_id


# ---------------------------------------------------------------------------
# Configless safety
# ---------------------------------------------------------------------------

class TestConfiglessSafety:
    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_create_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox", import_candidate_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_list_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-list", "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_show_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-show", result["provider_mock_response_review_sandbox_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_validate_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-validate", result["provider_mock_response_review_sandbox_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_replay_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-replay", result["provider_mock_response_review_sandbox_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_summary_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-summary", run_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_doctor_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-doctor", run_id, "--json"]):
            assert main() == 0


# ---------------------------------------------------------------------------
# Artifact creation
# ---------------------------------------------------------------------------

class TestArtifactCreation:
    def test_create_artifact(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        assert result["ok"] is True
        assert result["mock_review_sandbox_recorded"] is True
        assert result["mock_review_source_verified"] is True
        assert result["mock_review_checks_completed"] is True
        assert result["mock_review_passed"] is True
        assert result["mock_review_requires_manual_followup"] is True
        assert result["mock_only"] is True
        assert result["sandbox_review_only"] is True
        assert result["provider_id"] == "mock"
        assert result["real_provider_response_reviewed"] is False
        assert result["real_provider_response_imported"] is False
        assert result["real_provider_response_received"] is False
        assert result["provider_response_received"] is False
        assert result["provider_response_imported"] is False
        assert result["provider_response_reviewed"] is False
        assert result["provider_response_trusted"] is False
        assert result["mock_response_trusted"] is False
        assert result["review_result_present"] is False
        assert result["manual_review_gate_open"] is False
        assert result["manual_review_completed"] is False
        assert result["provider_call_allowed"] is False
        assert result["broker_touched"] is False
        assert result["artifact_path"].endswith(".json")

        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "provider_mock_response_review_sandbox"
        assert data["contract_version"] == PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert data["source_provider_mock_response_import_candidate_id"] == import_candidate_id
        assert data["artifact_hash"] == provider_mock_response_review_sandbox_sha256(data)

    def test_create_artifact_persists_file(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        path = tmp_path / result["artifact_path"]
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["provider_mock_response_review_sandbox_id"] == result["provider_mock_response_review_sandbox_id"]

    def test_create_rejects_non_mock_source_provider(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        # Tamper source import candidate provider_id
        from atlas_agent.research.provider_mock_response_import_candidate import find_provider_mock_response_import_candidate_by_id
        ic_path = find_provider_mock_response_import_candidate_by_id(tmp_path, import_candidate_id)
        ic_data = json.loads(ic_path.read_text(encoding="utf-8"))
        ic_data["provider_id"] = "custom-openai-compatible"
        ic_path.write_text(json.dumps(ic_data, indent=2, sort_keys=True), encoding="utf-8")

        from atlas_agent.research.session import ResearchSessionError
        with pytest.raises(ResearchSessionError):
            create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_validate_valid_artifact(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        path = tmp_path / result["artifact_path"]

        res = validate_provider_mock_response_review_sandbox_artifact(path, tmp_path)
        assert res.valid is True
        assert res.passed_checks > 0
        assert res.failed_checks == 0

    def test_validate_tampered_hash(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        data["artifact_hash"] = "tampered"
        path.write_text(json.dumps(data), encoding="utf-8")

        from atlas_agent.research.session import ResearchSessionError
        with pytest.raises(ResearchSessionError):
            load_provider_mock_response_review_sandbox(path, tmp_path)

        cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path=None, for_replay=True)
        assert cleaned is None
        assert error == "provider_mock_response_review_sandbox_hash_mismatch"

    def test_safe_validate_rejects_unsafe_positive_claim(self, tmp_path):
        valid_id = "aabbccdd11223344556677889900aabb"
        data = {
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "artifact_type": "provider_mock_response_review_sandbox",
            "contract_version": PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION,
            "provider_mock_response_review_sandbox_id": valid_id,
            "source_provider_mock_response_import_candidate_id": valid_id,
            "source_provider_mock_response_simulation_id": valid_id,
            "source_provider_adapter_interface_contract_id": valid_id,
            "source_provider_execution_unlock_state_id": valid_id,
            "source_provider_response_review_result_id": valid_id,
            "source_provider_response_schema_contract_id": valid_id,
            "source_provider_request_response_pairing_id": valid_id,
            "source_provider_response_intake_policy_id": valid_id,
            "source_provider_outbound_payload_preview_id": valid_id,
            "source_provider_credential_boundary_id": valid_id,
            "source_provider_opt_in_policy_id": valid_id,
            "source_provider_preflight_freeze_id": valid_id,
            "source_provider_execution_readiness_report_id": valid_id,
            "source_provider_execution_audit_packet_id": valid_id,
            "source_provider_execution_state_id": valid_id,
            "source_provider_execution_dry_run_id": valid_id,
            "source_provider_call_plan_id": valid_id,
            "source_sandbox_request_id": valid_id,
            "source_prompt_packet_id": valid_id,
            "source_run_id": valid_id,
            "mock_review_sandbox_status": "mock_review_sandbox_recorded",
            "mock_review_sandbox_scope": "offline_mock_response_review_sandbox_only",
            "mock_review_sandbox_state": "mock_review_sandbox_recorded_untrusted",
            "mock_review_sandbox_recorded": True,
            "mock_review_source_verified": True,
            "mock_review_checks_completed": True,
            "mock_review_passed": True,
            "mock_review_requires_manual_followup": True,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "real_provider_response_imported": False,
            "real_provider_response_received": False,
            "provider_response_received": False,
            "provider_response_imported": False,
            "provider_response_reviewed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "review_result_present": False,
            "manual_review_gate_open": False,
            "manual_review_completed": False,
            "review_decision_allows_use": False,
            "review_decision_allows_trust_upgrade": False,
            "review_decision_allows_trading_interpretation": False,
            "review_decision_allows_order_creation": False,
            "review_decision_allows_order_approval": False,
            "review_decision_allows_broker_call": False,
            "future_response_schema_validated": False,
            "raw_response_body_stored": False,
            "raw_request_body_stored": False,
            "raw_prompt_body_stored": False,
            "raw_review_notes_stored": False,
            "provider_sdk_imported": False,
            "http_client_imported": False,
            "network_enabled": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "credential_value_present": False,
            "credential_lookup_attempted": False,
            "env_read_attempted": False,
            "dotenv_loaded": False,
            "provider_execution_unlocked": False,
            "manual_unlock_granted": False,
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "outbound_request_sent": False,
            "trust_upgrade_performed": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "mode": "paper",
            "symbol": "AAPL",
            "provider_id": "mock",
            "model_id": "gpt-4o",
            "created_at": "2024-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/AAPL/provider_mock_response_review_sandboxes/abc.json",
            "mock_review_source_summary": {"note": "real provider response reviewed"},
            "mock_review_check_summary": {},
            "mock_review_boundary_policy": {},
            "mock_review_storage_policy": {},
            "mock_review_trust_policy": {},
            "mock_review_authorization_policy": {},
            "mock_review_trading_separation_policy": {},
            "mock_review_broker_separation_policy": {},
            "real_provider_review_boundary_policy": {},
            "network_boundary_policy": {},
            "credential_boundary_policy": {},
            "side_effect_policy": {},
            "required_prerequisites": [],
            "satisfied_prerequisites": [],
            "missing_prerequisites": [],
            "blocking_reasons": [],
            "warnings": [],
            "metadata": {},
            "denylist_metadata": {},
        }
        data["artifact_hash"] = provider_mock_response_review_sandbox_sha256(data)
        cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path=None, for_replay=True)
        assert cleaned is None
        assert error == "provider_mock_response_review_sandbox_forbidden_review_claim"

    def test_safe_validate_accepts_safe_negative_booleans(self, tmp_path):
        valid_id = "aabbccdd11223344556677889900aabb"
        data = {
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "artifact_type": "provider_mock_response_review_sandbox",
            "contract_version": PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION,
            "provider_mock_response_review_sandbox_id": valid_id,
            "source_provider_mock_response_import_candidate_id": valid_id,
            "source_provider_mock_response_simulation_id": valid_id,
            "source_provider_adapter_interface_contract_id": valid_id,
            "source_provider_execution_unlock_state_id": valid_id,
            "source_provider_response_review_result_id": valid_id,
            "source_provider_response_schema_contract_id": valid_id,
            "source_provider_request_response_pairing_id": valid_id,
            "source_provider_response_intake_policy_id": valid_id,
            "source_provider_outbound_payload_preview_id": valid_id,
            "source_provider_credential_boundary_id": valid_id,
            "source_provider_opt_in_policy_id": valid_id,
            "source_provider_preflight_freeze_id": valid_id,
            "source_provider_execution_readiness_report_id": valid_id,
            "source_provider_execution_audit_packet_id": valid_id,
            "source_provider_execution_state_id": valid_id,
            "source_provider_execution_dry_run_id": valid_id,
            "source_provider_call_plan_id": valid_id,
            "source_sandbox_request_id": valid_id,
            "source_prompt_packet_id": valid_id,
            "source_run_id": valid_id,
            "mock_review_sandbox_status": "mock_review_sandbox_recorded",
            "mock_review_sandbox_scope": "offline_mock_response_review_sandbox_only",
            "mock_review_sandbox_state": "mock_review_sandbox_recorded_untrusted",
            "mock_review_sandbox_recorded": True,
            "mock_review_source_verified": True,
            "mock_review_checks_completed": True,
            "mock_review_passed": True,
            "mock_review_requires_manual_followup": True,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "real_provider_response_imported": False,
            "real_provider_response_received": False,
            "provider_response_received": False,
            "provider_response_imported": False,
            "provider_response_reviewed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "review_result_present": False,
            "manual_review_gate_open": False,
            "manual_review_completed": False,
            "review_decision_allows_use": False,
            "review_decision_allows_trust_upgrade": False,
            "review_decision_allows_trading_interpretation": False,
            "review_decision_allows_order_creation": False,
            "review_decision_allows_order_approval": False,
            "review_decision_allows_broker_call": False,
            "future_response_schema_validated": False,
            "raw_response_body_stored": False,
            "raw_request_body_stored": False,
            "raw_prompt_body_stored": False,
            "raw_review_notes_stored": False,
            "provider_sdk_imported": False,
            "http_client_imported": False,
            "network_enabled": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "credential_value_present": False,
            "credential_lookup_attempted": False,
            "env_read_attempted": False,
            "dotenv_loaded": False,
            "provider_execution_unlocked": False,
            "manual_unlock_granted": False,
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "outbound_request_sent": False,
            "trust_upgrade_performed": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "mode": "paper",
            "symbol": "AAPL",
            "provider_id": "mock",
            "model_id": "gpt-4o",
            "created_at": "2024-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/AAPL/provider_mock_response_review_sandboxes/abc.json",
            "mock_review_source_summary": {"note": "safe mock source"},
            "mock_review_check_summary": {},
            "mock_review_boundary_policy": {},
            "mock_review_storage_policy": {},
            "mock_review_trust_policy": {},
            "mock_review_authorization_policy": {},
            "mock_review_trading_separation_policy": {},
            "mock_review_broker_separation_policy": {},
            "real_provider_review_boundary_policy": {},
            "network_boundary_policy": {},
            "credential_boundary_policy": {},
            "side_effect_policy": {},
            "required_prerequisites": [],
            "satisfied_prerequisites": [],
            "missing_prerequisites": [],
            "blocking_reasons": [],
            "warnings": [],
            "metadata": {},
            "denylist_metadata": {},
        }
        data["artifact_hash"] = provider_mock_response_review_sandbox_sha256(data)
        cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path=None, for_replay=True)
        assert error is None
        assert cleaned is not None


# ---------------------------------------------------------------------------
# Positive-claim detection
# ---------------------------------------------------------------------------

class TestPositiveClaimDetection:
    def test_has_unsafe_positive_claims_detects_phrases(self):
        assert _has_unsafe_positive_claims("real provider response reviewed") is True
        assert _has_unsafe_positive_claims("network call attempted") is True
        assert _has_unsafe_positive_claims("credentials loaded") is True
        assert _has_unsafe_positive_claims("broker touched") is True

    def test_has_unsafe_positive_claims_skips_safe_text(self):
        assert _has_unsafe_positive_claims("safe mock source") is False
        assert _has_unsafe_positive_claims("mock only") is False
        assert _has_unsafe_positive_claims("") is False

    def test_has_unsafe_positive_claims_recursive_dict(self):
        assert _has_unsafe_positive_claims({"a": {"b": "network enabled"}}) is True
        assert _has_unsafe_positive_claims({"a": {"b": "safe"}}) is False

    def test_has_unsafe_positive_claims_recursive_list(self):
        assert _has_unsafe_positive_claims(["safe", "real provider response reviewed"]) is True
        assert _has_unsafe_positive_claims(["safe", "also safe"]) is False


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

class TestReplay:
    def test_replay_matches(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        replay = replay_provider_mock_response_review_sandbox(tmp_path, sandbox_id)
        assert replay["ok"] is True
        assert replay["match"] is True
        assert replay["original_hash"] == replay["replayed_hash"]

    def test_replay_fails_on_tampered(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]
        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        data["model_id"] = "tampered-model"
        data["artifact_hash"] = provider_mock_response_review_sandbox_sha256(data)
        path.write_text(json.dumps(data), encoding="utf-8")

        replay = replay_provider_mock_response_review_sandbox(tmp_path, sandbox_id)
        assert replay["ok"] is True
        assert replay["match"] is False

    def test_replay_not_found(self, tmp_path):
        from atlas_agent.research.session import ResearchSessionError
        with pytest.raises(ResearchSessionError):
            replay_provider_mock_response_review_sandbox(tmp_path, "nonexistent")


# ---------------------------------------------------------------------------
# Summary and Doctor
# ---------------------------------------------------------------------------

class TestSummaryAndDoctor:
    def test_summary_found(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        result = summarize_provider_mock_response_review_sandbox(tmp_path, run_id)
        assert result["ok"] is True
        assert result["mock_review_sandbox_recorded"] is True
        assert result["mock_only"] is True
        assert result["sandbox_review_only"] is True
        assert result["real_provider_response_reviewed"] is False
        assert result["provider_call_allowed"] is False
        assert result["broker_touched"] is False

    def test_summary_missing(self, tmp_path):
        result = summarize_provider_mock_response_review_sandbox(tmp_path, "nonexistent")
        assert result["ok"] is True
        assert result["status"] == "missing_provider_mock_response_review_sandbox"
        assert result["mock_review_sandbox_recorded"] is False

    def test_doctor_found(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        result = doctor_provider_mock_response_review_sandbox(tmp_path, run_id)
        assert result["ok"] is True
        assert result["mock_review_sandbox_recorded"] is True
        assert result["mock_only"] is True
        assert result["sandbox_review_only"] is True
        assert "provider_execution_disabled" in result["blocking_reasons"]
        assert "real_provider_adapter_missing" in result["blocking_reasons"]
        assert "provider_mock_response_review_sandbox" not in result["missing_prerequisites"]

    def test_doctor_missing(self, tmp_path):
        result = doctor_provider_mock_response_review_sandbox(tmp_path, "nonexistent")
        assert result["ok"] is True
        assert result["mock_review_health"] == "mock_review_sandbox_missing"
        assert result["mock_review_sandbox_recorded"] is False
        assert "provider_mock_response_review_sandbox_not_created" in result["blocking_reasons"]


# ---------------------------------------------------------------------------
# Iteration and listing
# ---------------------------------------------------------------------------

class TestIteration:
    def test_iter_artifacts(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        items = iter_provider_mock_response_review_sandbox_artifacts(tmp_path)
        assert len(items) == 1
        assert items[0]["provider_id"] == "mock"
        assert items[0]["mock_only"] is True
        assert items[0]["sandbox_review_only"] is True

    def test_find_by_id(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        path = find_provider_mock_response_review_sandbox_by_id(tmp_path, sandbox_id)
        assert path is not None
        assert path.exists()

    def test_find_by_id_not_found(self, tmp_path):
        path = find_provider_mock_response_review_sandbox_by_id(tmp_path, "nonexistent")
        assert path is None


# ---------------------------------------------------------------------------
# Timeline / check / dossier integration
# ---------------------------------------------------------------------------

class TestSessionIntegration:
    def test_check_artifacts_counts_review_sandboxes(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        result = check_research_artifacts(tmp_path)
        assert result["counts"]["provider_mock_response_review_sandboxes"] == 1

    def test_timeline_includes_review_sandboxes(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        timeline = build_research_timeline(tmp_path, run_id_filter=run_id)
        assert len(timeline["entries"]) == 1
        entry = timeline["entries"][0]
        assert "prompts" in entry

    def test_dossier_includes_review_sandboxes(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        dossier = build_dossier(tmp_path, run_id)
        assert dossier["artifact_counts"]["provider_mock_response_review_sandboxes"] == 1
        assert dossier["workflow_status"]["provider_mock_response_review_sandboxes"] is True
        types = [a["type"] for a in dossier["linked_artifacts"]]
        assert "provider_mock_response_review_sandbox" in types


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

class TestCliCommands:
    def test_cli_create(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox", import_candidate_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "Provider mock response review sandbox created" in captured.out

    def test_cli_list(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-list"]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "mock" in captured.out

    def test_cli_show(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-show", sandbox_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "Provider mock response review sandbox:" in captured.out

    def test_cli_validate_pass(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-validate", sandbox_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_cli_replay(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-replay", sandbox_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "replay:" in captured.out.lower() or "True" in captured.out

    def test_cli_summary(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-summary", run_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "summary" in captured.out.lower()

    def test_cli_doctor(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox-doctor", run_id]):
            assert main() == 0
        captured = capsys.readouterr()
        assert "doctor" in captured.out.lower()


# ---------------------------------------------------------------------------
# Boolean safety flags
# ---------------------------------------------------------------------------

class TestBooleanSafetyFlags:
    def test_all_flags_must_be_false_listed(self):
        assert "real_provider_response_reviewed" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE
        assert "network_call_attempted" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE
        assert "credentials_loaded" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE
        assert "broker_touched" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE
        assert "provider_call_allowed" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE

    def test_all_flags_must_be_true_listed(self):
        assert "mock_review_sandbox_recorded" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE
        assert "mock_review_source_verified" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE
        assert "mock_review_checks_completed" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE
        assert "mock_review_passed" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE
        assert "mock_only" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE
        assert "sandbox_review_only" in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE

    def test_build_dict_sets_flags_correctly(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))

        for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
            assert data.get(flag) is False, f"Flag {flag} should be False"
        for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
            assert data.get(flag) is True, f"Flag {flag} should be True"


# ---------------------------------------------------------------------------
# Provider ID regression tests
# ---------------------------------------------------------------------------

class TestProviderIdRegression:
    def test_happy_path_artifact_provider_id_is_mock(self, tmp_path, monkeypatch, capsys):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        with patch("sys.argv", ["atlas", "research", "provider-mock-response-review-sandbox", import_candidate_id, "--json"]):
            assert main() == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert out.get("provider_id") == "mock"

        sandbox_id = out["provider_mock_response_review_sandbox_id"]
        path = tmp_path / ".atlas" / "research" / "AAPL" / "provider_mock_response_review_sandboxes" / f"{sandbox_id}.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        assert artifact["provider_id"] == "mock"

    def test_reject_non_mock_provider_id_with_recomputed_hash(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]
        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))

        data["provider_id"] = "custom-openai-compatible"
        data["artifact_hash"] = provider_mock_response_review_sandbox_sha256(data)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

        cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path=tmp_path, for_replay=True)
        assert cleaned is None
        assert error == "invalid_provider_mock_response_review_sandbox_provider"

        from atlas_agent.research.session import check_research_artifacts
        check_result = check_research_artifacts(tmp_path)
        issue_codes = [i["code"] for i in check_result.get("issues", [])]
        assert "invalid_provider_mock_response_review_sandbox_provider" in issue_codes

    def test_replay_preserves_mock_provider(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]

        replay = replay_provider_mock_response_review_sandbox(tmp_path, sandbox_id)
        assert replay["ok"] is True
        assert replay["match"] is True

    def test_list_and_timeline_safe_with_invalid_non_mock_provider(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, adapter_contract_id, simulation_id, import_candidate_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_review_sandbox(tmp_path, import_candidate_id)
        sandbox_id = result["provider_mock_response_review_sandbox_id"]
        path = tmp_path / result["artifact_path"]
        data = json.loads(path.read_text(encoding="utf-8"))

        data["provider_id"] = "custom-openai-compatible"
        data["artifact_hash"] = provider_mock_response_review_sandbox_sha256(data)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

        items = iter_provider_mock_response_review_sandbox_artifacts(tmp_path)
        valid = [i for i in items if not i.get("_invalid")]
        invalid = [i for i in items if i.get("_invalid")]
        assert len(valid) == 0
        assert len(invalid) == 1
        assert invalid[0].get("provider_id") == "unknown"

        timeline = build_research_timeline(tmp_path, run_id_filter=run_id)
        assert len(timeline["entries"]) == 1
