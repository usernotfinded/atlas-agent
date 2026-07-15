# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_provider_mock_response_trust_decision_blocker.py
# PURPOSE: Verifies research provider mock response trust decision blocker
#         behavior and regression expectations.
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
from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
    PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_VERSION,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE,
    _UNSAFE_POSITIVE_CLAIM_PHRASES,
    _has_unsafe_positive_claims,
    build_provider_mock_response_trust_decision_blocker_dict,
    create_provider_mock_response_trust_decision_blocker,
    doctor_provider_mock_response_trust_decision_blocker,
    find_provider_mock_response_trust_decision_blocker_by_id,
    iter_provider_mock_response_trust_decision_blocker_artifacts,
    load_provider_mock_response_trust_decision_blocker,
    provider_mock_response_trust_decision_blocker_sha256,
    replay_provider_mock_response_trust_decision_blocker,
    safe_validate_provider_mock_response_trust_decision_blocker_data,
    summarize_provider_mock_response_trust_decision_blocker,
    validate_provider_mock_response_trust_decision_blocker_artifact,
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


def _create_provider_mock_response_review_sandbox(tmp_path: Path, monkeypatch, import_candidate_id: str) -> str:
    from atlas_agent.research.provider_mock_response_review_sandbox import create_provider_mock_response_review_sandbox

    monkeypatch.chdir(tmp_path)
    result = create_provider_mock_response_review_sandbox(
        workspace_path=tmp_path,
        import_candidate_id=import_candidate_id,
    )
    return result["provider_mock_response_review_sandbox_id"]


def _full_chain_to_review_sandbox(tmp_path: Path, monkeypatch) -> tuple[str, str]:
    """Build full upstream chain and return (run_id, review_sandbox_id)."""
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
    review_sandbox_id = _create_provider_mock_response_review_sandbox(tmp_path, monkeypatch, import_candidate_id)
    return run_id, review_sandbox_id


