# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/cli/test_doctor_cli.py
# PURPOSE: Verifies doctor cli behavior and regression expectations.
# DEPS:    json, socket, urllib, pathlib, unittest, pytest, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.brokers.resolver import BrokerResolver
from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


# --- CONFIGURATION AND CONSTANTS ---

FAKE_SECRETS = (
    "sk-test-should-not-appear",
    "anthropic-secret-should-not-appear",
    "alpaca-secret-should-not-appear",
    "binance-secret-should-not-appear",
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    config = AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
    )
    config.model.provider = "anthropic"
    config.model.model = "claude-sonnet-4-6"
    config.broker.provider = "alpaca"
    return config


def _set_fake_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_SECRETS[0])
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_SECRETS[1])
    monkeypatch.setenv("ALPACA_API_KEY", "alpaca-key-should-not-appear")
    monkeypatch.setenv("ALPACA_SECRET_KEY", FAKE_SECRETS[2])
    monkeypatch.setenv("BINANCE_API_KEY", "binance-key-should-not-appear")
    monkeypatch.setenv("BINANCE_API_SECRET", FAKE_SECRETS[3])


@pytest.mark.parametrize("argv", [["doctor"], ["doctor", "--json"]])
def test_doctor_redacts_secrets_and_skips_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    argv: list[str],
) -> None:
    config = _config(tmp_path)
    _set_fake_secrets(monkeypatch)

    def fail_network(*args, **kwargs):
        raise AssertionError("doctor attempted a network operation")

    with (
        patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config),
        patch.object(urllib.request, "urlopen", side_effect=fail_network),
        patch.object(socket, "create_connection", side_effect=fail_network),
        patch(
            "atlas_agent.providers.factory.build_provider_from_runtime",
            side_effect=AssertionError("doctor instantiated a provider"),
        ),
        patch(
            "atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker",
            side_effect=AssertionError("doctor resolved an execution broker"),
        ),
        patch(
            "atlas_agent.brokers.resolver.BrokerResolver.resolve_sync_provider",
            side_effect=AssertionError("doctor resolved a sync provider"),
        ),
    ):
        assert main(argv) == 0

    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text
    for secret in FAKE_SECRETS + (
        "alpaca-key-should-not-appear",
        "binance-key-should-not-appear",
    ):
        assert secret not in combined
    assert "[REDACTED]" in captured.out
    assert "network_check" in captured.out


def test_doctor_json_is_deterministic_and_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    _set_fake_secrets(monkeypatch)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
        first = capsys.readouterr().out
        assert main(["doctor", "--json"]) == 0
        second = capsys.readouterr().out

    assert first == second
    payload = json.loads(first)
    assert payload["command"] == "atlas doctor"
    assert payload["diagnostic_mode"] == "read_only_local"
    assert payload["network_check"] == "skipped"
    assert payload["execution_enabled"] is False
    assert payload["safe_default"] == "paper_only"
    assert payload["provider"]["status"] == "configured"
    assert payload["broker"]["live_execution_blocked"] is True
    assert payload["broker"]["client_instantiated"] is False


def test_doctor_human_output_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    _set_fake_secrets(monkeypatch)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor"]) == 0
        first = capsys.readouterr().out
        assert main(["doctor"]) == 0
        second = capsys.readouterr().out

    assert first == second


def test_doctor_reports_missing_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    for env_var in (
        "ANTHROPIC_API_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"]["status"] == "missing_credentials"
    assert payload["broker"]["status"] == "missing_credentials"
    assert all(
        check["secret_state"] == "absent"
        for check in payload["provider"]["credential_checks"]
    )
    assert all(
        check["secret_state"] == "absent"
        for check in payload["broker"]["credential_checks"]
    )


def test_doctor_does_not_treat_placeholder_as_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "YOUR_API_KEY")
    monkeypatch.setenv("ALPACA_API_KEY", "YOUR_API_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "YOUR_API_KEY")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"]["status"] == "missing_credentials"
    assert payload["broker"]["status"] == "missing_credentials"
    assert payload["provider"]["credential_checks"][0]["format_category"] == "placeholder"
    assert all(
        check["format_category"] == "placeholder"
        for check in payload["broker"]["credential_checks"]
    )


def test_doctor_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "marker.txt"
    marker.write_text("unchanged\n", encoding="utf-8")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
    _ = capsys.readouterr()

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_doctor_reports_default_live_block_and_preserves_resolver_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.broker.provider = "none"
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_SECRETS[1])

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert config.trading_mode == "paper"
    assert config.broker.enable_live_trading is False
    assert config.broker.enable_live_submit is False
    assert payload["broker"]["status"] == "paper_only_available"
    assert payload["broker"]["paper_only_available"] is True
    assert payload["broker"]["live_execution_blocked"] is True

    resolution = BrokerResolver(config).resolve_execution_broker("live")
    assert resolution.execution_broker is None
    assert resolution.status.can_submit is False


def test_doctor_reports_missing_optional_broker_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.broker.provider = "binance"
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_SECRETS[1])
    monkeypatch.setenv("BINANCE_API_KEY", "configured-binance-key")
    monkeypatch.setenv("BINANCE_API_SECRET", FAKE_SECRETS[3])

    with (
        patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config),
        patch("importlib.util.find_spec", return_value=None),
    ):
        assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["broker"]["status"] == "missing_optional_dependency"
    assert payload["broker"]["optional_dependency"]["missing"] == ["ccxt"]


def test_doctor_reports_unsupported_provider_and_broker(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.model.provider = "unknown-provider"
    config.broker.provider = "unknown-broker"

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"]["status"] == "unsupported_provider"
    assert payload["broker"]["status"] == "unsupported_broker"
