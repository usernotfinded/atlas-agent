from __future__ import annotations

import asyncio

from atlas_agent.gateway.telegram.sanitize import safe_output, sanitize_output


def test_sanitize_output_redacts_sensitive_keys_and_tokens() -> None:
    payload = {
        "TELEGRAM_BOT_TOKEN": "123456:very-secret",
        "provider_api_key": "sk-supersecretkey123456789012345",
        "note": "Authorization: Bearer abcd1234efgh5678ijkl9012mnop3456",
        "ticker": "TEST-SYMBOL",
    }

    sanitized = sanitize_output(payload)

    assert sanitized["TELEGRAM_BOT_TOKEN"] == "[REDACTED]"
    assert sanitized["provider_api_key"] == "[REDACTED]"
    assert "[REDACTED]" in sanitized["note"]
    assert "abcd1234efgh5678ijkl9012mnop3456" not in sanitized["note"]
    assert sanitized["ticker"] == "TEST-SYMBOL"


def test_sanitize_output_redacts_usd_sensitive_fields() -> None:
    payload = {
        "symbol": "ETH-USD",
        "position_pct": 12.5,
        "position_size_usd": 15432.11,
        "equity_usd": "15300.99",
        "nested": {"notional_usd": 8000, "weight_pct": "42%"},
    }

    sanitized = sanitize_output(payload)

    assert sanitized["position_pct"] == 12.5
    assert sanitized["position_size_usd"] == "[REDACTED_USD]"
    assert sanitized["equity_usd"] == "USD [REDACTED]"
    assert sanitized["nested"]["notional_usd"] == "[REDACTED_USD]"
    assert sanitized["nested"]["weight_pct"] == "42%"


def test_sanitize_output_redacts_account_numbers_and_usd_strings() -> None:
    payload = {
        "message": "account: 123456789012 and balance is $12345.67 on BTC",
    }
    sanitized = sanitize_output(payload)
    text = sanitized["message"]

    assert "123456789012" not in text
    assert "USD [REDACTED]" in text
    assert "****9012" in text or "[REDACTED_ACCOUNT]" in text


def test_safe_output_decorator_sync() -> None:
    @safe_output
    def build_payload():
        return {
            "api_token": "token-value",
            "position_size_usd": 1000,
        }

    result = build_payload()
    assert result["api_token"] == "[REDACTED]"
    assert result["position_size_usd"] == "[REDACTED_USD]"


def test_safe_output_decorator_async() -> None:
    @safe_output
    async def build_payload():
        return {
            "note": "API_KEY=abc123",
            "equity_usd": 12000,
        }

    result = asyncio.run(build_payload())
    assert result["note"] == "API_KEY=[REDACTED]"
    assert result["equity_usd"] == "[REDACTED_USD]"
