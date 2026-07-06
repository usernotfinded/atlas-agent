from __future__ import annotations

import hashlib
import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.research import provider_mock_response_final_safety_seal as final_safety_seal
from atlas_agent.research.sandbox_contracts import canonical_json_dumps
from atlas_agent.research.session import ResearchSessionError
from tests.research.test_research_provider_mock_response_final_safety_seal import (
    _ensure_workspace,
    _full_chain_to_trust_decision_blocker,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "provider_artifacts" / "final_safety_seal"


def _load_json_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8").rstrip()


def _fixture_source_blocker() -> dict[str, Any]:
    return {
        "provider_mock_response_trust_decision_blocker_id": "blocker-golden-001",
        "artifact_hash": "0" * 64,
        "source_run_id": "run-golden-001",
        "symbol": "AAPL",
        "model_id": "gpt-4o",
        "source_provider_id": "mock",
    }


def _build_pinned_fixture_artifact() -> dict[str, Any]:
    artifact = final_safety_seal.build_provider_mock_response_final_safety_seal_dict(
        source_trust_decision_blocker=_fixture_source_blocker(),
        seal_id="seal-golden-001",
        workspace_path=Path("/tmp/atlas-golden-workspace"),
    )
    artifact["created_at"] = "2026-01-01T00:00:00+00:00"
    return artifact


def _artifact_from_case(name: str) -> tuple[dict[str, Any], str]:
    case = _load_json_fixture(name)
    artifact = deepcopy(_load_json_fixture(case["base_fixture"]))
    for field in case.get("remove_fields", []):
        artifact.pop(field, None)
    for field, value in case.get("mutations", {}).items():
        artifact[field] = value
    return artifact, case["expected_error"]


def _raise_if_config_or_secrets_are_loaded(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("Config/secrets loader must not be called by configless research commands")


def _workspace_with_final_safety_seal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _ensure_workspace(tmp_path)
    run_id, blocker_id = _full_chain_to_trust_decision_blocker(tmp_path, monkeypatch)
    result = final_safety_seal.create_provider_mock_response_final_safety_seal(tmp_path, blocker_id)
    seal_id = result["provider_mock_response_final_safety_seal_id"]
    path = final_safety_seal.find_provider_mock_response_final_safety_seal_by_id(tmp_path, seal_id)
    assert path is not None
    data = final_safety_seal.load_provider_mock_response_final_safety_seal(path, tmp_path)
    return {
        "run_id": run_id,
        "blocker_id": blocker_id,
        "seal_id": seal_id,
        "path": path,
        "data": data,
    }


def _run_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["atlas", *argv])
    with (
        patch("atlas_agent.cli.AtlasConfig.from_env", side_effect=_raise_if_config_or_secrets_are_loaded),
        patch("atlas_agent.config.secrets.load_atlas_secrets", side_effect=_raise_if_config_or_secrets_are_loaded),
    ):
        code = main()
    captured = capsys.readouterr()
    assert captured.err == ""
    return code, captured.out


def _replacement_map(context: dict[str, Any]) -> dict[str, str]:
    data = context["data"]
    return {
        context["seal_id"]: "<SEAL_ID>",
        context["blocker_id"]: "<BLOCKER_ID>",
        context["run_id"]: "<RUN_ID>",
        data["artifact_hash"]: "<ARTIFACT_HASH>",
        data["source_trust_decision_blocker_hash"]: "<SOURCE_BLOCKER_HASH>",
    }


def _normalize_dynamic_values(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        normalized = value
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return normalized
    if isinstance(value, list):
        return [_normalize_dynamic_values(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_dynamic_values(item, replacements) for key, item in value.items()}
    return value


def _project(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload[key] for key in keys}


def test_pilot_module_imports_without_filesystem_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    module = importlib.reload(final_safety_seal)
    assert list(tmp_path.iterdir()) == []
    assert module.PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION == (
        "research_provider_mock_response_final_safety_seal_v1"
    )


def test_build_artifact_matches_valid_golden_required_fields() -> None:
    expected = _load_json_fixture("artifact_valid.json")
    actual = _build_pinned_fixture_artifact()
    assert actual == expected
    assert expected["artifact_type"] == "provider_mock_response_final_safety_seal"
    assert expected["schema_version"] == "1"
    assert expected["provider_id"] == "mock"
    assert expected["source_provider_id"] == "mock"
    assert expected["final_safety_seal_status"] == "final_safety_seal_recorded"
    assert expected["final_safety_seal_state"] == "mock_pipeline_sealed"
    assert expected["seal_valid"] is True
    assert expected["seal_non_authorizing"] is True


def test_validate_success_passes_for_valid_golden() -> None:
    artifact = _load_json_fixture("artifact_valid.json")
    cleaned, error = final_safety_seal.safe_validate_provider_mock_response_final_safety_seal_data(
        artifact,
        workspace_path=None,
    )
    assert error is None
    assert cleaned == artifact


@pytest.mark.parametrize(
    "fixture_name",
    [
        "artifact_invalid_provider_id.json",
        "artifact_missing_required_field.json",
    ],
)
def test_validate_failure_diagnostics_are_stable(fixture_name: str) -> None:
    artifact, expected_error = _artifact_from_case(fixture_name)
    cleaned, error = final_safety_seal.safe_validate_provider_mock_response_final_safety_seal_data(
        artifact,
        workspace_path=None,
    )
    assert cleaned is None
    assert error == expected_error


def test_invalid_and_disabled_provider_diagnostics_are_stable() -> None:
    assert final_safety_seal.validate_provider_id("mock") == "mock"
    for provider_id in ("", "custom-openai-compatible", "openai"):
        with pytest.raises(ResearchSessionError) as exc:
            final_safety_seal.validate_provider_id(provider_id)
        assert str(exc.value) == "invalid_provider_mock_response_final_safety_seal_provider"


def test_missing_file_handling_and_exit_codes_are_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ensure_workspace(tmp_path)
    assert final_safety_seal.find_provider_mock_response_final_safety_seal_by_id(tmp_path, "missing-seal") is None

    with pytest.raises(ResearchSessionError) as exc:
        final_safety_seal.replay_provider_mock_response_final_safety_seal(tmp_path, "missing-seal")
    assert str(exc.value) == "provider_mock_response_final_safety_seal_not_found"

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-show", "missing-seal", "--json"],
    )
    assert code == 1
    assert json.loads(output) == {"ok": False, "status": "seal_not_found"}


def test_canonical_json_and_artifact_hash_are_stable() -> None:
    artifact = _load_json_fixture("artifact_valid.json")
    reference = _load_json_fixture("artifact_hash_reference.json")
    excluded = set(reference["hash_excluded_fields"])
    canonical_payload = {key: value for key, value in artifact.items() if key not in excluded}
    canonical_digest = hashlib.sha256(canonical_json_dumps(canonical_payload).encode("utf-8")).hexdigest()

    assert artifact["artifact_hash"] == reference["artifact_hash"]
    assert final_safety_seal.provider_mock_response_final_safety_seal_sha256(artifact) == reference["artifact_hash"]
    assert canonical_digest == reference["canonical_payload_sha256"]


def test_excluded_hash_fields_are_excluded_and_core_fields_are_included() -> None:
    artifact = _load_json_fixture("artifact_valid.json")
    reference = _load_json_fixture("artifact_hash_reference.json")

    volatile_change = deepcopy(artifact)
    volatile_change["artifact_hash"] = "changed"
    volatile_change["created_at"] = "2099-12-31T00:00:00+00:00"
    assert final_safety_seal.provider_mock_response_final_safety_seal_sha256(volatile_change) == (
        reference["hash_after_artifact_hash_and_created_at_change"]
    )

    core_change = deepcopy(artifact)
    core_change["broker_touched"] = True
    assert final_safety_seal.provider_mock_response_final_safety_seal_sha256(core_change) == (
        reference["hash_after_broker_touched_change"]
    )
    assert reference["hash_after_broker_touched_change"] != reference["artifact_hash"]


def test_version_and_status_fields_are_stable() -> None:
    artifact = _load_json_fixture("artifact_valid.json")
    reference = _load_json_fixture("artifact_hash_reference.json")
    assert artifact["contract_version"] == reference["contract_version"]
    assert artifact["final_safety_seal_status"] == reference["final_safety_seal_status"]
    assert artifact["final_safety_seal_state"] == reference["final_safety_seal_state"]


def test_iter_output_is_stable_against_golden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace_with_final_safety_seal(tmp_path, monkeypatch)
    items = final_safety_seal.iter_provider_mock_response_final_safety_seal_artifacts(tmp_path)
    assert len(items) == 1

    keys = [
        "provider_mock_response_final_safety_seal_id",
        "symbol",
        "provider_id",
        "model_id",
        "final_safety_seal_status",
        "final_safety_seal_state",
        "source_trust_decision_blocker_id",
        "source_run_id",
        "artifact_path",
    ]
    normalized = _normalize_dynamic_values(_project(items[0], keys), _replacement_map(context))
    assert normalized == _load_json_fixture("iter_list_json.golden")


def test_cli_show_json_and_text_outputs_are_stable_against_goldens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _workspace_with_final_safety_seal(tmp_path, monkeypatch)
    replacements = _replacement_map(context)
    seal_id = context["seal_id"]

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-show", seal_id, "--json"],
    )
    assert code == 0
    show_payload = json.loads(output)
    show_keys = [
        "artifact_hash",
        "artifact_path",
        "artifact_type",
        "broker_touched",
        "contract_version",
        "credentials_loaded",
        "final_safety_seal_scope",
        "final_safety_seal_state",
        "final_safety_seal_status",
        "live_trading_path_enabled",
        "mode",
        "mock_pipeline_complete",
        "mock_response_trusted",
        "network_enabled",
        "provider_call_allowed",
        "provider_id",
        "provider_mock_response_final_safety_seal_id",
        "provider_response_trusted",
        "schema_version",
        "seal_non_authorizing",
        "seal_valid",
        "source_provider_id",
        "source_run_id",
        "source_trust_decision_blocker_id",
        "symbol",
        "trust_decision_explicitly_blocked",
        "trust_decision_granted",
        "trust_upgrade_performed",
    ]
    normalized_show = _normalize_dynamic_values(_project(show_payload, show_keys), replacements)
    assert normalized_show == _load_json_fixture("cli_show_json.golden")

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-show", seal_id],
    )
    assert code == 0
    assert _normalize_dynamic_values(output.rstrip(), replacements) == _load_text_fixture("cli_show_text.golden")


