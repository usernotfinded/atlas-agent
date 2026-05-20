from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research.provider_outbound_payload_preview import (
    PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION,
    _BOOLEAN_SAFETY_FLAGS,
    build_provider_outbound_payload_preview_dict,
    create_provider_outbound_payload_preview,
    find_provider_outbound_payload_preview_by_id,
    iter_provider_outbound_payload_preview_artifacts,
    load_and_validate_provider_outbound_payload_preview,
    provider_outbound_payload_preview_sha256,
    replay_provider_outbound_payload_preview,
    safe_validate_provider_outbound_payload_preview_data,
    summarize_provider_outbound_payload_preview_state,
)
from atlas_agent.research.session import RESEARCH_ARTIFACT_SCHEMA_VERSION


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


def _full_chain_to_boundary(tmp_path: Path, monkeypatch) -> tuple[str, str]:
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
    return run_id, boundary_id


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


class TestProviderPayloadPreviewConfigless:
    def test_provider_payload_preview_does_not_load_config_or_secrets(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview", boundary_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_outbound_payload_preview_created"
        assert "provider_outbound_payload_preview_id" in data
        assert data["payload_body_stored"] is False
        assert data["outbound_request_sent"] is False

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in output: {frag}"

    def test_provider_payload_preview_list_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview-list", "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_outbound_payload_previews_listed"
        assert len(data["items"]) >= 1

    def test_provider_payload_preview_show_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        preview_id = result["provider_outbound_payload_preview_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview-show", preview_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["status"] == "research_provider_outbound_payload_preview_loaded"
        assert data["artifact"]["provider_outbound_payload_preview_id"] == preview_id

    def test_provider_payload_preview_validate_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        preview_id = result["provider_outbound_payload_preview_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview-validate", preview_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["valid"] is True

    def test_provider_payload_preview_replay_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        preview_id = result["provider_outbound_payload_preview_id"]

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview-replay", preview_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["match"] is True

    def test_provider_payload_preview_summary_does_not_load_config(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            code = main(["research", "provider-payload-preview-summary", run_id, "--json"])

        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True
        assert data["payload_body_stored"] is False
        assert data["outbound_request_sent"] is False
        assert data["credentials_loaded"] is False


class TestProviderPayloadPreviewCreation:
    def test_valid_preview_creates_artifact(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)

        assert result["ok"] is True
        assert result["status"] == "research_provider_outbound_payload_preview_created"
        assert result["payload_body_stored"] is False
        assert result["outbound_request_sent"] is False
        preview_id = result["provider_outbound_payload_preview_id"]
        artifact_path = tmp_path / result["artifact_path"]
        assert artifact_path.exists()

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "provider_outbound_payload_preview"
        assert data["contract_version"] == PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert "payload_shape" in data
        assert "payload_minimization_summary" in data
        assert "payload_redaction_summary" in data
        assert "payload_hash" in data
        assert "blocked_fields" in data
        assert "omitted_fields" in data
        assert "allowed_field_summary" in data
        assert data["payload_body_stored"] is False
        assert data["raw_prompt_stored"] is False
        assert data["raw_provider_request_stored"] is False
        assert data["raw_provider_response_stored"] is False
        assert data["outbound_request_sent"] is False
        assert data["credentials_loaded"] is False
        assert data["provider_enabled"] is False
        assert data["network_enabled"] is False

    def test_artifact_path_is_correct(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)

        assert ".atlas/research/" in result["artifact_path"]
        assert "provider_outbound_payload_previews" in result["artifact_path"]
        assert result["artifact_path"].endswith(".json")

    def test_output_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        with patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_called), patch(
            "atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_called
        ):
            main(["research", "provider-payload-preview-list", "--json"])

        out = capsys.readouterr().out
        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in out, f"Forbidden fragment in CLI output: {frag}"


class TestProviderPayloadPreviewArtifactDenylist:
    def test_artifact_does_not_contain_raw_forbidden_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        text = artifact_path.read_text(encoding="utf-8")

        for frag in FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"Forbidden fragment in artifact: {frag}"

    def test_artifact_does_not_store_raw_denylist_fragments(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert data.get("raw_denylist_fragments_stored") is False or data.get("forbidden_fragments_raw_stored") is False


class TestProviderPayloadPreviewSummary:
    def test_summary_on_valid_run_reports_preview_recorded(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        result = summarize_provider_outbound_payload_preview_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "research_provider_outbound_payload_preview_summary"
        assert result["payload_preview_status"] == "payload_preview_recorded"
        assert result["payload_body_stored"] is False
        assert result["outbound_request_sent"] is False
        assert result["credentials_loaded"] is False

    def test_summary_before_preview_exists_reports_safe_missing(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)

        result = summarize_provider_outbound_payload_preview_state(tmp_path, run_id)
        assert result["ok"] is True
        assert result["status"] == "missing_provider_outbound_payload_preview"
        assert result["provider_outbound_payload_preview_id"] is None
        assert result["payload_body_stored"] is False
        assert result["outbound_request_sent"] is False

    def test_summary_on_missing_run_fails_safely(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = summarize_provider_outbound_payload_preview_state(tmp_path, "run-99999999")
        assert result["ok"] is True
        assert result["status"] == "missing_provider_outbound_payload_preview"

    def test_summary_does_not_write_artifacts_or_events(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        events_before = list((tmp_path / "events").glob("*.jsonl"))
        previews_before = list((tmp_path / ".atlas" / "research").rglob("provider_outbound_payload_previews/*.json"))
        count_before = len(previews_before)

        summarize_provider_outbound_payload_preview_state(tmp_path, run_id)

        events_after = list((tmp_path / "events").glob("*.jsonl"))
        previews_after = list((tmp_path / ".atlas" / "research").rglob("provider_outbound_payload_previews/*.json"))
        assert len(previews_after) == count_before
        assert len(events_after) == len(events_before)


class TestProviderPayloadPreviewSafetyTamper:
    def test_tampered_lineage_fails_closed(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_credential_boundary_id"] = "tampered-id"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
        assert error is not None
        assert cleaned is None

    def test_impossible_boolean_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        for flag in _BOOLEAN_SAFETY_FLAGS:
            if flag not in data:
                continue
            data[flag] = True
            cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
            assert error is not None, f"Expected error for flag {flag}=True"
            assert cleaned is None
            data[flag] = False

    def test_forbidden_positive_claims_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
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
            data["payload_preview_status"] = value
            cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
            assert error is not None, f"Expected error for status={value}"
            assert cleaned is None
            data["payload_preview_status"] = "payload_preview_recorded"


class TestProviderPayloadPreviewReplayValidation:
    def test_valid_preview_validates(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        preview_id = result["provider_outbound_payload_preview_id"]

        artifact = load_and_validate_provider_outbound_payload_preview(
            tmp_path / result["artifact_path"], tmp_path
        )
        assert artifact["provider_outbound_payload_preview_id"] == preview_id

    def test_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["artifact_hash"] = "tampered_hash"
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
        assert error == "provider_outbound_payload_preview_hash_mismatch"
        assert cleaned is None

    def test_source_credential_boundary_missing_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_provider_credential_boundary_id"] = "boundary-99999999"
        data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
        assert error == "provider_outbound_payload_preview_source_boundary_missing"
        assert cleaned is None

    def test_source_credential_boundary_hash_mismatch_detected(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        data["source_credential_boundary_hash"] = "tampered_boundary_hash"
        data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=tmp_path)
        assert error == "provider_outbound_payload_preview_source_boundary_hash_mismatch"
        assert cleaned is None

    def test_replay_mismatch_envelope_works(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        preview_id = result["provider_outbound_payload_preview_id"]

        replay = replay_provider_outbound_payload_preview(tmp_path, preview_id)
        assert replay["ok"] is True
        assert replay["match"] is True


class TestProviderPayloadPreviewTimelineCheckDossier:
    def test_check_artifacts_counts_previews(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        assert result["counts"]["provider_outbound_payload_previews"] >= 1

    def test_check_artifacts_detects_preview_tampering(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        data["payload_body_stored"] = True
        data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        from atlas_agent.research.session import check_research_artifacts
        result = check_research_artifacts(tmp_path)
        issue_codes = {i["code"] for i in result["issues"]}
        assert "provider_outbound_payload_preview_impossible_boolean" in issue_codes

    def test_timeline_links_payload_preview(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

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
                                                    if b.get("provider_outbound_payload_previews"):
                                                        found = True
        assert found, "Timeline did not link payload preview under credential boundary"

    def test_dossier_includes_payload_preview_summary(self, tmp_path: Path, monkeypatch) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        create_provider_outbound_payload_preview(tmp_path, boundary_id)

        from atlas_agent.events.log import EventLogger
        from atlas_agent.research.session import build_dossier

        event_logger = EventLogger(tmp_path / "events")
        result = build_dossier(tmp_path, run_id, event_logger=event_logger)

        assert result["artifact_counts"]["provider_outbound_payload_previews"] >= 1
        assert "provider_outbound_payload_preview" in result["summaries"]
        assert result["summaries"]["provider_outbound_payload_preview"]["preview_count"] >= 1


class TestProviderPayloadPreviewInvalidLeakage:
    """Regression tests: invalid/tampered payload preview artifacts must not leak raw fields through list/timeline/check-artifacts."""

    def _tamper_and_list(self, tmp_path: Path, monkeypatch, capsys, tamper_fn) -> tuple[dict[str, Any], str]:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        tamper_fn(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        code = main(["research", "provider-payload-preview-list", "--json"])
        out = capsys.readouterr().out
        return json.loads(out), out, code

    def test_tampered_preview_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(data):
            data["provider_outbound_payload_preview_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
            data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)

        data, out, code = self._tamper_and_list(tmp_path, monkeypatch, capsys, tamper)
        assert code == 0
        assert data["ok"] is True
        # Raw tampered value must not appear in output
        assert "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com" not in out
        assert "APCA" not in out
        assert "SECRET" not in out
        assert "TOKEN" not in out
        assert "sk-" not in out
        assert "broker.example.com" not in out
        # Invalid item should be a safe sentinel
        invalid_items = [i for i in data["items"] if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["provider_outbound_payload_preview_id"] == "<invalid>"
        assert invalid_items[0]["provider_id"] == "unknown"
        assert invalid_items[0]["model_id"] == "unknown"
        assert invalid_items[0]["payload_preview_status"] == "invalid"
        assert invalid_items[0]["payload_preview_scope"] == "invalid"
        assert invalid_items[0].get("error_code") == "invalid_provider_outbound_payload_preview_artifact"

    def test_tampered_model_id_does_not_leak_through_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        def tamper(data):
            data["model_id"] = "sk-LEAKEDSECRET"
            data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)

        data, out, code = self._tamper_and_list(tmp_path, monkeypatch, capsys, tamper)
        assert code == 0
        assert data["ok"] is True
        assert "sk-LEAKEDSECRET" not in out
        assert "sk-" not in out
        invalid_items = [i for i in data["items"] if i.get("_invalid")]
        assert len(invalid_items) >= 1
        assert invalid_items[0]["model_id"] == "unknown"
        assert invalid_items[0]["provider_id"] == "unknown"

    def test_invalid_list_sentinel_does_not_copy_raw_artifact_fields(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        data["provider_outbound_payload_preview_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        data["model_id"] = "sk-LEAKEDSECRET"
        data["payload_preview_status"] = "tampered_status"
        data["payload_preview_scope"] = "tampered_scope"
        data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        code = main(["research", "provider-payload-preview-list", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert code == 0
        assert data["ok"] is True

        invalid_items = [i for i in data["items"] if i.get("_invalid")]
        assert len(invalid_items) >= 1
        item = invalid_items[0]
        # Sentinel values only
        assert item["provider_outbound_payload_preview_id"] == "<invalid>"
        assert item["provider_id"] == "unknown"
        assert item["model_id"] == "unknown"
        assert item["payload_preview_status"] == "invalid"
        assert item["payload_preview_scope"] == "invalid"
        assert item.get("error_code") == "invalid_provider_outbound_payload_preview_artifact"
        # Raw tampered values absent
        assert "APCA" not in out
        assert "SECRET" not in out
        assert "sk-" not in out
        assert "broker.example.com" not in out
        assert "tampered_status" not in out
        assert "tampered_scope" not in out

    def test_tampered_timeline_and_check_artifacts_stay_denylist_clean(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)
        result = create_provider_outbound_payload_preview(tmp_path, boundary_id)
        artifact_path = tmp_path / result["artifact_path"]
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        data["provider_outbound_payload_preview_id"] = "APCA_SECRET_TOKEN_sk-LEAKEDSECRET_broker.example.com"
        data["model_id"] = "sk-LEAKEDSECRET"
        data["artifact_hash"] = provider_outbound_payload_preview_sha256(data)
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        from atlas_agent.research.session import check_research_artifacts, build_research_timeline

        check_result = check_research_artifacts(tmp_path)
        check_out = json.dumps(check_result)
        assert "APCA" not in check_out
        assert "SECRET" not in check_out
        assert "sk-" not in check_out
        assert "broker.example.com" not in check_out
        # check-artifacts should detect the invalid artifact
        assert any(i["code"].startswith("invalid") for i in check_result.get("issues", []))

        timeline_result = build_research_timeline(tmp_path)
        timeline_out = json.dumps(timeline_result)
        assert "APCA" not in timeline_out
        assert "SECRET" not in timeline_out
        assert "sk-" not in timeline_out
        assert "broker.example.com" not in timeline_out


class TestProviderPayloadPreviewCLI:
    def test_cli_create_and_list(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)

        code = main(["research", "provider-payload-preview", boundary_id, "--json"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        preview_id = data["provider_outbound_payload_preview_id"]

        code = main(["research", "provider-payload-preview-list", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        ids = [i["provider_outbound_payload_preview_id"] for i in data["items"]]
        assert preview_id in ids

    def test_cli_show_validate_replay_summary(self, tmp_path: Path, monkeypatch, capsys) -> None:
        _ensure_workspace(tmp_path)
        monkeypatch.chdir(tmp_path)
        run_id, boundary_id = _full_chain_to_boundary(tmp_path, monkeypatch)

        code = main(["research", "provider-payload-preview", boundary_id, "--json"])
        assert code == 0
        preview_id = json.loads(capsys.readouterr().out)["provider_outbound_payload_preview_id"]

        code = main(["research", "provider-payload-preview-show", preview_id, "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["status"] == "research_provider_outbound_payload_preview_loaded"

        code = main(["research", "provider-payload-preview-validate", preview_id, "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["valid"] is True

        code = main(["research", "provider-payload-preview-replay", preview_id, "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["match"] is True

        code = main(["research", "provider-payload-preview-summary", run_id, "--json"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "research_provider_outbound_payload_preview_summary"
        assert data["payload_body_stored"] is False
        assert data["outbound_request_sent"] is False
