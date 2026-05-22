from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_adapter_interface_contract import (
    PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION,
    _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE,
    build_provider_adapter_interface_contract_dict,
    create_provider_adapter_interface_contract,
    doctor_provider_adapter_interface_contract,
    find_provider_adapter_interface_contract_by_id,
    iter_provider_adapter_interface_contract_artifacts,
    load_and_validate_provider_adapter_interface_contract,
    provider_adapter_interface_contract_sha256,
    replay_provider_adapter_interface_contract,
    run_disabled_adapter_smoke,
    safe_validate_provider_adapter_interface_contract_data,
    summarize_provider_adapter_interface_contract,
    validate_provider_adapter_interface_contract_artifact,
)
from atlas_agent.research.provider_adapter_interface import (
    DisabledProviderAdapter,
    ProviderAdapterDisabledError,
    ProviderAdapterCapability,
    ProviderAdapterProtocol,
    ProviderAdapterRequestPreview,
    ProviderAdapterResponsePlaceholder,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION
from atlas_agent.research.provider_execution_unlock_state import create_provider_execution_unlock_state
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


def _create_provider_execution_unlock_state(tmp_path: Path, monkeypatch, review_result_id: str) -> str:
    monkeypatch.chdir(tmp_path)
    result = create_provider_execution_unlock_state(
        workspace_path=tmp_path,
        review_result_id=review_result_id,
    )
    return result["provider_execution_unlock_state_id"]


def _full_chain_to_review_result(tmp_path: Path, monkeypatch) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
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


def _full_chain_to_unlock_state(tmp_path: Path, monkeypatch) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    (
        run_id, prompt_id, sandbox_id, plan_id, dry_run_id, state_id,
        audit_packet_id, readiness_report_id, freeze_id, policy_id,
        boundary_id, preview_id, intake_id, pairing_id, schema_contract_id,
        review_result_id,
    ) = _full_chain_to_review_result(tmp_path, monkeypatch)
    unlock_state_id = _create_provider_execution_unlock_state(tmp_path, monkeypatch, review_result_id)
    return (
        run_id, prompt_id, sandbox_id, plan_id, dry_run_id, state_id,
        audit_packet_id, readiness_report_id, freeze_id, policy_id,
        boundary_id, preview_id, intake_id, pairing_id, schema_contract_id,
        review_result_id, unlock_state_id,
    )


# ---------------------------------------------------------------------------
# Configless safety
# ---------------------------------------------------------------------------

class TestConfiglessSafety:
    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_create_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract", unlock_state_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_list_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-list", "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_show_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-show", result["provider_adapter_interface_contract_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_validate_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-validate", result["provider_adapter_interface_contract_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_replay_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-replay", result["provider_adapter_interface_contract_id"], "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_summary_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-summary", run_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_doctor_contract_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-doctor", run_id, "--json"]):
            assert main() == 0

    @patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called)
    @patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called)
    def test_disabled_smoke_is_configless(self, _mock_secrets, _mock_config, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)
        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-disabled-smoke", result["provider_adapter_interface_contract_id"], "--json"]):
            assert main() == 0


# ---------------------------------------------------------------------------
# Disabled adapter
# ---------------------------------------------------------------------------

class TestDisabledAdapter:
    def test_capabilities_returns_disabled_flags(self):
        adapter = DisabledProviderAdapter()
        cap = adapter.capabilities()
        assert cap.provider_id == "disabled"
        assert cap.adapter_status == "disabled"
        assert cap.supports_text_generation is False
        assert cap.supports_streaming is False
        assert cap.supports_tool_calls is False
        assert cap.supports_network_calls is False
        assert cap.supports_credential_loading is False
        assert cap.supports_provider_execution is False
        assert cap.supports_broker_bridge is False

    def test_build_request_preview_returns_safe_metadata(self):
        adapter = DisabledProviderAdapter()
        preview = adapter.build_request_preview(
            request_preview_id="test-preview",
            source_provider_execution_unlock_state_id="test-unlock",
            source_provider_outbound_payload_preview_id="test-preview-src",
            provider_id="disabled",
            model_id="disabled",
            request_family="test",
            payload_hash="test-hash",
        )
        assert preview.payload_body_present is False
        assert preview.raw_prompt_present is False
        assert preview.credentials_present is False
        assert preview.network_required is False
        assert preview.provider_call_allowed is False

    def test_send_raises_provider_adapter_disabled_error(self):
        adapter = DisabledProviderAdapter()
        preview = adapter.build_request_preview(
            request_preview_id="test-preview",
            source_provider_execution_unlock_state_id="test-unlock",
            source_provider_outbound_payload_preview_id="test-preview-src",
            provider_id="disabled",
            model_id="disabled",
            request_family="test",
            payload_hash="test-hash",
        )
        with pytest.raises(ProviderAdapterDisabledError):
            adapter.send(preview)

    def test_error_message_is_static_safe(self):
        adapter = DisabledProviderAdapter()
        preview = adapter.build_request_preview(
            request_preview_id="test-preview",
            source_provider_execution_unlock_state_id="test-unlock",
            source_provider_outbound_payload_preview_id="test-preview-src",
            provider_id="disabled",
            model_id="disabled",
            request_family="test",
            payload_hash="test-hash",
        )
        with pytest.raises(ProviderAdapterDisabledError) as exc_info:
            adapter.send(preview)
        msg = str(exc_info.value)
        assert "Authorization" not in msg
        assert "Bearer" not in msg
        assert "/Users/" not in msg
        assert "provider_adapter_disabled" in msg

    def test_send_does_not_set_response_received(self):
        adapter = DisabledProviderAdapter()
        preview = adapter.build_request_preview(
            request_preview_id="test-preview",
            source_provider_execution_unlock_state_id="test-unlock",
            source_provider_outbound_payload_preview_id="test-preview-src",
            provider_id="disabled",
            model_id="disabled",
            request_family="test",
            payload_hash="test-hash",
        )
        try:
            adapter.send(preview)
        except ProviderAdapterDisabledError:
            pass

    def test_validate_response_placeholder_works(self):
        adapter = DisabledProviderAdapter()
        placeholder = ProviderAdapterResponsePlaceholder(
            response_placeholder_id="test-placeholder",
            provider_response_received=False,
            provider_response_trusted=False,
            provider_response_imported=False,
            raw_response_body_present=False,
            response_hash_present=False,
            manual_review_required=True,
        )
        assert adapter.validate_response_placeholder(placeholder) is True


# ---------------------------------------------------------------------------
# Artifact creation
# ---------------------------------------------------------------------------

class TestArtifactCreation:
    def test_create_contract_creates_artifact(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_adapter_interface_contract_created"
        assert result["provider_adapter_interface_contract_id"]
        assert result["source_provider_execution_unlock_state_id"] == unlock_state_id
        assert result["adapter_contract_status"] == "adapter_interface_recorded"
        assert result["adapter_state"] == "disabled_adapter_only"
        assert Path(tmp_path / result["artifact_path"]).exists()

    def test_artifact_includes_all_policy_structures(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert "adapter_capability_summary" in data
        assert "disabled_adapter_policy" in data
        assert "request_preview_contract" in data
        assert "response_placeholder_contract" in data
        assert "send_method_policy" in data
        assert "credential_access_policy" in data
        assert "network_access_policy" in data
        assert "provider_sdk_policy" in data
        assert "error_handling_policy" in data
        assert "side_effect_policy" in data
        assert "broker_separation_policy" in data
        assert "future_adapter_requirements" in data

    def test_adapter_interface_recorded_is_true(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["adapter_interface_recorded"] is True
        assert data["disabled_adapter_available"] is True
        assert data["adapter_present"] is False
        assert data["adapter_enabled"] is False
        assert data["real_provider_adapter_implemented"] is False
        assert data["provider_sdk_imported"] is False
        assert data["http_client_imported"] is False
        assert data["network_enabled"] is False
        assert data["credentials_loaded"] is False
        assert data["provider_call_allowed"] is False
        assert data["actual_provider_call_made"] is False

    def test_artifact_path_is_correct(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        assert ".atlas/research/AAPL/provider_adapter_interface_contracts/" in result["artifact_path"]

    def test_output_is_denylist_clean(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
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
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
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
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["denylist_metadata"]["forbidden_fragments_raw_stored"] is False

    def test_artifact_does_not_include_request_or_response_body(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
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
    def test_summary_reports_contract_recorded(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        result = summarize_provider_adapter_interface_contract(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_adapter_interface_contract_summary"
        assert result["adapter_present"] is False
        assert result["adapter_enabled"] is False
        assert result["real_provider_adapter_implemented"] is False
        assert result["provider_call_allowed"] is False
        assert result["provider_adapter_interface_contract_id"] is not None

    def test_summary_before_contract_exists_reports_missing(self, tmp_path, monkeypatch):
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        result = summarize_provider_adapter_interface_contract(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "missing_provider_adapter_interface_contract"
        assert result["provider_adapter_interface_contract_id"] is None

    def test_summary_on_missing_run_fails_safely(self, tmp_path):
        result = summarize_provider_adapter_interface_contract(tmp_path, "missing-run-123")

        assert result["ok"] is True
        assert result["status"] == "missing_provider_adapter_interface_contract"


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class TestDoctor:
    def test_doctor_reports_disabled_adapter_only(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        result = doctor_provider_adapter_interface_contract(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_adapter_interface_contract_doctor"
        assert result["adapter_present"] is False
        assert result["adapter_enabled"] is False
        assert result["real_provider_adapter_implemented"] is False
        assert result["provider_call_allowed"] is False
        assert result["adapter_health"] == "disabled_adapter_only"

    def test_doctor_reports_missing_future_prerequisites(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        result = doctor_provider_adapter_interface_contract(tmp_path, run_id)

        missing = result.get("missing_prerequisites", [])
        assert any("real_provider_adapter" in m for m in missing)
        assert any("credential_loader" in m for m in missing)
        assert any("network_policy" in m for m in missing)

    def test_doctor_before_contract_exists_reports_missing(self, tmp_path, monkeypatch):
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        result = doctor_provider_adapter_interface_contract(tmp_path, run_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_adapter_interface_contract_doctor"
        assert result["adapter_health"] == "adapter_interface_contract_missing"

    def test_doctor_on_missing_run_fails_safely(self, tmp_path):
        result = doctor_provider_adapter_interface_contract(tmp_path, "missing-run-123")

        assert result["ok"] is True
        assert result["status"] == "research_provider_adapter_interface_contract_doctor"
        assert result["adapter_health"] == "adapter_interface_contract_missing"

    def test_doctor_output_is_denylist_clean(self, tmp_path, monkeypatch):
        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        result = doctor_provider_adapter_interface_contract(tmp_path, run_id)
        text = json.dumps(result)

        assert "Authorization" not in text
        assert "Bearer" not in text
        assert "/Users/" not in text


# ---------------------------------------------------------------------------
# Disabled smoke
# ---------------------------------------------------------------------------

class TestDisabledSmoke:
    def test_smoke_passes_on_valid_contract(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        contract_id = result["provider_adapter_interface_contract_id"]

        smoke = run_disabled_adapter_smoke(contract_id)

        assert smoke["ok"] is True
        assert smoke["status"] == "research_provider_adapter_disabled_smoke_passed"
        assert smoke["send_failed_closed"] is True
        assert smoke["static_safe_error"] is True
        assert smoke["provider_response_received"] is False
        assert smoke["network_call_attempted"] is False
        assert smoke["credentials_loaded"] is False
        assert smoke["broker_touched"] is False
        assert smoke["provider_call_allowed"] is False

    def test_smoke_passes_with_any_valid_contract_id(self):
        smoke = run_disabled_adapter_smoke("test-contract-id-123")
        assert smoke["ok"] is True
        assert smoke["send_failed_closed"] is True
        assert smoke["static_safe_error"] is True


# ---------------------------------------------------------------------------
# Safety / tamper
# ---------------------------------------------------------------------------

class TestSafetyTamper:
    def test_tampered_contract_id_fails(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_adapter_interface_contract_id"] = "../tampered"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "invalid_provider_adapter_interface_contract_lineage"

    def test_tampered_source_unlock_state_id_fails(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_provider_execution_unlock_state_id"] = "../tampered"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "invalid_provider_adapter_interface_contract_lineage"

    def test_impossible_boolean_detected_adapter_present(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_present"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_adapter_enabled(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_enabled"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_real_provider_adapter_implemented(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["real_provider_adapter_implemented"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_provider_sdk_imported(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_sdk_imported"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_network_enabled(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["network_enabled"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_credentials_loaded(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["credentials_loaded"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_provider_call_allowed(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_call_allowed"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_actual_provider_call_made(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["actual_provider_call_made"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_provider_response_received(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_response_received"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_provider_response_trusted(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["provider_response_trusted"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_trading_signal_generated(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["trading_signal_generated"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_approval_created(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["approval_created"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_pending_order_created(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["pending_order_created"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_impossible_boolean_detected_broker_touched(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["broker_touched"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_impossible_boolean"

    def test_forbidden_positive_claim_in_policy_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["disabled_adapter_policy"]["disabled_adapter_can_call_provider"] = "Authorization"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_malformed"

    def test_no_raw_artifact_serialization_on_tamper(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_present"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, _ = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None

    def test_tampered_send_method_policy_positive_claim_detected_after_rehash(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["send_method_policy"]["tampered_claim"] = "provider call allowed and send succeeded"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_forbidden_adapter_claim"

        from atlas_agent.research.session import check_research_artifacts
        check_result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in check_result["issues"]}
        assert "provider_adapter_interface_contract_forbidden_adapter_claim" in issue_codes

        text = json.dumps(check_result)
        assert "provider call allowed and send succeeded" not in text
        assert "Authorization" not in text

    def test_tampered_future_adapter_requirements_trading_claim_detected_after_rehash(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["future_adapter_requirements"]["tampered_claim"] = "create order and call broker"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_forbidden_adapter_claim"

        from atlas_agent.research.session import check_research_artifacts
        check_result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in check_result["issues"]}
        assert "provider_adapter_interface_contract_forbidden_adapter_claim" in issue_codes

        text = json.dumps(check_result)
        assert "create order and call broker" not in text

    def test_safe_negative_policy_strings_do_not_trigger_false_positive(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        # Safe negative phrases should not trigger false positives
        data["send_method_policy"]["safe_note"] = "disabled_adapter_send_returns_success is false"
        data["future_adapter_requirements"]["safe_note"] = "future_real_adapter_requires_network_policy is true"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is not None
        assert error is None

    def test_list_timeline_denylist_clean_after_positive_claim_tamper(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["send_method_policy"]["tampered_claim"] = "provider call allowed and send succeeded"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        items = iter_provider_adapter_interface_contract_artifacts(tmp_path)
        for item in items:
            if item.get("_invalid"):
                text = json.dumps(item)
                assert "provider call allowed and send succeeded" not in text
                assert "<invalid>" in text

        from atlas_agent.research.session import build_research_timeline
        timeline = build_research_timeline(tmp_path)
        text = json.dumps(timeline)
        assert "provider call allowed and send succeeded" not in text


# ---------------------------------------------------------------------------
# Replay / validation
# ---------------------------------------------------------------------------

class TestReplayValidation:
    def test_valid_contract_replay_matches(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])

        assert replay["ok"] is True
        assert replay["match"] is True

    def test_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["symbol"] = "TAMPERED"
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_unlock_state_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_execution_unlock_state import find_provider_execution_unlock_state_by_id
        us_path = find_provider_execution_unlock_state_by_id(tmp_path, unlock_state_id)
        if us_path:
            us_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_unlock_state_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_unlock_state_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_unlock_state_hash_mismatch"

    def test_source_review_result_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_response_review_result import find_provider_response_review_result_by_id
        rr_path = find_provider_response_review_result_by_id(tmp_path, review_result_id)
        if rr_path:
            rr_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_review_result_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_review_result_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_review_result_hash_mismatch"

    def test_source_schema_contract_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_response_schema_contract import find_provider_response_schema_contract_by_id
        sc_path = find_provider_response_schema_contract_by_id(tmp_path, schema_contract_id)
        if sc_path:
            sc_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_schema_contract_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_schema_contract_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_schema_contract_hash_mismatch"

    def test_source_pairing_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_request_response_pairing import find_provider_request_response_pairing_by_id
        pairing_path = find_provider_request_response_pairing_by_id(tmp_path, pairing_id)
        if pairing_path:
            pairing_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_pairing_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_pairing_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_pairing_hash_mismatch"

    def test_source_response_intake_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_response_intake_policy import find_provider_response_intake_policy_by_id
        intake_path = find_provider_response_intake_policy_by_id(tmp_path, intake_id)
        if intake_path:
            intake_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_response_intake_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_response_intake_policy_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_response_intake_hash_mismatch"

    def test_source_payload_preview_missing_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        from atlas_agent.research.provider_outbound_payload_preview import find_provider_outbound_payload_preview_by_id
        preview_path = find_provider_outbound_payload_preview_by_id(tmp_path, preview_id)
        if preview_path:
            preview_path.unlink()

        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])
        assert replay["match"] is False

    def test_source_payload_preview_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_payload_preview_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_payload_preview_hash_mismatch"

    def test_replay_returns_safety_flags(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        replay = replay_provider_adapter_interface_contract(tmp_path, result["provider_adapter_interface_contract_id"])

        assert replay["provider_response_received"] is False
        assert replay["network_call_attempted"] is False
        assert replay["credentials_loaded"] is False
        assert replay["provider_call_allowed"] is False
        assert replay["broker_touched"] is False


# ---------------------------------------------------------------------------
# Timeline / check / dossier integration
# ---------------------------------------------------------------------------

class TestTimelineCheckDossier:
    def test_check_artifacts_counts_contracts(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import check_research_artifacts

        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        result = check_research_artifacts(tmp_path)

        assert result["counts"]["provider_adapter_interface_contracts"] >= 1

    def test_check_artifacts_detects_contract_tampering(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import check_research_artifacts

        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_present"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        check_result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in check_result["issues"]}
        assert "provider_adapter_interface_contract_impossible_boolean" in issue_codes

    def test_timeline_links_contract(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import build_research_timeline

        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        timeline = build_research_timeline(tmp_path, run_id_filter=run_id)

        entries = timeline.get("entries", [])
        assert len(entries) > 0
        found_contract = False
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
                                                                        for paic in prrr.get("provider_adapter_interface_contracts", []):
                                                                            if paic.get("provider_adapter_interface_contract_id"):
                                                                                found_contract = True
                                                                                assert paic.get("adapter_present") is False
                                                                                assert paic.get("adapter_enabled") is False
        assert found_contract

    def test_dossier_includes_contract_summary(self, tmp_path, monkeypatch):
        from atlas_agent.research.session import build_dossier

        (
            run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        dossier = build_dossier(tmp_path, run_id)

        counts = dossier.get("artifact_counts", {})
        assert counts.get("provider_adapter_interface_contracts", 0) >= 1

        linked = dossier.get("linked_artifacts", [])
        contract_linked = [a for a in linked if a.get("type") == "provider_adapter_interface_contract"]
        assert len(contract_linked) >= 1


# ---------------------------------------------------------------------------
# List / find
# ---------------------------------------------------------------------------

class TestListFind:
    def test_list_returns_contracts(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        items = iter_provider_adapter_interface_contract_artifacts(tmp_path)

        ids = {i["provider_adapter_interface_contract_id"] for i in items if not i.get("_invalid")}
        assert result["provider_adapter_interface_contract_id"] in ids

    def test_find_by_id_returns_path(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        path = find_provider_adapter_interface_contract_by_id(tmp_path, result["provider_adapter_interface_contract_id"])

        assert path is not None
        assert path.exists()

    def test_find_by_invalid_id_returns_none(self, tmp_path):
        path = find_provider_adapter_interface_contract_by_id(tmp_path, "nonexistent-id-123")
        assert path is None


# ---------------------------------------------------------------------------
# Invalid artifact leakage
# ---------------------------------------------------------------------------

class TestInvalidArtifactLeakage:
    def test_invalid_contract_uses_safe_sentinel(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        artifact_path.write_text("{not valid json")

        items = iter_provider_adapter_interface_contract_artifacts(tmp_path)
        invalid_items = [i for i in items if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["provider_adapter_interface_contract_id"] == "<invalid>"
        assert invalid_items[0]["adapter_contract_status"] == "invalid"

    def test_malformed_contract_skipped_in_list(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        artifact_path.write_text("{not valid json")

        items = iter_provider_adapter_interface_contract_artifacts(tmp_path)
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
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = load_and_validate_provider_adapter_interface_contract(artifact_path, tmp_path)

        assert data["provider_adapter_interface_contract_id"] == result["provider_adapter_interface_contract_id"]

    def test_load_and_validate_fails_on_tamper(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_present"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        from atlas_agent.research.session import ResearchSessionError
        with pytest.raises(ResearchSessionError):
            load_and_validate_provider_adapter_interface_contract(artifact_path, tmp_path)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_unsupported_schema_rejected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["schema_version"] = "999"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "unsupported_provider_adapter_interface_contract_schema"


# ---------------------------------------------------------------------------
# Boolean safety flags completeness
# ---------------------------------------------------------------------------

class TestBooleanSafetyFlags:
    def test_all_must_be_false_flags_are_false(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
            assert data.get(flag) is False, f"Expected {flag} to be False"

    def test_adapter_interface_recorded_is_true(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())

        assert data["adapter_interface_recorded"] is True
        assert data["disabled_adapter_available"] is True


# ---------------------------------------------------------------------------
# Source hash validation
# ---------------------------------------------------------------------------

class TestSourceHashValidation:
    def test_source_unlock_state_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_unlock_state_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_unlock_state_hash_mismatch"

    def test_source_review_result_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_review_result_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_review_result_hash_mismatch"

    def test_source_schema_contract_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_schema_contract_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_schema_contract_hash_mismatch"

    def test_source_pairing_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_pairing_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_pairing_hash_mismatch"

    def test_source_intake_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_response_intake_policy_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_response_intake_hash_mismatch"

    def test_source_payload_preview_hash_mismatch_detected(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["source_payload_preview_hash"] = "tamperedhash123"
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=tmp_path)
        assert cleaned is None
        assert error == "provider_adapter_interface_contract_source_payload_preview_hash_mismatch"


# ---------------------------------------------------------------------------
# Policy content
# ---------------------------------------------------------------------------

class TestPolicyContent:
    def test_disabled_adapter_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["disabled_adapter_policy"]

        assert policy["disabled_adapter_must_fail_send"] is True
        assert policy["disabled_adapter_send_returns_success"] is False
        assert policy["disabled_adapter_can_call_provider"] is False
        assert policy["disabled_adapter_can_use_network"] is False
        assert policy["disabled_adapter_can_load_credentials"] is False
        assert policy["disabled_adapter_can_call_broker"] is False
        assert policy["disabled_adapter_error_static_safe"] is True

    def test_send_method_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["send_method_policy"]

        assert policy["send_method_defined_by_interface"] is True
        assert policy["send_method_disabled_in_this_batch"] is True
        assert policy["send_method_must_fail_closed"] is True
        assert policy["send_method_returns_provider_response"] is False
        assert policy["send_method_can_use_network"] is False
        assert policy["send_method_can_load_credentials"] is False
        assert policy["send_method_can_create_orders"] is False
        assert policy["send_method_can_call_broker"] is False

    def test_credential_access_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["credential_access_policy"]

        assert policy["credential_access_allowed"] is False
        assert policy["credential_lookup_attempted"] is False
        assert policy["env_lookup_allowed"] is False
        assert policy["dotenv_loading_allowed"] is False
        assert policy["api_key_required_in_this_batch"] is False
        assert policy["future_credential_loader_required"] is True

    def test_network_access_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["network_access_policy"]

        assert policy["network_access_allowed"] is False
        assert policy["network_call_attempted"] is False
        assert policy["http_client_imported"] is False
        assert policy["provider_network_call_allowed"] is False
        assert policy["future_network_policy_required"] is True

    def test_broker_separation_policy_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["broker_separation_policy"]

        assert policy["broker_live_bridge_allowed"] is False
        assert policy["broker_adapter_access_allowed"] is False
        assert policy["order_routing_allowed"] is False
        assert policy["approval_manager_access_allowed"] is False
        assert policy["risk_manager_access_allowed"] is False

    def test_future_adapter_requirements_values(self, tmp_path, monkeypatch):
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        policy = data["future_adapter_requirements"]

        assert policy["future_real_adapter_requires_manual_unlock"] is True
        assert policy["future_real_adapter_requires_credential_loader"] is True
        assert policy["future_real_adapter_requires_network_policy"] is True
        assert policy["future_real_adapter_requires_provider_sdk_policy"] is True
        assert policy["future_real_adapter_requires_response_import_policy"] is True
        assert policy["future_real_adapter_cannot_call_broker"] is True


# ---------------------------------------------------------------------------
# CLI edge cases
# ---------------------------------------------------------------------------

class TestCliEdgeCases:
    def test_create_contract_with_missing_unlock_state(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract", "missing-id-123", "--json"]):
            assert main() == 1

    def test_show_contract_with_missing_id(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-show", "missing-id-123", "--json"]):
            assert main() == 1

    def test_replay_contract_with_missing_id(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-replay", "missing-id-123", "--json"]):
            assert main() == 1

    def test_validate_contract_strict_exits_nonzero(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["adapter_present"] = True
        data["artifact_hash"] = provider_adapter_interface_contract_sha256(data)
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-validate", result["provider_adapter_interface_contract_id"], "--json", "--strict"]):
            assert main() == 2

    def test_replay_contract_strict_exits_nonzero(self, tmp_path, monkeypatch):
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        (
            _run_id, _prompt_id, _sandbox_id, _plan_id, _dry_run_id, _state_id,
            _audit_packet_id, _readiness_report_id, _freeze_id, _policy_id,
            _boundary_id, _preview_id, _intake_id, _pairing_id, _schema_contract_id,
            _review_result_id, unlock_state_id,
        ) = _full_chain_to_unlock_state(tmp_path, monkeypatch)

        result = create_provider_adapter_interface_contract(tmp_path, unlock_state_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text())
        data["symbol"] = "TAMPERED"
        artifact_path.write_text(json.dumps(data, indent=2, sort_keys=True))

        with patch("sys.argv", ["atlas", "research", "provider-adapter-interface-contract-replay", result["provider_adapter_interface_contract_id"], "--json", "--strict"]):
            assert main() == 2
