# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_provider_preflight.py
# PURPOSE: Verifies provider preflight behavior and regression expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _write_valid_call_plan(path: Path) -> dict:
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact

    artifact = generate_call_plan_artifact(
        provider_id="demo-provider",
        model_id="demo-model",
        purpose="research-summary",
    )
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def _create_valid_bundle(tmp_path: Path) -> Path:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"
    create_preflight_evidence_bundle(artifact_path, output_dir)
    return output_dir


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_bundle_hashes(bundle_dir: Path) -> None:
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    call_plan_sha = _sha256(bundle_dir / "call-plan.json")
    validation_report_sha = _sha256(bundle_dir / "validation-report.json")
    manifest["source_artifact_sha256"] = call_plan_sha
    manifest["bundle_sha256s"] = {
        "call-plan.json": call_plan_sha,
        "validation-report.json": validation_report_sha,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha = _sha256(manifest_path)
    (bundle_dir / "sha256sums.txt").write_text(
        "\n".join(
            [
                f"{call_plan_sha}  call-plan.json",
                f"{validation_report_sha}  validation-report.json",
                f"{manifest_sha}  manifest.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_provider_preflight_success(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "custom-plan.json"

    args = [
        "providers", "preflight",
        "--provider", "openrouter",
        "--model", "openrouter/auto",
        "--purpose", "research-summary",
        "--max-context-chars", "4000",
        "--output", str(output_path),
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "Generated dry-run call-plan artifact" in captured.out
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "provider_call_plan"
    assert payload["schema_version"] == 1
    assert payload["provider_id"] == "openrouter"
    assert payload["model_id"] == "openrouter/auto"
    assert payload["purpose"] == "research-summary"
    assert payload["max_context_chars"] == 4000

    # Assert safety flags are false
    flags = payload["safety_flags"]
    assert flags["provider_enabled"] is False
    assert flags["network_enabled"] is False
    assert flags["credentials_loaded"] is False
    assert flags["outbound_request_sent"] is False
    assert flags["response_received"] is False
    assert flags["broker_touched"] is False
    assert flags["live_trading_enabled"] is False
    assert flags["pending_order_created"] is False
    assert flags["order_approved"] is False
    assert flags["payload_body_stored"] is False

    # Assert no raw bodies are stored
    minimization = payload["payload_minimization_summary"]
    assert minimization["raw_prompt_body_stored"] is False
    assert minimization["raw_request_body_stored"] is False
    assert minimization["raw_response_body_stored"] is False
    assert minimization["hashes_only"] is True


def test_provider_preflight_json_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    args = [
        "providers", "preflight",
        "--provider", "anthropic",
        "--model", "claude-3",
        "--purpose", "test",
        "--json",
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers preflight"

    out_path = Path(envelope["data"]["artifact_path"])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["provider_id"] == "anthropic"


def test_provider_preflight_invalid_inputs_rejected(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    invalid_cases = [
        # Empty provider
        ["--provider", "", "--model", "test", "--purpose", "test"],
        # Too long provider (>64)
        ["--provider", "a" * 65, "--model", "test", "--purpose", "test"],
        # Control characters
        ["--provider", "test\x00", "--model", "test", "--purpose", "test"],
        # Newlines
        ["--provider", "test\n", "--model", "test", "--purpose", "test"],
        # Absolute path
        ["--provider", "test", "--model", "/etc/passwd", "--purpose", "test"],
        # Secret fragment
        ["--provider", "test", "--model", "test", "--purpose", "api_key_stuff"],
    ]

    for flags in invalid_cases:
        args = ["providers", "preflight"] + flags
        code = main(args)
        assert code == 2


def test_provider_preflight_no_api_key_leakage(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "secret-test.json"

    # Set fake API keys
    fake_keys = {
        "OPENAI_API_KEY": "fake_sk_openai_123",
        "ANTHROPIC_API_KEY": "fake_sk_ant_123",
        "OPENROUTER_API_KEY": "fake_sk_or_123",
        "MOONSHOT_API_KEY": "fake_sk_moon_123",
        "XAI_API_KEY": "fake_sk_xai_123",
        "GEMINI_API_KEY": "fake_sk_gemini_123",
    }
    for k, v in fake_keys.items():
        monkeypatch.setenv(k, v)

    args = [
        "providers", "preflight",
        "--provider", "openrouter",
        "--model", "openrouter/auto",
        "--purpose", "research",
        "--output", str(output_path),
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert output_path.exists()

    # Verify no fake keys leaked in stdout/stderr
    for val in fake_keys.values():
        assert val not in captured.out
        assert val not in captured.err

    # Verify no fake keys leaked in the generated artifact
    artifact_content = output_path.read_text(encoding="utf-8")
    for val in fake_keys.values():
        assert val not in artifact_content


def test_provider_preflight_module_imports_are_safe():
    """Verify that the module does not import provider SDKs or network libraries."""
    import ast
    from atlas_agent.providers import provider_preflight

    source = Path(provider_preflight.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_imports = {
        "openai", "anthropic", "requests", "urllib", "http", "socket", "httpx"
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split('.')[0]
                assert base not in forbidden_imports, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            base = node.module.split('.')[0] if node.module else ""
            assert base not in forbidden_imports, f"Forbidden import from: {node.module}"


def test_provider_preflight_does_not_touch_protected_boundaries():
    """Verify that the preflight command does not interact with live trading or brokers."""
    from atlas_agent.providers import provider_preflight

    with patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_resolver:
        provider_preflight.generate_call_plan_artifact(
            provider_id="test",
            model_id="test",
            purpose="test",
        )
    mock_resolver.assert_not_called()


def test_validate_valid_artifact():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    # Should not raise
    validate_call_plan_artifact(artifact)

def test_validate_missing_or_true_safety_flag():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact, PreflightValidationError
    import pytest
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    artifact["safety_flags"]["provider_enabled"] = True
    with pytest.raises(PreflightValidationError, match="Safety flag provider_enabled must be false"):
        validate_call_plan_artifact(artifact)

def test_validate_raw_body_field():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact, PreflightValidationError
    import pytest
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    artifact["payload_minimization_summary"]["raw_prompt_body_stored"] = True
    with pytest.raises(PreflightValidationError, match="raw_prompt_body_stored must be false"):
        validate_call_plan_artifact(artifact)

def test_validate_secret_looking_value():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact, PreflightValidationError
    import pytest
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    artifact["extra_notes"] = "My super password is password123"
    with pytest.raises(PreflightValidationError, match="Artifact contains forbidden secret-like fragment in string value"):
        validate_call_plan_artifact(artifact)

def test_validate_absolute_path():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact, PreflightValidationError
    import pytest
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    artifact["path"] = "/var/secret/path"
    with pytest.raises(PreflightValidationError, match="Artifact contains forbidden absolute path in string value"):
        validate_call_plan_artifact(artifact)

def test_validate_forbidden_field():
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact, validate_call_plan_artifact, PreflightValidationError
    import pytest
    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    artifact["api_key"] = "test"
    with pytest.raises(PreflightValidationError, match="Artifact contains forbidden field: api_key"):
        validate_call_plan_artifact(artifact)

def test_cli_validate_preflight(tmp_path):
    from atlas_agent.cli import main
    from atlas_agent.providers.provider_preflight import generate_call_plan_artifact
    import json

    artifact = generate_call_plan_artifact(
        provider_id="openrouter", model_id="openrouter/auto", purpose="research-summary"
    )
    p = tmp_path / "valid.json"
    p.write_text(json.dumps(artifact))

    # Needs a mock of sys.argv. Test via subprocess to be safe
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "providers", "validate-preflight", str(p)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Artifact is valid and safe." in result.stdout

def test_cli_validate_preflight_invalid(tmp_path):
    import json
    p = tmp_path / "invalid.json"
    p.write_text(json.dumps({"artifact_type": "wrong"}))

    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "providers", "validate-preflight", str(p)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Validation failed:" in result.stderr

def test_cli_validate_preflight_malformed_json(tmp_path):
    p = tmp_path / "malformed.json"
    p.write_text("{bad json")

    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "providers", "validate-preflight", str(p)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Invalid JSON:" in result.stderr


def test_preflight_bundle_valid_artifact_creates_expected_files(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    result = create_preflight_evidence_bundle(artifact_path, output_dir)

    assert result == {
        "bundle_dir": str(output_dir),
        "files": [
            "call-plan.json",
            "validation-report.json",
            "manifest.json",
            "sha256sums.txt",
        ],
        "valid": True,
    }
    for name in result["files"]:
        assert (output_dir / name).exists()
    assert (output_dir / "call-plan.json").read_bytes() == artifact_path.read_bytes()


def test_preflight_bundle_validation_report_is_valid(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    create_preflight_evidence_bundle(artifact_path, output_dir)
    report = json.loads((output_dir / "validation-report.json").read_text(encoding="utf-8"))

    assert report["artifact_type"] == "provider_preflight_validation_report"
    assert report["schema_version"] == 1
    assert report["valid"] is True
    assert report["source_artifact"] == "call-plan.json"
    assert all(value is True for value in report["checks"].values())
    assert report["provider_call_made"] is False
    assert report["network_used"] is False
    assert report["credentials_loaded"] is False
    assert report["broker_touched"] is False
    assert report["live_trading_enabled"] is False


def test_preflight_bundle_manifest_safety_summary_is_closed(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    create_preflight_evidence_bundle(artifact_path, output_dir)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["artifact_type"] == "provider_preflight_evidence_bundle_manifest"
    assert manifest["schema_version"] == 1
    assert manifest["bundle_files"] == [
        "call-plan.json",
        "validation-report.json",
        "manifest.json",
        "sha256sums.txt",
    ]
    assert set(manifest["bundle_sha256s"]) == {"call-plan.json", "validation-report.json"}
    assert all(value is False for value in manifest["safety_summary"].values())
    assert manifest["manual_review_required"] is True


def test_preflight_bundle_sha256sums_uses_relative_paths_only(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    create_preflight_evidence_bundle(artifact_path, output_dir)
    lines = (output_dir / "sha256sums.txt").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 3
    assert [line.split("  ", 1)[1] for line in lines] == [
        "call-plan.json",
        "validation-report.json",
        "manifest.json",
    ]
    for line in lines:
        digest, rel_path = line.split("  ", 1)
        assert len(digest) == 64
        assert not Path(rel_path).is_absolute()
        assert "/" not in rel_path
        assert "\\" not in rel_path


def test_preflight_bundle_invalid_artifact_fails_without_completed_bundle(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightValidationError,
        create_preflight_evidence_bundle,
    )

    artifact_path = tmp_path / "call-plan-source.json"
    artifact = _write_valid_call_plan(artifact_path)
    artifact["safety_flags"]["network_enabled"] = True
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    output_dir = tmp_path / "bundle"

    with pytest.raises(PreflightValidationError):
        create_preflight_evidence_bundle(artifact_path, output_dir)

    assert not output_dir.exists()


def test_preflight_bundle_malformed_json_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "malformed.json"
    artifact_path.write_text("{bad json", encoding="utf-8")
    output_dir = tmp_path / "bundle"

    with pytest.raises(json.JSONDecodeError):
        create_preflight_evidence_bundle(artifact_path, output_dir)

    assert not output_dir.exists()


def test_preflight_bundle_secret_looking_value_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightValidationError,
        create_preflight_evidence_bundle,
    )

    artifact_path = tmp_path / "call-plan-source.json"
    artifact = _write_valid_call_plan(artifact_path)
    artifact["extra"] = "contains password marker"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(PreflightValidationError):
        create_preflight_evidence_bundle(artifact_path, tmp_path / "bundle")


def test_preflight_bundle_absolute_path_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightValidationError,
        create_preflight_evidence_bundle,
    )

    artifact_path = tmp_path / "call-plan-source.json"
    artifact = _write_valid_call_plan(artifact_path)
    artifact["extra"] = "/var/tmp/provider-payload.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(PreflightValidationError):
        create_preflight_evidence_bundle(artifact_path, tmp_path / "bundle")


def test_cli_bundle_preflight_succeeds_for_valid_artifact(tmp_path: Path, capsys) -> None:
    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    code = main([
        "providers",
        "bundle-preflight",
        str(artifact_path),
        "--output-dir",
        str(output_dir),
        "--json",
    ])
    captured = capsys.readouterr()

    assert code == 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers bundle-preflight"
    assert envelope["data"]["bundle_dir"] == str(output_dir)
    assert envelope["data"]["valid"] is True
    assert (output_dir / "manifest.json").exists()


def test_cli_bundle_preflight_does_not_load_config_or_credentials(tmp_path: Path, capsys) -> None:
    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)
    output_dir = tmp_path / "bundle"

    with patch("atlas_agent.cli.AtlasConfig.from_env") as mock_from_env:
        code = main([
            "providers",
            "bundle-preflight",
            str(artifact_path),
            "--output-dir",
            str(output_dir),
        ])

    captured = capsys.readouterr()

    assert code == 0
    assert "Provider preflight evidence bundle created at" in captured.out
    mock_from_env.assert_not_called()


def test_cli_bundle_preflight_fails_for_invalid_artifact(tmp_path: Path, capsys) -> None:
    artifact_path = tmp_path / "invalid.json"
    artifact_path.write_text(json.dumps({"artifact_type": "wrong"}), encoding="utf-8")
    output_dir = tmp_path / "bundle"

    code = main([
        "providers",
        "bundle-preflight",
        str(artifact_path),
        "--output-dir",
        str(output_dir),
        "--json",
    ])
    captured = capsys.readouterr()

    assert code != 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "preflight_validation_error"
    assert not output_dir.exists()


def test_preflight_bundle_does_not_touch_protected_boundaries(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import create_preflight_evidence_bundle

    artifact_path = tmp_path / "call-plan-source.json"
    _write_valid_call_plan(artifact_path)

    with (
        patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_broker_resolver,
        patch("atlas_agent.execution.order_router.OrderRouter") as mock_order_router,
        patch("atlas_agent.risk.manager.RiskManager") as mock_risk_manager,
        patch("atlas_agent.safety.write_deadman_heartbeat") as mock_deadman,
    ):
        create_preflight_evidence_bundle(artifact_path, tmp_path / "bundle")

    mock_broker_resolver.assert_not_called()
    mock_order_router.assert_not_called()
    mock_risk_manager.assert_not_called()
    mock_deadman.assert_not_called()


def test_verify_preflight_bundle_valid_bundle_passes(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import verify_preflight_evidence_bundle

    bundle_dir = _create_valid_bundle(tmp_path)

    result = verify_preflight_evidence_bundle(bundle_dir)

    assert result["artifact_type"] == "provider_preflight_bundle_verification_report"
    assert result["schema_version"] == 1
    assert result["valid"] is True
    assert result["verified_files"] == [
        "call-plan.json",
        "validation-report.json",
        "manifest.json",
        "sha256sums.txt",
    ]
    assert all(value is True for value in result["checks"].values())
    assert result["provider_call_made"] is False
    assert result["network_used"] is False
    assert result["credentials_loaded"] is False
    assert result["broker_touched"] is False
    assert result["live_trading_enabled"] is False


def test_verify_preflight_bundle_missing_call_plan_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    (bundle_dir / "call-plan.json").unlink()

    with pytest.raises(PreflightBundleVerificationError, match="Required bundle file missing"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_tampered_call_plan_hash_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    call_plan = json.loads((bundle_dir / "call-plan.json").read_text(encoding="utf-8"))
    call_plan["purpose"] = "tampered-purpose"
    (bundle_dir / "call-plan.json").write_text(json.dumps(call_plan), encoding="utf-8")

    with pytest.raises(PreflightBundleVerificationError, match="call-plan.json hash does not match"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_tampered_validation_report_hash_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    (bundle_dir / "validation-report.json").write_text(
        (bundle_dir / "validation-report.json").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PreflightBundleVerificationError, match="validation-report.json hash does not match"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_absolute_path_in_sha256sums_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    call_plan_sha = _sha256(bundle_dir / "call-plan.json")
    (bundle_dir / "sha256sums.txt").write_text(
        f"{call_plan_sha}  /tmp/call-plan.json\n",
        encoding="utf-8",
    )

    with pytest.raises(PreflightBundleVerificationError, match="absolute path"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_validation_report_false_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["valid"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_bundle_hashes(bundle_dir)

    with pytest.raises(PreflightBundleVerificationError, match="valid must be true"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_unsafe_call_plan_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    call_plan_path = bundle_dir / "call-plan.json"
    call_plan = json.loads(call_plan_path.read_text(encoding="utf-8"))
    call_plan["safety_flags"]["broker_touched"] = True
    call_plan_path.write_text(json.dumps(call_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_bundle_hashes(bundle_dir)

    with pytest.raises(PreflightBundleVerificationError, match="call-plan.json validation failed"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_verify_preflight_bundle_extra_script_file_fails(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    bundle_dir = _create_valid_bundle(tmp_path)
    (bundle_dir / "extra.sh").write_text("echo no\n", encoding="utf-8")

    with pytest.raises(PreflightBundleVerificationError, match="Extra executable or script file"):
        verify_preflight_evidence_bundle(bundle_dir)


def test_cli_verify_preflight_bundle_succeeds_for_valid_bundle(tmp_path: Path, capsys) -> None:
    bundle_dir = _create_valid_bundle(tmp_path)

    code = main(["providers", "verify-preflight-bundle", str(bundle_dir)])
    captured = capsys.readouterr()

    assert code == 0
    assert "Provider preflight evidence bundle is valid." in captured.out


def test_cli_verify_preflight_bundle_fails_for_invalid_bundle(tmp_path: Path, capsys) -> None:
    bundle_dir = _create_valid_bundle(tmp_path)
    (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")

    code = main(["providers", "verify-preflight-bundle", str(bundle_dir)])
    captured = capsys.readouterr()

    assert code == 1
    assert "Provider preflight evidence bundle verification failed:" in captured.err


def test_cli_verify_preflight_bundle_json_mode(tmp_path: Path, capsys) -> None:
    bundle_dir = _create_valid_bundle(tmp_path)

    code = main(["providers", "verify-preflight-bundle", str(bundle_dir), "--json"])
    captured = capsys.readouterr()

    assert code == 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers verify-preflight-bundle"
    assert envelope["data"]["valid"] is True
    assert envelope["data"]["artifact_type"] == "provider_preflight_bundle_verification_report"


def test_cli_verify_preflight_bundle_does_not_load_config_or_credentials(tmp_path: Path, capsys) -> None:
    bundle_dir = _create_valid_bundle(tmp_path)

    with patch("atlas_agent.cli.AtlasConfig.from_env") as mock_from_env:
        code = main(["providers", "verify-preflight-bundle", str(bundle_dir)])

    captured = capsys.readouterr()

    assert code == 0
    assert "Provider preflight evidence bundle is valid." in captured.out
    mock_from_env.assert_not_called()


def test_verify_preflight_bundle_does_not_touch_protected_boundaries(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import verify_preflight_evidence_bundle

    bundle_dir = _create_valid_bundle(tmp_path)

    with (
        patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_broker_resolver,
        patch("atlas_agent.execution.order_router.OrderRouter") as mock_order_router,
        patch("atlas_agent.risk.manager.RiskManager") as mock_risk_manager,
        patch("atlas_agent.safety.write_deadman_heartbeat") as mock_deadman,
    ):
        verify_preflight_evidence_bundle(bundle_dir)

    mock_broker_resolver.assert_not_called()
    mock_order_router.assert_not_called()
    mock_risk_manager.assert_not_called()
    mock_deadman.assert_not_called()


def test_cli_smoke_preflight_chain_succeeds_and_creates_expected_files(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from atlas_agent.providers.provider_preflight import (
        validate_call_plan_artifact,
        verify_preflight_evidence_bundle,
    )

    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "smoke"

    code = main([
        "providers",
        "smoke-preflight-chain",
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
    assert "Provider preflight smoke chain completed successfully at" in captured.out

    expected_files = {
        "call-plan.json",
        "validation-report.json",
        "manifest.json",
        "sha256sums.txt",
        "smoke-report.json",
    }
    assert {path.name for path in output_dir.iterdir() if path.is_file()} == expected_files

    report = json.loads((output_dir / "smoke-report.json").read_text(encoding="utf-8"))
    assert report["artifact_type"] == "provider_preflight_smoke_report"
    assert report["valid"] is True
    assert all(value is True for value in report["stages"].values())
    assert all(value is False for value in report["safety_summary"].values())
    assert report["manual_review_required"] is True

    for rel_path in report["files"].values():
        assert not Path(rel_path).is_absolute()
        assert rel_path == Path(rel_path).name

    report_text = (output_dir / "smoke-report.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in report_text

    call_plan = json.loads((output_dir / "call-plan.json").read_text(encoding="utf-8"))
    validate_call_plan_artifact(call_plan)
    verification = verify_preflight_evidence_bundle(output_dir)
    assert verification["valid"] is True


def test_cli_smoke_preflight_chain_json_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "smoke-json"

    code = main([
        "providers",
        "smoke-preflight-chain",
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

    assert code == 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers smoke-preflight-chain"
    assert envelope["data"]["valid"] is True
    assert envelope["data"]["output_dir"] == str(output_dir)
    assert all(value is True for value in envelope["data"]["stages"].values())


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--provider", ""),
        ("--model", "/etc/passwd"),
        ("--purpose", "api_key_marker"),
    ],
)
def test_cli_smoke_preflight_chain_invalid_strings_fail(
    tmp_path: Path,
    monkeypatch,
    capsys,
    flag: str,
    value: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    args = [
        "providers",
        "smoke-preflight-chain",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--output-dir",
        str(tmp_path / "smoke-invalid"),
    ]
    args[args.index(flag) + 1] = value

    code = main(args)
    captured = capsys.readouterr()

    assert code == 2
    assert "Provider preflight smoke chain failed:" in captured.err


@pytest.mark.parametrize("max_context_chars", ["0", "200001"])
def test_cli_smoke_preflight_chain_invalid_max_context_chars_fail(
    tmp_path: Path,
    monkeypatch,
    capsys,
    max_context_chars: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    code = main([
        "providers",
        "smoke-preflight-chain",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--max-context-chars",
        max_context_chars,
        "--output-dir",
        str(tmp_path / "smoke-invalid-context"),
    ])
    captured = capsys.readouterr()

    assert code == 2
    assert "Provider preflight smoke chain failed:" in captured.err


def test_cli_smoke_preflight_chain_does_not_require_api_keys(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_" + "API" + "_KEY", raising=False)

    with patch("atlas_agent.cli.AtlasConfig.from_env") as mock_from_env:
        code = main([
            "providers",
            "smoke-preflight-chain",
            "--provider",
            "openrouter",
            "--model",
            "openrouter/auto",
            "--purpose",
            "research-summary",
            "--output-dir",
            str(tmp_path / "smoke-no-keys"),
        ])

    captured = capsys.readouterr()

    assert code == 0
    assert "Provider preflight smoke chain completed successfully at" in captured.out
    mock_from_env.assert_not_called()


def test_cli_smoke_preflight_chain_fake_api_key_values_do_not_leak(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_values = {
        "OPENROUTER_" + "API" + "_KEY": "fake_smoke_value_one_123",
        "OPENAI_" + "API" + "_KEY": "fake_smoke_value_two_456",
    }
    for name, value in fake_values.items():
        monkeypatch.setenv(name, value)

    output_dir = tmp_path / "smoke-fake-keys"
    code = main([
        "providers",
        "smoke-preflight-chain",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research-summary",
        "--output-dir",
        str(output_dir),
    ])
    captured = capsys.readouterr()

    assert code == 0
    for value in fake_values.values():
        assert value not in captured.out
        assert value not in captured.err
        for path in output_dir.iterdir():
            if path.is_file():
                assert value not in path.read_text(encoding="utf-8")


def test_preflight_smoke_chain_does_not_touch_protected_boundaries(tmp_path: Path) -> None:
    from atlas_agent.providers.provider_preflight import run_preflight_smoke_chain

    with (
        patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_broker_resolver,
        patch("atlas_agent.execution.order_router.OrderRouter") as mock_order_router,
        patch("atlas_agent.risk.manager.RiskManager") as mock_risk_manager,
        patch("atlas_agent.safety.write_deadman_heartbeat") as mock_deadman,
    ):
        result = run_preflight_smoke_chain(
            provider_id="openrouter",
            model_id="openrouter/auto",
            purpose="research-summary",
            max_context_chars=4000,
            output_dir=tmp_path / "smoke",
        )

    assert result["valid"] is True
    mock_broker_resolver.assert_not_called()
    mock_order_router.assert_not_called()
    mock_risk_manager.assert_not_called()
    mock_deadman.assert_not_called()