def test_replay_summarize_and_doctor_outputs_are_stable_against_goldens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _workspace_with_final_safety_seal(tmp_path, monkeypatch)
    replacements = _replacement_map(context)
    run_id = context["run_id"]
    seal_id = context["seal_id"]

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-replay", seal_id, "--json"],
    )
    assert code == 0
    replay_payload = json.loads(output)
    replay_keys = [
        "broker_order_path_enabled",
        "broker_touched",
        "final_safety_seal_created",
        "live_trading_path_enabled",
        "match",
        "mock_pipeline_complete",
        "mock_response_trusted",
        "ok",
        "original_hash",
        "provider_call_allowed",
        "provider_mock_response_final_safety_seal_id",
        "provider_response_trusted",
        "replayed_hash",
        "seal_non_authorizing",
        "seal_valid",
        "status",
        "trust_blocker_active",
        "trust_decision_blocker_recorded",
        "trust_decision_explicitly_blocked",
        "trust_decision_granted",
        "trust_decision_present",
        "trust_decision_required",
        "trust_upgrade_performed",
    ]
    normalized_replay = _normalize_dynamic_values(_project(replay_payload, replay_keys), replacements)
    assert normalized_replay == _load_json_fixture("cli_replay_json.golden")

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-summary", run_id, "--json"],
    )
    assert code == 0
    summary_payload = json.loads(output)
    summary_keys = [
        "broker_order_path_enabled",
        "broker_touched",
        "final_safety_seal_created",
        "final_safety_seal_state",
        "final_safety_seal_status",
        "live_trading_path_enabled",
        "mock_pipeline_complete",
        "mock_response_trusted",
        "ok",
        "provider_call_allowed",
        "provider_mock_response_final_safety_seal_id",
        "provider_response_trusted",
        "run_id",
        "seal_non_authorizing",
        "seal_valid",
        "status",
        "trust_blocker_active",
        "trust_decision_explicitly_blocked",
        "trust_decision_granted",
        "trust_decision_present",
        "trust_decision_required",
        "trust_upgrade_performed",
    ]
    normalized_summary = _normalize_dynamic_values(_project(summary_payload, summary_keys), replacements)
    assert normalized_summary == _load_json_fixture("cli_summarize_json.golden")

    code, output = _run_cli(
        tmp_path,
        monkeypatch,
        capsys,
        ["research", "provider-mock-response-final-safety-seal-doctor", run_id],
    )
    assert code == 0
    assert _normalize_dynamic_values(output.rstrip(), replacements) == _load_text_fixture("doctor_output.golden")
