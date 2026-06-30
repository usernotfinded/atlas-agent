from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.gated_submit_conformance_cli import (
    _UNSAFE_FLAGS,
    build_parser,
    main,
)


_AS_OF = "2026-06-24T10:00:00Z"


def _make_order_intent(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_order_intent",
        "schema_version": "gated-submit-order-intent.v1",
        "intent_kind": "hypothetical",
        "intent_id": "intent-001",
        "run_id": "run-123",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": "1",
        "order_type": "limit",
        "limit_price": "100",
        "time_in_force": "day",
        "created_at": "2026-06-24T09:00:00Z",
    }
    data.update(overrides)
    return data


def _make_kill_switch(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_kill_switch_fixture",
        "schema_version": "gated-submit-kill-switch.v1",
        "fixture_mode": "simulated",
        "scope": "conformance_rehearsal_only",
        "state": "inactive",
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
    }
    data.update(overrides)
    return data


def _make_risk_envelope(intent_fingerprint: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_risk_envelope_fixture",
        "schema_version": "gated-submit-risk-envelope.v1",
        "fixture_mode": "simulated",
        "represents": "RiskManager_evaluation",
        "evaluation_mode": "paper",
        "intent_fingerprint": intent_fingerprint,
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
        "decision": "allowed",
        "evaluated_price": "100",
        "evaluated_notional": "100",
        "checks": [{"rule": "max_position_size", "passed": True}],
        "violations": [],
        "limits_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "portfolio_snapshot_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    data.update(overrides)
    return data


def _make_approval(
    intent_fingerprint: str, risk_fingerprint: str, **overrides: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_approval_fixture",
        "schema_version": "gated-submit-approval-fixture.v1",
        "fixture_mode": "simulated",
        "scope": "conformance_rehearsal_only",
        "fixture_id": "approval-001",
        "intent_fingerprint": intent_fingerprint,
        "risk_envelope_fingerprint": risk_fingerprint,
        "decision": "approved",
        "actor_label": "simulated-reviewer",
        "approved_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
    }
    data.update(overrides)
    return data


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


def _write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _make_fixtures(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["quality_gate"] = tmp_path / "quality_gate.json"
    _write_fixture(paths["quality_gate"], _make_quality_gate())

    paths["shadow_comparison"] = tmp_path / "shadow_comparison.json"
    _write_fixture(paths["shadow_comparison"], _make_shadow_comparison())

    paths["order_intent"] = tmp_path / "order_intent.json"
    _write_fixture(paths["order_intent"], _make_order_intent())
    order_fp = fingerprint_json(_make_order_intent())

    paths["kill_switch"] = tmp_path / "kill_switch.json"
    _write_fixture(paths["kill_switch"], _make_kill_switch())

    paths["risk_envelope"] = tmp_path / "risk_envelope.json"
    _write_fixture(paths["risk_envelope"], _make_risk_envelope(order_fp))
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))

    paths["approval"] = tmp_path / "approval.json"
    _write_fixture(paths["approval"], _make_approval(order_fp, risk_fp))

    return paths


def fingerprint_json(value: Any) -> str:
    import hashlib

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _cli_args(paths: dict[str, Path], output_dir: Path, extra: list[str] | None = None) -> list[str]:
    args = [
        "--quality-gate",
        str(paths["quality_gate"]),
        "--shadow-comparison",
        str(paths["shadow_comparison"]),
        "--order-intent",
        str(paths["order_intent"]),
        "--kill-switch",
        str(paths["kill_switch"]),
        "--risk-envelope",
        str(paths["risk_envelope"]),
        "--approval",
        str(paths["approval"]),
        "--output-dir",
        str(output_dir),
        "--as-of",
        _AS_OF,
    ]
    if extra:
        args.extend(extra)
    return args


def test_help_returns_zero() -> None:
    parser = build_parser()
    # argparse raises SystemExit(0) for --help.
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0


def test_help_text_contains_simulated_only_disclaimer() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli_bootstrap", "agent", "submit-conformance", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "simulated" in combined.lower()
    assert "does not submit orders" in combined.lower()
    assert "does not call brokers" in combined.lower() or "broker" in combined.lower()
    assert "does not load credentials" in combined.lower()
    assert "not live readiness" in combined.lower() or "live readiness" in combined.lower()


def _run_and_capture_code(func: Any, *args: Any, **kwargs: Any) -> int:
    try:
        return func(*args, **kwargs)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


@pytest.mark.parametrize("flag", sorted(_UNSAFE_FLAGS))
def test_unsafe_flag_rejected(flag: str) -> None:
    code = _run_and_capture_code(main, [flag])
    assert code == 2


@pytest.mark.parametrize(
    "flag",
    ["--mode=live", "--live=true", "--broker=alpaca", "--api-key=sk-xxx"],
)
def test_unsafe_flag_equals_syntax_rejected(flag: str) -> None:
    code = _run_and_capture_code(main, [flag])
    assert code == 2
    # Error message should indicate the flag is unsupported for simulated-only conformance.
    import io
    from unittest.mock import patch

    with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
        _run_and_capture_code(main, [flag])
    err = fake_stderr.getvalue().lower()
    assert "unsupported" in err or "unsafe" in err or "simulated" in err


