# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_provider_audit_pack.py
# PURPOSE: Verifies provider audit pack behavior and regression expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

"""Tests for the local-only provider audit pack command."""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.providers.provider_audit_pack import create_provider_audit_pack
from atlas_agent.providers.provider_evidence_index import inspect_provider_evidence_index
from atlas_agent.providers.provider_preflight import (
    validate_call_plan_artifact,
    verify_preflight_evidence_bundle,
)

# --- CONFIGURATION AND CONSTANTS ---

EXPECTED_FILES = [
    "call-plan.json",
    "validation-report.json",
    "manifest.json",
    "sha256sums.txt",
    "smoke-report.json",
    "evidence-index.json",
    "evidence-report.md",
    "evidence-summary.json",
    "audit-pack-manifest.json",
]


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_audit_pack_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    output_dir = tmp_path / "audit-pack"
    code = main([
        "providers",
        "audit-pack",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--max-context-chars",
        "4000",
        "--output-dir",
        str(output_dir),
    ])
    captured = capsys.readouterr()
    assert code == 0
    assert "Provider audit pack created at" in captured.out
    return output_dir


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_json(data):
    if isinstance(data, dict):
        for key, value in data.items():
            yield key, value
            yield from _walk_json(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk_json(item)


def test_audit_pack_cli_succeeds_with_valid_arguments(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    assert output_dir.is_dir()


def test_audit_pack_creates_all_expected_files(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    assert sorted(path.name for path in output_dir.iterdir() if path.is_file()) == sorted(EXPECTED_FILES)


def test_audit_pack_manifest_schema_and_stage_state(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    manifest = _read_json(output_dir / "audit-pack-manifest.json")

    assert manifest["artifact_type"] == "provider_audit_pack_manifest"
    assert manifest["valid"] is True
    assert manifest["files"] == EXPECTED_FILES
    assert all(value is True for value in manifest["stages"].values())


def test_audit_pack_safety_summary_is_closed(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    manifest = _read_json(output_dir / "audit-pack-manifest.json")

    assert manifest["manual_review_required"] is True
    assert manifest["non_authorizing"] is True
    assert all(value is False for value in manifest["safety_summary"].values())


def test_audit_pack_call_plan_and_bundle_validate(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)

    validate_call_plan_artifact(_read_json(output_dir / "call-plan.json"))
    verification = verify_preflight_evidence_bundle(output_dir)
    assert verification["valid"] is True


def test_audit_pack_evidence_index_and_summary_validate(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)

    index = inspect_provider_evidence_index(output_dir / "evidence-index.json")
    assert index["findings"] == []

    summary = _read_json(output_dir / "evidence-summary.json")
    assert summary["artifact_type"] == "provider_evidence_index_summary"
    assert summary["valid"] is True


def test_audit_pack_markdown_report_contains_reviewer_notes(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    report = (output_dir / "evidence-report.md").read_text(encoding="utf-8")

    assert "## Reviewer Notes" in report
    assert "It does not authorize provider execution." in report


def test_audit_pack_manifest_report_and_summary_paths_are_relative(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    audit_manifest = _read_json(output_dir / "audit-pack-manifest.json")
    bundle_manifest = _read_json(output_dir / "manifest.json")
    smoke_report = _read_json(output_dir / "smoke-report.json")
    index = _read_json(output_dir / "evidence-index.json")
    summary = _read_json(output_dir / "evidence-summary.json")
    report = (output_dir / "evidence-report.md").read_text(encoding="utf-8")

    for rel_path in audit_manifest["files"]:
        assert not Path(rel_path).is_absolute()
        assert Path(rel_path).name == rel_path
    for rel_path in bundle_manifest["bundle_files"]:
        assert not Path(rel_path).is_absolute()
        assert Path(rel_path).name == rel_path
    for rel_path in smoke_report["files"].values():
        assert not Path(rel_path).is_absolute()
        assert Path(rel_path).name == rel_path
    for artifact in index["artifacts"]:
        assert not Path(artifact["relative_path"]).is_absolute()
    assert index["root"] == "."
    assert summary["source_index_path"] == "evidence-index.json"
    assert str(output_dir) not in report
    assert str(tmp_path) not in report


def test_audit_pack_outputs_do_not_contain_fake_key_values(tmp_path: Path, monkeypatch, capsys) -> None:
    fake_values = {
        "ATLAS_" + "API" + "_KEY": "fake-audit-pack-value-one-123",
        "ATLAS_" + "TO" + "KEN": "fake-audit-pack-value-two-456",
    }
    for name, value in fake_values.items():
        monkeypatch.setenv(name, value)

    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    for path in output_dir.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for value in fake_values.values():
                assert value not in text


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--provider", ""),
        ("--model", "/etc/passwd"),
        ("--purpose", "api_key_marker"),
    ],
)
def test_audit_pack_invalid_provider_model_or_purpose_fails(
    tmp_path: Path,
    capsys,
    flag: str,
    value: str,
) -> None:
    args = [
        "providers",
        "audit-pack",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--output-dir",
        str(tmp_path / "invalid"),
    ]
    args[args.index(flag) + 1] = value

    code = main(args)
    captured = capsys.readouterr()
    assert code == 2
    assert "Provider audit pack creation failed:" in captured.err


@pytest.mark.parametrize("max_context_chars", ["0", "200001"])
def test_audit_pack_invalid_max_context_chars_fails(
    tmp_path: Path,
    capsys,
    max_context_chars: str,
) -> None:
    code = main([
        "providers",
        "audit-pack",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--max-context-chars",
        max_context_chars,
        "--output-dir",
        str(tmp_path / "invalid-context"),
    ])
    captured = capsys.readouterr()

    assert code == 2
    assert "Provider audit pack creation failed:" in captured.err


def test_audit_pack_does_not_include_raw_prompt_request_or_response_body(tmp_path: Path, capsys) -> None:
    output_dir = _run_audit_pack_cli(tmp_path, capsys)
    forbidden_keys = {
        "raw_prompt",
        "raw_request",
        "raw_response",
        "prompt_body",
        "request_body",
        "response_body",
    }

    for path in output_dir.glob("*.json"):
        data = _read_json(path)
        for key, value in _walk_json(data):
            assert key not in forbidden_keys
            if isinstance(value, str):
                assert value not in {"raw_prompt", "raw_request", "raw_response"}


def test_audit_pack_module_has_no_provider_sdk_or_network_imports() -> None:
    import atlas_agent.providers.provider_audit_pack as provider_audit_pack

    source = Path(provider_audit_pack.__file__).read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    banned = (
        "requests",
        "httpx",
        "urllib",
        "socket",
        "openai",
        "anthropic",
        "gemini",
        "google.genai",
        "openrouter",
    )
    for line in import_lines:
        assert not any(fragment in line for fragment in banned)


def test_audit_pack_does_not_touch_protected_boundaries(tmp_path: Path) -> None:
    with (
        patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_broker_resolver,
        patch("atlas_agent.execution.order_router.OrderRouter") as mock_order_router,
        patch("atlas_agent.risk.manager.RiskManager") as mock_risk_manager,
        patch("atlas_agent.safety.write_deadman_heartbeat") as mock_deadman,
    ):
        result = create_provider_audit_pack(
            provider_id="openrouter",
            model_id="openrouter/auto",
            purpose="research-summary",
            max_context_chars=4000,
            output_dir=tmp_path / "audit-pack",
        )

    assert result["valid"] is True
    mock_broker_resolver.assert_not_called()
    mock_order_router.assert_not_called()
    mock_risk_manager.assert_not_called()
    mock_deadman.assert_not_called()


def test_audit_pack_cli_json_mode(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "audit-pack-json"
    code = main([
        "providers",
        "audit-pack",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--output-dir",
        str(output_dir),
        "--json",
    ])
    captured = capsys.readouterr()
    envelope = json.loads(captured.out)

    assert code == 0
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers audit-pack"
    assert envelope["data"]["valid"] is True
    assert envelope["data"]["output_dir"] == str(output_dir)
    assert envelope["data"]["files"] == EXPECTED_FILES
    assert all(value is True for value in envelope["data"]["stages"].values())
