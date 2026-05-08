from __future__ import annotations

import os
import sys

import pytest

from atlas_agent.providers.base import ProviderConfigurationError, ProviderRequest
from atlas_agent.providers.local_command import LocalCommandProvider
from atlas_agent.providers.null_provider import NullProvider
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider


def test_null_provider_deterministic() -> None:
    response = NullProvider().generate(
        ProviderRequest("system", "user", "null", metadata={"symbol": "BTC-USD"})
    )

    assert response.parsed_json is not None
    assert response.parsed_json["action"] == "hold"
    assert response.parsed_json["symbol"] == "BTC-USD"


def test_openai_compatible_config_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.example/v1")

    provider = OpenAICompatibleProvider.from_env("DEEPSEEK")

    assert provider.api_key_env == "DEEPSEEK_API_KEY"
    assert provider.base_url == "https://api.deepseek.example/v1"


def test_openai_compatible_missing_api_key_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError, match="missing API key"):
        OpenAICompatibleProvider().generate(ProviderRequest("s", "u", "model"))


def test_local_command_provider_can_be_configured() -> None:
    command = f"\"{sys.executable}\" -c \"import sys; print(sys.stdin.read().upper())\""
    provider = LocalCommandProvider(command=command)

    response = provider.generate(ProviderRequest("s", "hello", "local"))

    assert response.text == "HELLO"
    assert response.raw_response["returncode"] == 0


def test_provider_errors_do_not_execute_trades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAICompatibleProvider()
    broker_called = False

    with pytest.raises(ProviderConfigurationError):
        provider.generate(ProviderRequest("s", "u", "model"))

    assert broker_called is False
    assert "OPENAI_API_KEY" not in os.environ