def test_safe_flag_equals_syntax_allowed(tmp_path: Path) -> None:
    """A safe required flag using ``=`` syntax must not be confused with unsafe flags."""
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    args = _cli_args(paths, output_dir)
    idx = args.index("--as-of")
    args[idx] = "--as-of=2026-06-24T10:00:00Z"
    args.pop(idx + 1)
    ret = main(args)
    assert ret == 0


def test_unsafe_flag_message_mentions_simulated_only() -> None:
    import io
    from unittest.mock import patch

    with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
        code = _run_and_capture_code(main, ["--live"])
    assert code == 2
    err = fake_stderr.getvalue().lower()
    assert "unsupported" in err or "unsafe" in err
    assert "simulated" in err


def test_policy_flag_rejected() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--policy", "x.json"])
    assert exc_info.value.code != 0


def test_valid_fixture_set_exits_zero(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 0
    assert (output_dir / "gated-submit-conformance.json").exists()
    assert (output_dir / "gated-submit-conformance-report.md").exists()


def test_json_output_emits_valid_dry_run_recorded(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    import io
    from unittest.mock import patch

    with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
        ret = main(_cli_args(paths, output_dir, ["--json"]))
    assert ret == 0
    data = json.loads(fake_stdout.getvalue())
    assert data["status"] == "dry_run_recorded"
    assert data["exit_code"] == 0


def test_missing_quality_gate_exits_not_evaluated(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    paths["quality_gate"].unlink()
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2


def test_quality_gate_blocked_exits_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    _write_fixture(paths["quality_gate"], _make_quality_gate(quality_state="blocked"))
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    json_path = output_dir / "gated-submit-conformance.json"
    data = json.loads(json_path.read_text())
    assert data["status"] == "blocked"


def test_unknown_fixture_field_rejected(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order = _make_order_intent(extra_field="x")
    _write_fixture(paths["order_intent"], order)
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "not_evaluated"


def test_cand004_run_id_mismatch_blocks(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    _write_fixture(paths["quality_gate"], _make_quality_gate(run_id="run-999"))
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "blocked"
    assert any("run_id mismatch" in b for b in data["blockers"])


def test_cand004_symbol_mismatch_blocks(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    _write_fixture(paths["quality_gate"], _make_quality_gate(symbol="TSLA"))
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "blocked"
    assert any("symbol mismatch" in b for b in data["blockers"])


def test_cand005_minor_divergence_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    _write_fixture(
        paths["shadow_comparison"], _make_shadow_comparison(status="minor_divergence")
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "shadow_divergence_blocked"


def test_kill_switch_active_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    _write_fixture(paths["kill_switch"], _make_kill_switch(state="active"))
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "kill_switch_blocked"


def test_risk_requires_approval_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    _write_fixture(
        paths["risk_envelope"],
        _make_risk_envelope(order_fp, decision="requires_approval"),
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "risk_blocked"


def test_risk_allowed_with_empty_checks_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    _write_fixture(
        paths["risk_envelope"],
        _make_risk_envelope(order_fp, checks=[]),
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "risk_blocked"


def test_risk_failed_check_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    _write_fixture(
        paths["risk_envelope"],
        _make_risk_envelope(
            order_fp,
            checks=[{"rule": "max_position_size", "passed": False}],
        ),
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "risk_blocked"


def test_approval_denied_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))
    _write_fixture(
        paths["approval"], _make_approval(order_fp, risk_fp, decision="denied")
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "approval_required"


def test_approval_expired_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))
    _write_fixture(
        paths["approval"],
        _make_approval(order_fp, risk_fp, expires_at="2026-06-24T09:30:00Z"),
    )
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2
    data = json.loads((output_dir / "gated-submit-conformance.json").read_text())
    assert data["status"] == "approval_required"


def test_approval_missing_blocked(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    paths["approval"].unlink()
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 2


def test_actor_label_optional(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    order_fp = fingerprint_json(_make_order_intent())
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))
    approval = _make_approval(order_fp, risk_fp)
    approval.pop("actor_label")
    _write_fixture(paths["approval"], approval)
    output_dir = tmp_path / "out"
    ret = main(_cli_args(paths, output_dir))
    assert ret == 0


def test_output_contains_no_absolute_paths_or_secrets(tmp_path: Path) -> None:
    paths = _make_fixtures(tmp_path)
    output_dir = tmp_path / "out"
    main(_cli_args(paths, output_dir))
    text = (output_dir / "gated-submit-conformance-report.md").read_text()
    assert str(tmp_path) not in text
    assert "/Users/" not in text
    assert "api_key" not in text.lower()


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
    assert "submit-conformance" not in result.stdout


def test_bootstrap_delegates_workspace_variant() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atlas_agent.cli_bootstrap",
            "--workspace",
            "/tmp/nonexistent-ws-cand006",
            "agent",
            "submit-conformance",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    # The legacy CLI receives the full argv unchanged and now also registers the
    # CAND-006 subcommand, so it prints the simulated-only help.
    assert result.returncode == 0, result.stdout + result.stderr
    assert "simulated" in (result.stdout + result.stderr).lower()


def test_bootstrap_delegates_unknown_subcommand() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atlas_agent.cli_bootstrap",
            "agent",
            "submit-conformance-extra",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in (result.stdout + result.stderr).lower() or "invalid choice" in (result.stdout + result.stderr).lower()
