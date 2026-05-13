from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.events import EventLogger, generate_run_id


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def _assert_json_envelope(output: str) -> dict:
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    assert parsed["ok"] is True
    assert isinstance(parsed["command"], str)
    assert isinstance(parsed["generated_at"], str)
    generated_at = datetime.fromisoformat(parsed["generated_at"])
    assert generated_at.tzinfo is not None
    assert generated_at.utcoffset() == timezone.utc.utcoffset(generated_at)
    assert "data" in parsed
    return parsed


def _assert_json_error_envelope(output: str) -> dict:
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    assert parsed["ok"] is False
    assert isinstance(parsed["command"], str)
    assert isinstance(parsed["generated_at"], str)
    generated_at = datetime.fromisoformat(parsed["generated_at"])
    assert generated_at.tzinfo is not None
    assert generated_at.utcoffset() == timezone.utc.utcoffset(generated_at)
    assert isinstance(parsed["error"], dict)
    assert isinstance(parsed["error"]["code"], str)
    assert isinstance(parsed["error"]["message"], str)
    return parsed


@pytest.mark.parametrize(
    "argv",
    [
        ["agent", "status", "--json"],
        ["agent", "plan", "--json"],
        ["events", "list", "--json"],
        ["portfolio", "show", "--json"],
        ["skills", "list", "--json"],
        ["memory", "search", "risk", "--json"],
        ["memory", "doctor", "--json"],
    ],
)
def test_json_contract_commands_emit_single_parseable_json_object(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    (config.memory_dir / "trade_journal.md").write_text("# Journal\n\nrisk note\n", encoding="utf-8")
    skills_dir = config.memory_dir.parent / "skills" / "proposed"
    skills_dir.mkdir(parents=True, exist_ok=True)

    logger = EventLogger(config.events_dir)
    logger.write(
        "agent_started",
        run_id=generate_run_id(),
        command="atlas test",
        mode="paper",
        payload={"source": "test"},
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(argv) == 0

    output = capsys.readouterr().out.strip()
    payload = _assert_json_envelope(output)
    assert payload["command"].startswith("atlas")


def test_validate_json_envelope_non_strict_returns_0_even_when_readiness_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["validate", "--json"])

    output = capsys.readouterr().out.strip()
    payload = _assert_json_envelope(output)
    assert code == 0
    assert payload["command"] == "atlas validate"
    assert payload["data"]["strict"] is False
    assert payload["data"]["passed"] is False
    assert isinstance(payload["data"]["report"], dict)
    assert "Atlas setup checklist" not in output


def test_validate_json_strict_returns_2_with_success_envelope_on_readiness_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["validate", "--json", "--strict"])

    output = capsys.readouterr().out.strip()
    payload = _assert_json_envelope(output)
    assert code == 2
    assert payload["command"] == "atlas validate"
    assert payload["data"]["strict"] is True
    assert payload["data"]["passed"] is False
    assert isinstance(payload["data"]["report"], dict)


def test_validate_strict_text_returns_2_when_readiness_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["validate", "--strict"])

    output = capsys.readouterr().out
    assert code == 2
    assert "Status:" in output


def test_validate_json_internal_failure_emits_error_envelope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        with patch("atlas_agent.diagnostics.readiness.run_diagnostics", side_effect=RuntimeError("boom")):
            code = main(["validate", "--json"])

    output = capsys.readouterr().out.strip()
    payload = _assert_json_error_envelope(output)
    assert code != 0
    assert payload["command"] == "atlas validate"
    assert payload["error"]["code"] == "validate_failed"


def test_validate_json_config_failure_emits_error_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_like_value = "sk-secret-validate-json-should-not-leak"
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atlas" / "config.toml").write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    code = main(["validate", "--json"])
    captured = capsys.readouterr()
    output = captured.out.strip()
    combined = captured.out + captured.err
    payload = _assert_json_error_envelope(output)

    assert code != 0
    assert payload["command"] == "atlas validate"
    assert payload["error"]["code"] == "config_load_failed"
    assert secret_like_value not in combined


def test_config_check_json_emits_envelope_and_returns_int_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atlas" / "config.toml").write_text(
        '[model]\napi_key_env = "sk-test-should-not-leak"\n',
        encoding="utf-8",
    )

    code = main(["config", "check", "--json"])
    output = capsys.readouterr().out.strip()
    payload = _assert_json_envelope(output)

    assert isinstance(code, int)
    assert code == 0
    assert payload["command"] == "atlas config check"
    assert payload["data"]["model"]["api_key_env"] == "[REDACTED]"
    assert "sk-test-should-not-leak" not in output


def test_config_check_json_failure_emits_error_envelope_without_secret_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_like_value = "sk-secret-json-should-not-leak"
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atlas" / "config.toml").write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    code = main(["config", "check", "--json"])
    captured = capsys.readouterr()
    output = captured.out.strip()
    combined = captured.out + captured.err
    payload = _assert_json_error_envelope(output)

    assert code != 0
    assert payload["command"] == "atlas config check"
    assert payload["error"]["code"] == "config_load_failed"
    assert secret_like_value not in combined
