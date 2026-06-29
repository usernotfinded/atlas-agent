from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.runtime_readiness_envelope_cli import (
    _UNSAFE_FLAGS,
    build_parser,
    main,
)


_AS_OF = "2026-06-24T10:00:00Z"


def _write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _make_quality_gate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
    }
    data.update(overrides)
    return data


def _make_shadow_comparison(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "shadow_live_comparison",
        "schema_version": "shadow-live-comparison.v1",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "status": "matched",
        "freshness_assessment": {"snapshot_age_seconds": 0},
        "blockers": [],
    }
    data.update(overrides)
    return data


def _make_submit_conformance(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_conformance",
        "schema_version": "gated-submit-conformance.v1",
        "candidate": "CAND-006",
        "mode": "simulated_only",
        "run_id": "run-123",
        "symbol": "AAPL",
        "status": "dry_run_recorded",
        "as_of": _AS_OF,
        "safety_assertions": {
            "no_live_submit": True,
            "no_broker_called": True,
            "no_provider_called": True,
            "no_credentials_loaded": True,
        },
        "dry_run_request": {
            "transmission": {
                "allowed": False,
                "broker_adapter": None,
                "provider": None,
            }
        },
        "blockers": [],
    }
    data.update(overrides)
    return data


def _make_runtime_envelope(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "runtime_readiness_envelope_fixture",
        "schema_version": "runtime-readiness-envelope-fixture.v1",
        "fixture_mode": "simulated/static",
        "run_id": "run-123",
        "symbol": "AAPL",
        "allowed_modes": ["paper", "shadow_live_readonly", "simulated"],
        "forbidden_modes": ["live", "live_submit"],
        "live_submit_enabled": False,
        "require_human_approval": True,
        "require_kill_switch_inactive": True,
        "require_risk_gate": True,
        "require_audit_recording": True,
        "require_broker_capability_manifest": True,
        "max_order_notional": "1000.00",
        "max_symbol_exposure": "5000.00",
        "max_daily_orders": 10,
        "max_daily_notional": "10000.00",
        "supported_order_types": ["market", "limit"],
        "supported_time_in_force": ["day"],
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_broker_capabilities(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "broker_capability_manifest_fixture",
        "schema_version": "broker-capability-manifest-fixture.v1",
        "broker_label": "local-test-broker",
        "capabilities": {"paper_trading": True},
        "disabled_capabilities": [],
        "unsupported_order_types": [],
        "sandbox_only": True,
        "live_api_contact_allowed": False,
        "credentials_present": False,
        "endpoint_present": False,
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_operator_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "operator_policy_fixture",
        "schema_version": "operator-policy-fixture.v1",
        "requires_manual_review": True,
        "requires_explicit_approval": True,
        "approval_scope": "simulated_only",
        "unattended_operation_allowed": False,
        "max_runtime_window_seconds": 3600,
        "max_actions_per_session": 10,
        "allowed_symbols": ["AAPL"],
        "blocked_symbols": [],
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_kill_switch_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "kill_switch_policy_fixture",
        "schema_version": "kill-switch-policy-fixture.v1",
        "kill_switch_required": True,
        "default_state_on_missing_runtime": "blocked",
        "default_state_on_unknown_runtime": "blocked",
        "operator_override_allowed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_audit_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "audit_policy_fixture",
        "schema_version": "audit-policy-fixture.v1",
        "audit_required": True,
        "append_only_required": True,
        "hash_chain_required": True,
        "local_artifact_recording_required": True,
        "live_audit_chain_claimed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_fixtures(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for label, maker in (
        ("quality_gate", _make_quality_gate),
        ("shadow_comparison", _make_shadow_comparison),
        ("submit_conformance", _make_submit_conformance),
        ("runtime_envelope", _make_runtime_envelope),
        ("broker_capabilities", _make_broker_capabilities),
        ("operator_policy", _make_operator_policy),
        ("kill_switch_policy", _make_kill_switch_policy),
        ("audit_policy", _make_audit_policy),
    ):
        paths[label] = tmp_path / f"{label}.json"
        _write_fixture(paths[label], maker())
    return paths


def _cli_args(paths: dict[str, Path], output_dir: Path, extra: list[str] | None = None) -> list[str]:
    args = [
        "--quality-gate", str(paths["quality_gate"]),
        "--shadow-comparison", str(paths["shadow_comparison"]),
        "--submit-conformance", str(paths["submit_conformance"]),
        "--runtime-envelope", str(paths["runtime_envelope"]),
        "--broker-capabilities", str(paths["broker_capabilities"]),
        "--operator-policy", str(paths["operator_policy"]),
        "--kill-switch-policy", str(paths["kill_switch_policy"]),
        "--audit-policy", str(paths["audit_policy"]),
        "--output-dir", str(output_dir),
        "--as-of", _AS_OF,
    ]
    if extra:
        args.extend(extra)
    return args


def _run_and_capture_code(func: Any, *args: Any, **kwargs: Any) -> int:
    try:
        return func(*args, **kwargs)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def test_cli_help_contains_disclaimer() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "simulated only" in help_text.lower()
    assert "does not submit orders" in help_text.lower()


def test_help_returns_zero() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0


def test_json_emits_valid_readiness_envelope_recorded(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    import io
    from unittest.mock import patch

    with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
        ret = main(_cli_args(paths, output_dir, ["--json"]))
    assert ret == 0
    data = json.loads(fake_stdout.getvalue())
    assert data["status"] == "readiness_envelope_recorded"
    assert data["exit_code"] == 0


def test_missing_required_flag_returns_two(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    args = _cli_args(paths, tmp_path / "out")
    # Remove --as-of and its value to trigger a missing-required-flag error.
    idx = args.index("--as-of")
    args = args[:idx] + args[idx + 2 :]
    code = _run_and_capture_code(main, args)
    assert code == 2


@pytest.mark.parametrize("flag", sorted(_UNSAFE_FLAGS))
def test_unsafe_flag_rejected(flag: str) -> None:
    code = _run_and_capture_code(main, [flag])
    assert code == 2


def test_valid_fixture_set_writes_artifacts_and_exits_zero(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 0
    assert (output_dir / "runtime-readiness-envelope.json").is_file()
    assert (output_dir / "runtime-readiness-envelope-report.md").is_file()


def test_unknown_fixture_fields_rejected(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    runtime_envelope = _make_runtime_envelope(extra_field="x")
    _write_fixture(paths["runtime_envelope"], runtime_envelope)
    output_dir = tmp_path / "out"
    import io
    from unittest.mock import patch

    with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
        ret = main(_cli_args(paths, output_dir, ["--json"]))
    assert ret == 2
    data = json.loads(fake_stdout.getvalue())
    assert data["status"] == "not_evaluated"


def test_output_contains_no_absolute_temp_paths(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    main(_cli_args(paths, output_dir))
    text = (output_dir / "runtime-readiness-envelope-report.md").read_text()
    assert str(tmp_path) not in text
    assert "/Users/" not in text


def test_bootstrap_delegates_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli_bootstrap", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_bootstrap_delegates_validate() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli_bootstrap", "validate"],
        capture_output=True,
        text=True,
    )
    # validate may fail if no workspace, but it must route through legacy CLI.
    assert "readiness-envelope" not in result.stdout


def test_bootstrap_delegates_unknown_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli_bootstrap", "agent", "readiness-envelope-extra", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "unrecognized arguments" in combined or "invalid choice" in combined