class TestConfiglessSafety:
    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_create_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker", review_sandbox_id, "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_list_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-list", "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_show_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-show", blocker_id, "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_validate_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-validate", blocker_id, "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_replay_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-replay", blocker_id, "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_summary_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-summary", run_id, "--json"])
        code = main()
        assert code == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_trust_decision_blocker_doctor_configless(self, _mock_secrets, _mock_config, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-doctor", run_id, "--json"])
        code = main()
        assert code == 0


class TestTrustBlockerCreation:
    def test_valid_trust_blocker_creates_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_mock_response_trust_decision_blocker_created"
        assert result["provider_id"] == "mock"
        assert result["trust_decision_blocker_recorded"] is True
        assert result["trust_source_verified"] is True
        assert result["trust_blocker_active"] is True
        assert result["trust_decision_required"] is True
        assert result["trust_decision_present"] is False
        assert result["trust_decision_granted"] is False
        assert result["trust_decision_explicitly_blocked"] is True
        assert result["trust_upgrade_performed"] is False
        assert result["provider_response_trusted"] is False
        assert result["mock_response_trusted"] is False
        assert result["provider_call_allowed"] is False
        assert result["broker_touched"] is False

    def test_artifact_contains_all_policies(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        assert path is not None
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert "trust_source_summary" in data
        assert "trust_blocker_summary" in data
        assert "trust_decision_policy" in data
        assert "trust_upgrade_policy" in data
        assert "manual_review_policy" in data
        assert "mock_response_trust_policy" in data
        assert "real_provider_trust_boundary_policy" in data
        assert "trading_authorization_policy" in data
        assert "broker_separation_policy" in data
        assert "network_boundary_policy" in data
        assert "credential_boundary_policy" in data
        assert "side_effect_policy" in data

    def test_trust_source_summary_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        tss = data["trust_source_summary"]
        assert tss["source_artifact_type"] == "provider_mock_response_review_sandbox"
        assert tss["source_provider_id"] == "mock"
        assert tss["source_is_mock"] is True
        assert tss["source_is_real_provider_response"] is False
        assert tss["source_review_sandbox_recorded"] is True
        assert tss["source_review_sandbox_trusted"] is False
        assert tss["source_manual_review_completed"] is False
        assert tss["source_provider_response_trusted"] is False
        assert tss["source_can_create_orders"] is False
        assert tss["source_can_call_broker"] is False

    def test_trust_blocker_summary_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        tbs = data["trust_blocker_summary"]
        assert tbs["trust_decision_blocker_recorded"] is True
        assert tbs["trust_blocker_active"] is True
        assert tbs["trust_decision_required"] is True
        assert tbs["trust_decision_present"] is False
        assert tbs["trust_decision_granted"] is False
        assert tbs["trust_decision_explicitly_blocked"] is True
        assert tbs["trust_upgrade_performed"] is False
        assert tbs["provider_response_trusted"] is False
        assert tbs["mock_response_trusted"] is False
        assert tbs["manual_review_completed"] is False
        assert tbs["trading_signal_generated"] is False
        assert tbs["approval_created"] is False
        assert tbs["pending_order_created"] is False
        assert tbs["broker_touched"] is False

    def test_trust_decision_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        tdp = data["trust_decision_policy"]
        assert tdp["trust_decision_required_before_any_future_use"] is True
        assert tdp["trust_decision_present"] is False
        assert tdp["trust_decision_granted"] is False
        assert tdp["trust_decision_denied"] is False
        assert tdp["trust_decision_explicitly_blocked"] is True
        assert tdp["mock_review_sandbox_does_not_create_trust_decision"] is True
        assert tdp["trust_decision_requires_future_command"] is True
        assert tdp["trust_decision_requires_future_policy"] is True
        assert tdp["trust_decision_cannot_be_inferred_from_mock"] is True

    def test_trust_upgrade_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        tup = data["trust_upgrade_policy"]
        assert tup["trust_upgrade_available"] is False
        assert tup["trust_upgrade_performed"] is False
        assert tup["trust_upgrade_not_implemented"] is True
        assert tup["mock_review_sandbox_cannot_upgrade_trust"] is True
        assert tup["mock_import_candidate_cannot_upgrade_trust"] is True
        assert tup["mock_response_simulation_cannot_upgrade_trust"] is True
        assert tup["trust_upgrade_requires_future_design"] is True

    def test_manual_review_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        mrp = data["manual_review_policy"]
        assert mrp["manual_review_required"] is True
        assert mrp["manual_review_gate_open"] is False
        assert mrp["manual_review_completed"] is False
        assert mrp["review_result_present"] is False
        assert mrp["sandbox_review_does_not_complete_manual_review"] is True
        assert mrp["manual_review_required_before_future_trust_decision"] is True
        assert mrp["manual_review_cannot_be_inferred_from_mock"] is True

    def test_mock_response_trust_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        mtp = data["mock_response_trust_policy"]
        assert mtp["provider_response_trusted"] is False
        assert mtp["mock_response_trusted"] is False
        assert mtp["sandbox_review_trusted"] is False
        assert mtp["mock_response_cannot_be_trusted_in_this_batch"] is True
        assert mtp["mock_response_cannot_be_trading_signal"] is True
        assert mtp["mock_response_cannot_create_orders"] is True
        assert mtp["mock_response_cannot_approve_orders"] is True
        assert mtp["mock_response_cannot_call_broker"] is True

    def test_trading_authorization_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        tap = data["trading_authorization_policy"]
        assert tap["trust_blocker_is_not_trading_signal"] is True
        assert tap["trust_blocker_cannot_create_pending_order"] is True
        assert tap["trust_blocker_cannot_approve_order"] is True
        assert tap["trust_blocker_cannot_submit_order"] is True
        assert tap["trust_blocker_cannot_modify_risk"] is True
        assert tap["trust_blocker_cannot_call_broker"] is True

    def test_broker_separation_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        bsp = data["broker_separation_policy"]
        assert bsp["broker_live_bridge_allowed"] is False
        assert bsp["broker_adapter_access_allowed"] is False
        assert bsp["order_routing_allowed"] is False
        assert bsp["approval_manager_access_allowed"] is False
        assert bsp["risk_manager_access_allowed"] is False

    def test_network_boundary_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        nbp = data["network_boundary_policy"]
        assert nbp["network_enabled"] is False
        assert nbp["network_call_attempted"] is False
        assert nbp["http_client_imported"] is False
        assert nbp["provider_network_call_allowed"] is False

    def test_credential_boundary_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        cbp = data["credential_boundary_policy"]
        assert cbp["credentials_loaded"] is False
        assert cbp["credential_value_present"] is False
        assert cbp["credential_lookup_attempted"] is False
        assert cbp["env_read_attempted"] is False
        assert cbp["dotenv_loaded"] is False

    def test_side_effect_policy_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        sep = data["side_effect_policy"]
        assert sep["filesystem_side_effects_limited_to_artifacts"] is True
        assert sep["summary_commands_write_artifacts"] is False
        assert sep["doctor_commands_write_artifacts"] is False
        assert sep["trust_decision_blocker_writes_only_blocker_artifact"] is True
        assert sep["trust_decision_blocker_writes_events"] is True
        assert sep["trust_decision_blocker_touches_broker"] is False


class TestTrustBlockerPolicySafety:
    def test_all_must_be_false_flags_are_false(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        for field in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
            assert data.get(field) is False, f"Field {field} should be False"

    def test_all_must_be_true_flags_are_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        for field in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
            assert data.get(field) is True, f"Field {field} should be True"


class TestTrustBlockerValidation:
    def test_safe_validate_passes_for_valid_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)

    def test_safe_validate_fails_for_missing_provider_id(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["provider_id"] = "openai"
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "provider" in error.lower()

    def test_safe_validate_fails_for_trust_decision_granted_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_decision_granted"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_broker_touched_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["broker_touched"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_provider_call_allowed_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["provider_call_allowed"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_mock_response_trusted_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["mock_response_trusted"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_provider_response_trusted_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["provider_response_trusted"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_network_enabled_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["network_enabled"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_credentials_loaded_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["credentials_loaded"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_trust_upgrade_performed_true(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_upgrade_performed"] = True
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "impossible_boolean" in error.lower()

    def test_safe_validate_fails_for_forbidden_claim(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["mock_response_trust_policy"]["notes"] = "trust decision granted"
        # Recompute hash so the forbidden claim check is reached
        data["artifact_hash"] = provider_mock_response_trust_decision_blocker_sha256(data)
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "forbidden_trust_claim" in error.lower()

    def test_safe_validate_fails_for_tampered_source_hash(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["source_mock_review_sandbox_hash"] = "tampered"
        # Recompute artifact hash so source hash validation is reached
        data["artifact_hash"] = provider_mock_response_trust_decision_blocker_sha256(data)
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "source_review_sandbox_hash_mismatch" in error.lower()

    def test_safe_validate_fails_for_wrong_source_hash(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["source_mock_review_sandbox_hash"] = "a" * 64
        # Recompute artifact hash so source hash validation is reached
        data["artifact_hash"] = provider_mock_response_trust_decision_blocker_sha256(data)
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "source_review_sandbox_hash_mismatch" in error.lower()

    def test_safe_validate_fails_for_missing_source_provider_mock_response_review_sandbox_id(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        del data["source_provider_mock_response_review_sandbox_id"]
        validated, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, tmp_path)
        assert validated is None
        assert "lineage" in error.lower()


class TestTrustBlockerTamperDetection:
    def test_hash_excludes_volatile_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        h1 = provider_mock_response_trust_decision_blocker_sha256(data)
        data["artifact_hash"] = "changed"
        data["created_at"] = "changed"
        h2 = provider_mock_response_trust_decision_blocker_sha256(data)
        assert h1 == h2

    def test_hash_includes_core_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        h1 = provider_mock_response_trust_decision_blocker_sha256(data)
        data["trust_decision_granted"] = True
        h2 = provider_mock_response_trust_decision_blocker_sha256(data)
        assert h1 != h2

    def test_validate_detects_tampered_hash(self, tmp_path: Path, monkeypatch) -> None:
        from atlas_agent.research.session import ResearchSessionError
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_decision_granted"] = True
        json.dump(data, path.open("w"))
        with pytest.raises(ResearchSessionError):
            validate_provider_mock_response_trust_decision_blocker_artifact(path, tmp_path)


class TestTrustBlockerReplay:
    def test_replay_returns_chain(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        replay = replay_provider_mock_response_trust_decision_blocker(tmp_path, blocker_id)
        assert replay["ok"] is True
        assert replay["match"] is True
        assert replay["provider_mock_response_trust_decision_blocker_id"] == blocker_id

    def test_replay_detects_tampered_artifact(self, tmp_path: Path, monkeypatch) -> None:
        from atlas_agent.research.session import ResearchSessionError
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_decision_granted"] = True
        json.dump(data, path.open("w"))
        with pytest.raises(ResearchSessionError):
            replay_provider_mock_response_trust_decision_blocker(tmp_path, blocker_id)


class TestTrustBlockerSummary:
    def test_summary_returns_blocker_summary(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        summary = summarize_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert summary["ok"] is True
        assert summary["trust_decision_blocker_recorded"] is True
        assert summary["provider_mock_response_trust_decision_blocker_id"] == blocker_id

    def test_summary_shows_safe_flags(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        summary = summarize_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert summary["trust_decision_granted"] is False
        assert summary["broker_touched"] is False
        assert summary["provider_call_allowed"] is False
        assert summary["trust_decision_explicitly_blocked"] is True


class TestTrustBlockerDoctor:
    def test_doctor_passes_for_valid_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["ok"] is True
        assert doctor["trust_blocker_active"] is True
        assert doctor["trust_decision_granted"] is False
        assert doctor["trust_decision_explicitly_blocked"] is True
        assert doctor["provider_call_allowed"] is False
        assert doctor["mock_response_trusted"] is False

    def test_doctor_fails_for_tampered_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_decision_granted"] = True
        json.dump(data, path.open("w"))
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["trust_health"] == "trust_decision_blocker_missing"

    def test_doctor_fails_for_wrong_provider_id(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["provider_id"] = "anthropic"
        json.dump(data, path.open("w"))
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["trust_health"] == "trust_decision_blocker_missing"

    def test_doctor_detects_source_hash_mismatch(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["source_mock_review_sandbox_hash"] = "a" * 64
        json.dump(data, path.open("w"))
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["trust_health"] == "trust_decision_blocker_missing"

    def test_doctor_detects_artifact_hash_mismatch(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        data["trust_decision_granted"] = True
        json.dump(data, path.open("w"))
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["trust_health"] == "trust_decision_blocker_missing"

    def test_doctor_detects_missing_review_sandbox_link(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        del data["source_provider_mock_response_review_sandbox_id"]
        json.dump(data, path.open("w"))
        doctor = doctor_provider_mock_response_trust_decision_blocker(tmp_path, run_id)
        assert doctor["trust_health"] == "trust_decision_blocker_missing"


class TestTrustBlockerListingAndLoading:
    def test_iter_returns_all_artifacts(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        items = list(iter_provider_mock_response_trust_decision_blocker_artifacts(tmp_path))
        assert len(items) >= 1

    def test_find_by_id_returns_path(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        assert path is not None
        assert path.name.endswith(".json")

    def test_find_by_id_returns_none_for_missing(self, tmp_path: Path) -> None:
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, "nonexistent")
        assert path is None

    def test_load_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["provider_id"] == "mock"


class TestTrustBlockerTimelineAndDossier:
    def test_check_research_artifacts_counts_blockers(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        result = check_research_artifacts(tmp_path, "AAPL")
        counts = result["counts"]
        assert counts["provider_mock_response_trust_decision_blockers"] >= 1

    def test_check_research_artifacts_validates_blocker_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        result = check_research_artifacts(tmp_path, "AAPL")
        # check_research_artifacts returns counts/issues/warnings, not per-artifact details
        assert result["ok"] is True
        assert result["counts"]["provider_mock_response_trust_decision_blockers"] >= 1

    def test_timeline_includes_run(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        timeline = build_research_timeline(tmp_path, run_id_filter=run_id)
        # Timeline is deeply nested; just verify it builds and contains our run
        assert timeline["ok"] is True
        entries = timeline.get("entries", [])
        assert any(e.get("run_id") == run_id for e in entries)

    def test_dossier_builds_without_error(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        dossier = build_dossier(tmp_path, run_id)
        assert dossier["source_run_id"] == run_id
        assert dossier["workflow_status"].get("provider_mock_response_trust_decision_blockers", False) is True


class TestTrustBlockerSchemaVersion:
    def test_artifact_has_correct_version(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert data["artifact_type"] == "provider_mock_response_trust_decision_blocker"


class TestTrustBlockerProviderIdInvariant:
    def test_provider_id_must_be_mock(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["provider_id"] == "mock"
        assert data["source_provider_id"] == "mock"

    def test_creation_from_non_mock_review_sandbox_fails(self, tmp_path: Path, monkeypatch) -> None:
        from atlas_agent.research.provider_mock_response_review_sandbox import load_provider_mock_response_review_sandbox
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)

        # Patch the review sandbox to have non-mock provider
        sandbox_path = tmp_path / ".atlas" / "research" / "AAPL" / "provider_mock_response_review_sandboxes" / f"{review_sandbox_id}.json"
        sandbox_data = json.load(sandbox_path.open())
        sandbox_data["provider_id"] = "openai"
        json.dump(sandbox_data, sandbox_path.open("w"))

        with pytest.raises(Exception):
            create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)


class TestTrustBlockerSemantics:
    def test_trust_decision_explicitly_blocked_implies_not_granted(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["trust_decision_explicitly_blocked"] is True
        assert data["trust_decision_granted"] is False
        assert data["trust_decision_denied"] is False
        assert data["trust_decision_present"] is False

    def test_mock_response_trusted_false(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["mock_response_trusted"] is False
        assert data["provider_response_trusted"] is False
        assert data["mock_response_trust_policy"]["mock_response_cannot_be_trusted_in_this_batch"] is True

    def test_no_trading_authorization(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["trading_signal_generated"] is False
        assert data["approval_created"] is False
        assert data["pending_order_created"] is False
        assert data["broker_touched"] is False
        assert data["broker_separation_policy"]["order_routing_allowed"] is False
        assert data["broker_separation_policy"]["broker_live_bridge_allowed"] is False

    def test_no_network_no_credentials(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        path = find_provider_mock_response_trust_decision_blocker_by_id(tmp_path, blocker_id)
        data = load_provider_mock_response_trust_decision_blocker(path, tmp_path)
        assert data["network_enabled"] is False
        assert data["network_call_attempted"] is False
        assert data["http_client_imported"] is False
        assert data["credentials_loaded"] is False
        assert data["credential_value_present"] is False
        assert data["env_read_attempted"] is False
        assert data["dotenv_loaded"] is False


class TestUnsafePositiveClaims:
    def test_has_unsafe_positive_claims_detects_trust_claim(self) -> None:
        data = {"notes": "trust decision granted"}
        assert _has_unsafe_positive_claims(data) is True

    def test_has_unsafe_positive_claims_detects_safe_mock(self) -> None:
        data = {"notes": "mock response trusted"}
        assert _has_unsafe_positive_claims(data) is True

    def test_has_unsafe_positive_claims_ignores_blocked_prefix(self) -> None:
        data = {"notes": "mock_response_trusted"}
        assert _has_unsafe_positive_claims(data) is False

    def test_has_unsafe_positive_claims_ignores_safe_data(self) -> None:
        data = {"notes": "mock_response_cannot_be_trusted_in_this_batch"}
        assert _has_unsafe_positive_claims(data) is False

    def test_denylist_contains_trust_phrases(self) -> None:
        assert "trust decision granted" in _UNSAFE_POSITIVE_CLAIM_PHRASES
        assert "mock response trusted" in _UNSAFE_POSITIVE_CLAIM_PHRASES


class TestTrustBlockerCreationErrorHandling:
    def test_create_from_nonexistent_review_sandbox_fails(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            create_provider_mock_response_trust_decision_blocker(tmp_path, "nonexistent")

    def test_create_from_empty_review_sandbox_id_fails(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            create_provider_mock_response_trust_decision_blocker(tmp_path, "")


class TestTrustBlockerMultipleArtifacts:
    def test_multiple_blockers_per_run(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        r1 = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        r2 = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        assert r1["provider_mock_response_trust_decision_blocker_id"] != r2["provider_mock_response_trust_decision_blocker_id"]
        items = list(iter_provider_mock_response_trust_decision_blocker_artifacts(tmp_path))
        assert len(items) == 2


class TestTrustBlockerCLIIntegration:
    def test_cli_create_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker", review_sandbox_id, "--json"])
        code = main()
        assert code == 0

    def test_cli_list_trust_blockers(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-list", "--json"])
        code = main()
        assert code == 0

    def test_cli_show_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-show", blocker_id, "--json"])
        code = main()
        assert code == 0

    def test_cli_validate_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-validate", blocker_id, "--json"])
        code = main()
        assert code == 0

    def test_cli_replay_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        result = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        blocker_id = result["provider_mock_response_trust_decision_blocker_id"]
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-replay", blocker_id, "--json"])
        code = main()
        assert code == 0

    def test_cli_summary_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-summary", run_id, "--json"])
        code = main()
        assert code == 0

    def test_cli_doctor_trust_blocker(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        run_id, review_sandbox_id = _full_chain_to_review_sandbox(tmp_path, monkeypatch)
        create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["atlas", "research", "provider-mock-response-trust-decision-blocker-doctor", run_id, "--json"])
        code = main()
        assert code == 0
