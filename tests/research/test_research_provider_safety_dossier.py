"""Tests for provider safety dossier."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from atlas_agent.research.provider_mock_response_trust_decision_blocker import create_provider_mock_response_trust_decision_blocker
from atlas_agent.research.provider_mock_response_final_safety_seal import create_provider_mock_response_final_safety_seal
from atlas_agent.research.provider_safety_dossier import (
    ProviderSafetyDossierValidationResult,
    _has_unsafe_positive_claims,
    _SAFE_STATUS_INCOMPLETE,
    _SAFE_STATUS_INVALID,
    _SAFE_STATUS_TAMPER,
    _SAFE_STATUS_VALID,
    build_provider_safety_dossier_dict,
    create_provider_safety_dossier,
    doctor_provider_safety_dossier,
    export_provider_safety_dossier_markdown,
    find_provider_safety_dossier_by_id,
    iter_provider_safety_dossier_artifacts,
    latest_provider_safety_dossier,
    load_provider_safety_dossier,
    provider_safety_dossier_sha256,
    replay_provider_safety_dossier,
    safe_validate_provider_safety_dossier_data,
    summarize_provider_safety_dossier,
    validate_provider_id,
    validate_provider_safety_dossier_artifact,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION, ResearchSessionError

# ---------------------------------------------------------------------------
# Chain builder helpers (inlined, same pattern as final_safety_seal test)
# ---------------------------------------------------------------------------

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


def _full_chain_to_seal(tmp_path: Path, monkeypatch) -> tuple[str, str]:
    """Build full upstream chain and return (run_id, seal_id)."""
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
    blocker_res = create_provider_mock_response_trust_decision_blocker(tmp_path, review_sandbox_id)
    blocker_id = blocker_res["provider_mock_response_trust_decision_blocker_id"]
    seal_res = create_provider_mock_response_final_safety_seal(tmp_path, blocker_id)
    seal_id = seal_res["provider_mock_response_final_safety_seal_id"]
    return run_id, seal_id


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_has_unsafe_positive_claims():
    assert _has_unsafe_positive_claims("trust decision granted")
    assert _has_unsafe_positive_claims("we have trust upgrade available")
    assert _has_unsafe_positive_claims({"key": "seal authorizes"})
    assert _has_unsafe_positive_claims(["safe", "live trading authorized"])
    assert not _has_unsafe_positive_claims("everything is safe")
    assert not _has_unsafe_positive_claims({"key": "safe"})

def test_validate_provider_id():
    assert validate_provider_id("mock") == "mock"
    with pytest.raises(ResearchSessionError):
        validate_provider_id("openai")

def test_build_provider_safety_dossier_dict_missing_seal(tmp_path):
    with pytest.raises(ResearchSessionError, match="provider_safety_dossier_source_seal_missing"):
        build_provider_safety_dossier_dict(tmp_path, "seal_123", "dossier_123")


class TestSafetyDossierCreation:
    def test_create_and_load(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path

        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)

        res = create_provider_safety_dossier(ws, seal_id)
        assert res["ok"] is True
        dossier_id = res["provider_safety_dossier_id"]
        assert len(dossier_id) > 10

        path = find_provider_safety_dossier_by_id(ws, dossier_id)
        assert path is not None
        assert path.exists()

        data = load_provider_safety_dossier(path, ws)
        assert data["artifact_type"] == "provider_safety_dossier"
        assert data["provider_safety_dossier_id"] == dossier_id
        assert data["chain_complete"] is True
        assert data["safety_verdict"] == "sandbox_chain_complete"

        val_res = validate_provider_safety_dossier_artifact(path, ws)
        assert val_res.valid

def test_tamper_rejection(tmp_path):
    ws = tmp_path
    dossier_id = "dossier_123"
    dossier_dir = ws / ".atlas" / "research" / "DEMO-SYMBOL" / "provider_safety_dossiers"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / f"{dossier_id}.json"

    data = {
        "artifact_type": "provider_safety_dossier",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": "research_provider_safety_dossier_v1",
        "provider_safety_dossier_id": dossier_id,
        "symbol": "DEMO-SYMBOL",
        "provider_id": "mock",
        "sandbox_only": True,
        "chain_complete": False,
        "provider_call_allowed": True,  # TAMPER!
        "actual_provider_call_made": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "trust_upgrade_performed": False,
        "trust_decision_granted": False,
        "provider_execution_unlocked": False,
        "real_provider_response_imported": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "artifact_hash": "",
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_path": str(dossier_path.relative_to(ws)),
    }
    data["artifact_hash"] = provider_safety_dossier_sha256(data)
    dossier_path.write_text(json.dumps(data))

    with pytest.raises(ResearchSessionError, match="provider_safety_dossier_impossible_boolean"):
        load_provider_safety_dossier(dossier_path, ws)

def test_tamper_positive_claim(tmp_path):
    ws = tmp_path
    dossier_id = "dossier_123"
    dossier_dir = ws / ".atlas" / "research" / "DEMO-SYMBOL" / "provider_safety_dossiers"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / f"{dossier_id}.json"

    data = {
        "artifact_type": "provider_safety_dossier",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": "research_provider_safety_dossier_v1",
        "provider_safety_dossier_id": dossier_id,
        "symbol": "DEMO-SYMBOL",
        "provider_id": "mock",
        "sandbox_only": True,
        "chain_complete": False,
        "chain_health": "incomplete",
        "safety_verdict": "trust decision granted", # TAMPER positive claim!
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "trust_upgrade_performed": False,
        "trust_decision_granted": False,
        "provider_execution_unlocked": False,
        "real_provider_response_imported": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "artifact_hash": "",
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_path": str(dossier_path.relative_to(ws)),
    }
    data["artifact_hash"] = provider_safety_dossier_sha256(data)
    dossier_path.write_text(json.dumps(data))

    with pytest.raises(ResearchSessionError, match="provider_safety_dossier_forbidden_trust_claim"):
        load_provider_safety_dossier(dossier_path, ws)


# ---------------------------------------------------------------------------
# Markdown export tests
# ---------------------------------------------------------------------------

class TestSafetyDossierMarkdownExport:
    def test_export_happy_path(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "dossier_export.md"
        result = export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert result["ok"] is True
        assert result["format"] == "markdown"
        assert result["output_path_redacted"] is True
        assert "output_path_relative" in result
        assert result["output_path_relative"] == "reports/dossier_export.md"
        assert "output_path" not in result
        assert output_path.exists()

        text = output_path.read_text(encoding="utf-8")
        assert "# Provider Safety Dossier" in text
        assert "## 1. Summary" in text
        assert "## 2. Chain" in text
        assert "## 3. Safety Invariants" in text
        assert "## 4. Trust Status" in text
        assert "## 5. Execution Status" in text
        assert "## 6. Broker/Order Status" in text
        assert "## 7. Validation Result" in text
        assert "## 8. Limitations" in text

    def test_export_output_file_created(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "nested" / "export.md"
        export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_export_forbidden_word_absent(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        text = output_path.read_text(encoding="utf-8").lower()
        forbidden = [
            "production ready",
            "live trading ready",
            "safe to trade",
            "trust granted",
            "provider execution enabled",
            "broker execution enabled",
            "orders enabled",
            "approvals enabled",
        ]
        for phrase in forbidden:
            assert phrase not in text, f"Forbidden phrase found: {phrase}"

    def test_export_forbidden_fragments_absent(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        text = output_path.read_text(encoding="utf-8")
        for frag in [
            "/Users/", "/private/var/", "Authorization", "Bearer", "APCA",
            "SECRET", "TOKEN", "PASSWORD", "API_KEY", "sk-", "broker.example.com",
        ]:
            assert frag not in text, f"Forbidden fragment found: {frag}"

    def test_export_invalid_dossier_fails_closed(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_bad"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        bad_data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "provider_call_allowed": True,  # invalid
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        bad_data["artifact_hash"] = provider_safety_dossier_sha256(bad_data)
        dossier_path.write_text(json.dumps(bad_data))

        output_path = ws / "reports" / "export.md"
        with pytest.raises(ResearchSessionError, match="provider_safety_dossier_impossible_boolean"):
            export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert not output_path.exists()

    def test_export_tampered_dossier_fails_closed(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_tampered"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
                {"artifact_type": "b", "artifact_id": "2"},
                {"artifact_type": "c", "artifact_id": "3"},
                {"artifact_type": "d", "artifact_id": "4"},
                {"artifact_type": "e", "artifact_id": "5"},
                {"artifact_type": "f", "artifact_id": "6"},
            ],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "tampered_hash_12345",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        dossier_path.write_text(json.dumps(data))

        output_path = ws / "reports" / "export.md"
        with pytest.raises(ResearchSessionError, match="provider_safety_dossier_hash_mismatch"):
            export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert not output_path.exists()

    def test_export_positive_unsafe_claim_rejected(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_unsafe"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
                {"artifact_type": "b", "artifact_id": "2"},
                {"artifact_type": "c", "artifact_id": "3"},
                {"artifact_type": "d", "artifact_id": "4"},
                {"artifact_type": "e", "artifact_id": "5"},
                {"artifact_type": "f", "artifact_id": "6"},
            ],
            "safety_verdict": "trust decision granted",  # unsafe claim
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        data["artifact_hash"] = provider_safety_dossier_sha256(data)
        dossier_path.write_text(json.dumps(data))

        output_path = ws / "reports" / "export.md"
        # safe_validate catches the forbidden claim during load
        with pytest.raises(ResearchSessionError, match="provider_safety_dossier_forbidden_trust_claim"):
            export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert not output_path.exists()

    def test_export_chain_incomplete_fails(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_incomplete"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": False,
            "chain_nodes": [],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        data["artifact_hash"] = provider_safety_dossier_sha256(data)
        dossier_path.write_text(json.dumps(data))

        output_path = ws / "reports" / "export.md"
        with pytest.raises(ResearchSessionError, match="provider_safety_dossier_export_chain_incomplete"):
            export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        assert not output_path.exists()

    def test_export_no_raw_invalid_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        text = output_path.read_text(encoding="utf-8")
        # The raw artifact_path should not appear in the markdown
        artifact = load_provider_safety_dossier(find_provider_safety_dossier_by_id(ws, dossier_id), ws)
        raw_path = artifact.get("artifact_path", "")
        assert raw_path not in text

    def test_export_envelope_no_absolute_paths(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        result = export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        result_json = json.dumps(result)
        assert "/private/var/" not in result_json
        assert "/Users/" not in result_json
        assert str(ws) not in result_json

    def test_export_markdown_no_absolute_paths(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        text = output_path.read_text(encoding="utf-8")
        assert "/private/var/" not in text
        assert "/Users/" not in text
        assert str(ws) not in text

    def test_export_envelope_no_forbidden_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        output_path = ws / "reports" / "export.md"
        result = export_provider_safety_dossier_markdown(ws, dossier_id, output_path)
        result_json = json.dumps(result)
        for frag in [
            "Authorization", "Bearer", "APCA", "SECRET", "TOKEN",
            "PASSWORD", "API_KEY", "sk-", "broker.example.com",
        ]:
            assert frag not in result_json, f"Forbidden fragment in envelope: {frag}"

    def test_export_temp_path_redacted(self, tmp_path: Path, monkeypatch) -> None:
        """Ensure that even when output_path is outside workspace (should not happen in CLI),
        the envelope falls back to basename and never leaks absolute paths."""
        ws = tmp_path
        dossier_id = "dossier_temp"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
                {"artifact_type": "b", "artifact_id": "2"},
                {"artifact_type": "c", "artifact_id": "3"},
                {"artifact_type": "d", "artifact_id": "4"},
                {"artifact_type": "e", "artifact_id": "5"},
                {"artifact_type": "f", "artifact_id": "6"},
            ],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        data["artifact_hash"] = provider_safety_dossier_sha256(data)
        dossier_path.write_text(json.dumps(data))

        # Pass an absolute path that is not inside workspace
        external_path = tmp_path.parent / "external_export.md"
        result = export_provider_safety_dossier_markdown(ws, dossier_id, external_path)
        assert result["output_path_redacted"] is True
        assert "/" not in result["output_path_relative"] or result["output_path_relative"] == "external_export.md"
        assert "/private/var/" not in json.dumps(result)


# ---------------------------------------------------------------------------
# Discovery UX tests (Batch 9.7)
# ---------------------------------------------------------------------------

class TestSafetyDossierDiscoveryUX:
    def test_latest_returns_newest_valid_dossier(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        result = latest_provider_safety_dossier(ws)
        assert result["ok"] is True
        assert result["found"] is True
        assert result["artifact_id"] == dossier_id
        assert result["provider_id"] == "mock"
        assert result["sandbox_only"] is True
        assert result["chain_health"] == "complete"
        assert result["safety_verdict"] == "sandbox_chain_complete"
        assert result["export_available"] is True
        assert result["safe_status"] == _SAFE_STATUS_VALID

    def test_latest_no_dossiers_returns_not_found(self, tmp_path: Path) -> None:
        ws = tmp_path
        result = latest_provider_safety_dossier(ws)
        assert result["ok"] is True
        assert result["found"] is False
        assert result["reason"] == "no_provider_safety_dossier_found"

    def test_latest_ignores_invalid_dossier(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_bad"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        bad_data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "provider_call_allowed": True,  # invalid
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        bad_data["artifact_hash"] = provider_safety_dossier_sha256(bad_data)
        dossier_path.write_text(json.dumps(bad_data))

        result = latest_provider_safety_dossier(ws)
        assert result["ok"] is True
        assert result["found"] is False
        assert result["reason"] == "no_provider_safety_dossier_found"

    def test_latest_ignores_tampered_dossier(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_tampered"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
                {"artifact_type": "b", "artifact_id": "2"},
                {"artifact_type": "c", "artifact_id": "3"},
                {"artifact_type": "d", "artifact_id": "4"},
                {"artifact_type": "e", "artifact_id": "5"},
                {"artifact_type": "f", "artifact_id": "6"},
            ],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "tampered_hash_12345",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        dossier_path.write_text(json.dumps(data))

        result = latest_provider_safety_dossier(ws)
        assert result["ok"] is True
        assert result["found"] is False
        assert result["reason"] == "no_provider_safety_dossier_found"

    def test_latest_does_not_copy_raw_invalid_fields(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        res = create_provider_safety_dossier(ws, seal_id)
        dossier_id = res["provider_safety_dossier_id"]

        result = latest_provider_safety_dossier(ws)
        assert result["ok"] is True
        assert result["found"] is True
        # Should not contain raw artifact_path or other raw fields
        assert "artifact_path" not in result
        assert "source_seal_id" not in result
        assert "chain_nodes" not in result

    def test_list_status_filter_sandbox_chain_complete(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id)

        items = iter_provider_safety_dossier_artifacts(ws, status_filter=_SAFE_STATUS_VALID)
        assert len(items) == 1
        assert items[0]["safe_status"] == _SAFE_STATUS_VALID

    def test_list_status_filter_chain_incomplete(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_incomplete"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": False,
            "chain_nodes": [],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        data["artifact_hash"] = provider_safety_dossier_sha256(data)
        dossier_path.write_text(json.dumps(data))

        items = iter_provider_safety_dossier_artifacts(ws, status_filter=_SAFE_STATUS_INCOMPLETE)
        assert len(items) == 1
        assert items[0]["safe_status"] == _SAFE_STATUS_INCOMPLETE

    def test_list_status_filter_chain_invalid(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_invalid"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        # Use chain_complete=True with too few nodes to trigger chain_incomplete validation error
        bad_data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
            ],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        bad_data["artifact_hash"] = provider_safety_dossier_sha256(bad_data)
        dossier_path.write_text(json.dumps(bad_data))

        items = iter_provider_safety_dossier_artifacts(ws, status_filter=_SAFE_STATUS_INVALID)
        assert len(items) == 1
        assert items[0]["_invalid"] is True
        assert items[0]["safe_status"] == _SAFE_STATUS_INVALID

    def test_list_status_filter_unsafe_tamper_detected(self, tmp_path: Path) -> None:
        ws = tmp_path
        dossier_id = "dossier_tampered"
        dossier_dir = ws / ".atlas" / "research" / "DEMO" / "provider_safety_dossiers"
        dossier_dir.mkdir(parents=True)
        dossier_path = dossier_dir / f"{dossier_id}.json"
        data = {
            "artifact_type": "provider_safety_dossier",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "contract_version": "research_provider_safety_dossier_v1",
            "provider_safety_dossier_id": dossier_id,
            "symbol": "DEMO",
            "provider_id": "mock",
            "sandbox_only": True,
            "chain_complete": True,
            "chain_nodes": [
                {"artifact_type": "a", "artifact_id": "1"},
                {"artifact_type": "b", "artifact_id": "2"},
                {"artifact_type": "c", "artifact_id": "3"},
                {"artifact_type": "d", "artifact_id": "4"},
                {"artifact_type": "e", "artifact_id": "5"},
                {"artifact_type": "f", "artifact_id": "6"},
            ],
            "provider_call_allowed": False,
            "actual_provider_call_made": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "trading_signal_generated": False,
            "approval_created": False,
            "pending_order_created": False,
            "broker_touched": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "trust_upgrade_performed": False,
            "trust_decision_granted": False,
            "provider_execution_unlocked": False,
            "real_provider_response_imported": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "artifact_hash": "tampered_hash_12345",
            "created_at": datetime.now(UTC).isoformat(),
            "artifact_path": str(dossier_path.relative_to(ws)),
        }
        dossier_path.write_text(json.dumps(data))

        items = iter_provider_safety_dossier_artifacts(ws, status_filter=_SAFE_STATUS_TAMPER)
        assert len(items) == 1
        assert items[0]["_invalid"] is True
        assert items[0]["safe_status"] == _SAFE_STATUS_TAMPER

    def test_list_invalid_filter_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ResearchSessionError, match="invalid_provider_safety_dossier_status_filter"):
            iter_provider_safety_dossier_artifacts(tmp_path, status_filter="invalid_status")

    def test_list_limit_respected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        # Create two dossiers with slight time gap
        run_id1, seal_id1 = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id1)
        import time
        time.sleep(0.01)
        run_id2, seal_id2 = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id2)

        items = iter_provider_safety_dossier_artifacts(ws)
        assert len(items) == 2
        limited = items[:1]
        assert len(limited) == 1

    def test_latest_output_no_absolute_paths(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id)

        result = latest_provider_safety_dossier(ws)
        result_json = json.dumps(result)
        assert "/private/var/" not in result_json
        assert "/Users/" not in result_json
        assert str(ws) not in result_json

    def test_list_output_no_absolute_paths(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id)

        items = iter_provider_safety_dossier_artifacts(ws)
        items_json = json.dumps(items)
        assert "/private/var/" not in items_json
        assert "/Users/" not in items_json
        assert str(ws) not in items_json

    def test_list_output_no_forbidden_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        ws = tmp_path
        run_id, seal_id = _full_chain_to_seal(ws, monkeypatch)
        create_provider_safety_dossier(ws, seal_id)

        items = iter_provider_safety_dossier_artifacts(ws)
        items_json = json.dumps(items)
        for frag in [
            "Authorization", "Bearer", "APCA", "SECRET", "TOKEN",
            "PASSWORD", "API_KEY", "sk-", "broker.example.com",
        ]:
            assert frag not in items_json, f"Forbidden fragment in list output: {frag}"
