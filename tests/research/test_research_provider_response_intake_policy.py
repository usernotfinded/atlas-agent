# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_provider_response_intake_policy.py
# PURPOSE: Verifies research provider response intake policy behavior and
#         regression expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_response_intake_policy import (
    PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION,
    _BOOLEAN_SAFETY_FLAGS,
    build_provider_response_intake_policy_dict,
    create_provider_response_intake_policy,
    find_provider_response_intake_policy_by_id,
    iter_provider_response_intake_policy_artifacts,
    load_and_validate_provider_response_intake_policy,
    provider_response_intake_policy_sha256,
    replay_provider_response_intake_policy,
    safe_validate_provider_response_intake_policy_data,
    summarize_provider_response_intake_policy_state,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION


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


def _full_chain_to_preview(tmp_path: Path, monkeypatch) -> tuple[str, str]:
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
    return run_id, preview_id


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


class TestProviderResponseIntakePolicyConfigless:
    def test_provider_response_intake_policy_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy", preview_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_intake_policy_created"
        assert "provider_response_intake_policy_id" in data
        assert data["provider_response_trusted"] is False

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_provider_response_intake_policy_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_intake_policy_list"
        assert len(data["items"]) >= 1

    def test_provider_response_intake_policy_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        policy_id = result["provider_response_intake_policy_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy-show", policy_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_intake_policy_shown"
        assert data["provider_response_intake_policy_id"] == policy_id

    def test_provider_response_intake_policy_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        policy_id = result["provider_response_intake_policy_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy-validate", policy_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True

    def test_provider_response_intake_policy_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        policy_id = result["provider_response_intake_policy_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy-replay", policy_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_provider_response_intake_policy_summary_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy-summary", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["provider_response_trusted"] is False
        assert data["provider_response_received"] is False


class TestProviderResponseIntakePolicyCreation:
    def test_valid_policy_creates_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_response_intake_policy_created"
        assert result["provider_response_trusted"] is False
        policy_id = result["provider_response_intake_policy_id"]
        artifact_path = tmp_path / result["artifact_path"]
        assert artifact_path.exists()

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "provider_response_intake_policy"
        assert data["contract_version"] == PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert "response_storage_policy" in data
        assert "response_redaction_policy" in data
        assert "response_validation_policy" in data
        assert "response_review_policy" in data
        assert "unsafe_response_policy" in data
        assert "trading_separation_policy" in data
        assert "response_hash_policy" in data
        assert "manual_review_policy" in data
        assert data["provider_response_received"] is False
        assert data["provider_response_trusted"] is False
        assert data["provider_response_can_create_orders"] is False
        assert data["provider_response_can_call_broker"] is False
        assert data["provider_enabled"] is False
        assert data["network_enabled"] is False
        assert data["credentials_loaded"] is False

    def test_create_json_envelope_includes_all_false_safety_flags(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)

        from unittest.mock import patch
        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-response-intake-policy", preview_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_response_intake_policy_created"

        required_false_fields = [
            "provider_response_received",
            "provider_response_imported",
            "provider_response_reviewed",
            "provider_response_can_create_orders",
            "provider_response_can_approve_orders",
            "provider_response_can_call_broker",
            "provider_call_allowed",
            "actual_provider_call_made",
            "trading_signal_generated",
            "approval_created",
            "pending_order_created",
            "broker_touched",
        ]
        for field in required_false_fields:
            assert field in data, f"Missing field in create JSON envelope: {field}"
            assert data[field] is False, f"Field {field} should be False, got {data[field]}"

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"

    def test_artifact_path_is_correct(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)

        assert ".atlas/research/" in result["artifact_path"]
        assert "provider_response_intake_policies" in result["artifact_path"]
        assert result["artifact_path"].endswith(".json")

    def test_output_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            main(["research", "provider-response-intake-policy-list", "--json"])

        out = capsys.readouterr().out
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"


class TestProviderResponseIntakePolicyArtifactDenylist:
    def test_artifact_does_not_contain_raw_forbidden_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text(encoding="utf-8")

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"Forbidden fragment in artifact: {frag}"

    def test_artifact_does_not_store_raw_denylist_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        denylist = data.get("denylist_metadata", {})
        assert denylist.get("forbidden_fragments_raw_stored") is False or denylist.get("raw_denylist_fragments_stored") is False


class TestProviderResponseIntakePolicySummary:
    def test_summary_on_valid_run_reports_policy_recorded(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        result = summarize_provider_response_intake_policy_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_response_intake_policy_summary"
        assert result["response_intake_policy_status"] == "response_intake_policy_recorded"
        assert result["provider_response_trusted"] is False
        assert result["provider_response_received"] is False
        assert result["provider_response_can_create_orders"] is False

    def test_summary_before_policy_exists_reports_safe_missing(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)

        result = summarize_provider_response_intake_policy_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "missing_provider_response_intake_policy"
        assert result["provider_response_intake_policy_id"] is None
        assert result["provider_response_trusted"] is False
        assert result["provider_response_received"] is False

    def test_summary_on_missing_run_fails_safely(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = summarize_provider_response_intake_policy_state(tmp_path, "run-99999999")
        assert result["ok"] is True
        assert result["status"] == "missing_provider_response_intake_policy"

    def test_summary_does_not_write_artifacts_or_events(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        events_before = list((tmp_path / "events").glob("*.jsonl"))
        policies_before = list((tmp_path / ".atlas" / "research").rglob("provider_response_intake_policies/*.json"))
        count_before = len(policies_before)

        summarize_provider_response_intake_policy_state(tmp_path, run_id)

        events_after = list((tmp_path / "events").glob("*.jsonl"))
        policies_after = list((tmp_path / ".atlas" / "research").rglob("provider_response_intake_policies/*.json"))
        assert len(policies_after) == count_before
        assert len(events_after) == len(events_before)


class TestProviderResponseIntakePolicySafetyTamper:
    def test_tampered_lineage_fails_closed(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_outbound_payload_preview_id"] = "tampered-id"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
        assert error is not None
        assert cleaned is None

    def test_impossible_boolean_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        for flag in _BOOLEAN_SAFETY_FLAGS:
            if flag not in data:
                continue
            data[flag] = True
            cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
            assert error is not None, f"Expected error for flag {flag}=True"
            assert cleaned is None
            data[flag] = False

    def test_forbidden_positive_claims_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
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
        ]
        for value in unsafe_values:
            data["response_intake_policy_status"] = value
            cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
            assert error is not None, f"Expected error for status={value}"
            assert cleaned is None
            data["response_intake_policy_status"] = "response_intake_policy_recorded"


class TestProviderResponseIntakePolicyReplayValidation:
    def test_valid_policy_validates(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        policy_id = result["provider_response_intake_policy_id"]

        artifact = load_and_validate_provider_response_intake_policy(
            tmp_path / result["artifact_path"], tmp_path
        )
        assert artifact["provider_response_intake_policy_id"] == policy_id

    def test_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["artifact_hash"] = "tampered_hash"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
        assert error == "provider_response_intake_policy_hash_mismatch"
        assert cleaned is None

    def test_source_payload_preview_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_outbound_payload_preview_id"] = "preview-99999999"
        data["artifact_hash"] = provider_response_intake_policy_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
        assert error == "provider_response_intake_policy_source_payload_preview_missing"
        assert cleaned is None

    def test_source_payload_preview_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_payload_preview_hash"] = "tampered_preview_hash"
        data["artifact_hash"] = provider_response_intake_policy_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path=tmp_path)
        assert error == "provider_response_intake_policy_source_payload_preview_hash_mismatch"
        assert cleaned is None

    def test_replay_mismatch_envelope_works(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        policy_id = result["provider_response_intake_policy_id"]

        replay = replay_provider_response_intake_policy(tmp_path, policy_id)
        assert replay["ok"] is True
        assert replay["match"] is True


class TestProviderResponseIntakePolicyTimelineCheckDossier:
    def test_check_artifacts_counts_intake_policies(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        assert result["counts"]["provider_response_intake_policies"] >= 1

    def test_check_artifacts_detects_intake_policy_tampering(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        data["provider_response_received"] = True
        data["artifact_hash"] = provider_response_intake_policy_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in result["issues"]}
        assert "provider_response_intake_policy_impossible_boolean" in issue_codes

    def test_timeline_links_intake_policy(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

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
                                                        if pp.get("provider_response_intake_policies"):
                                                            found = True
        assert found, "Timeline did not link intake policy under payload preview"

    def test_dossier_includes_intake_policy_summary(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        create_provider_response_intake_policy(tmp_path, preview_id)

        from atlas_agent.events.log import EventLogger
        from atlas_agent.research.session import build_dossier

        event_logger = EventLogger(tmp_path / "events")
        result = build_dossier(tmp_path, run_id, event_logger=event_logger)

        assert result["artifact_counts"]["provider_response_intake_policies"] >= 1
        assert "provider_response_intake_policy" in result["summaries"]
        assert result["summaries"]["provider_response_intake_policy"]["policy_count"] >= 1


class TestProviderResponseIntakePolicyInvalidLeakage:
    """Regression tests: invalid/tampered intake policy artifacts must not leak raw fields through list/timeline/check-artifacts."""

    def _tamper_and_list(self, tmp_path: Path, monkeypatch, capsys, tamper_fn) -> tuple[dict[str, Any], str, int]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, preview_id = _full_chain_to_preview(tmp_path, monkeypatch)
        result = create_provider_response_intake_policy(tmp_path, preview_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        tamper_fn(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        code = main(["research", "provider-response-intake-policy-list", "--json"])
        out = capsys.readouterr().out
        return json.loads(out), out, code

    def test_tampered_policy_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(data):
            data["provider_response_intake_policy_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
            data["artifact_hash"] = provider_response_intake_policy_sha256(data)

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
        assert invalid_items[0]["provider_response_intake_policy_id"] == "<invalid>"
        assert invalid_items[0]["provider_id"] == "unknown"
        assert invalid_items[0]["model_id"] == "unknown"
        assert invalid_items[0]["response_intake_policy_status"] == "invalid"
        assert invalid_items[0]["response_intake_policy_scope"] == "invalid"
        assert invalid_items[0].get("error_code") == "invalid_provider_response_intake_policy_artifact"

    def test_tampered_model_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(data):
            data["model_id"] = "sk-LEAKEDSECRET"
            data["artifact_hash"] = provider_response_intake_policy_sha256(data)

        data, out, code = self._tamper_and_list(tmp_path, monkeypatch, capsys, tamper)
        assert code == 0
        assert data["ok"] is True
        assert "sk-LEAKEDSECRET" not in out
        assert "sk-" not in out
        invalid_items = [i for i in data["items"] if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["model_id"] == "unknown"
        assert invalid_items[0]["provider_id"] == "unknown"
