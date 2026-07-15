# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/notifications/test_notification_transports.py
# PURPOSE: Verifies notification transports behavior and regression
#         expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

"""Tests for notification transports."""
# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.notifications.models import (
    NotificationConfig,
    NotificationPayload,
    NotificationSeverity,
    NotificationTransport,
)
from atlas_agent.notifications.transports import (
    DisabledTransport,
    DryRunTransport,
    SlackWebhookTransport,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_disabled_transport_returns_disabled() -> None:
    transport = DisabledTransport()
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig()
    result = transport.send(payload, config)
    assert result.status == "disabled"
    assert result.transport == NotificationTransport.disabled


def test_dry_run_transport_returns_dry_run() -> None:
    transport = DryRunTransport()
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(dry_run_emit_preview=True)
    result = transport.send(payload, config)
    assert result.status == "dry_run"
    assert result.transport == NotificationTransport.dry_run
    assert result.redacted_preview
    assert "T" in result.redacted_preview


def test_dry_run_transport_no_preview_when_config_disabled() -> None:
    transport = DryRunTransport()
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(dry_run_emit_preview=False)
    result = transport.send(payload, config)
    assert result.redacted_preview == ""


def test_slack_transport_fails_closed_without_webhook() -> None:
    transport = SlackWebhookTransport()
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(
        transport=NotificationTransport.slack,
        slack_webhook_url="",
        slack_webhook_url_env="NONEXISTENT_ENV_VAR",
    )
    result = transport.send(payload, config)
    assert result.status == "failed"
    assert result.error_code == "slack_webhook_missing"
    assert result.retryable is False


def test_slack_transport_redacts_webhook_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        raise RuntimeError("network error")

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/FAKE")
    transport = SlackWebhookTransport(http_post=fake_post)
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(transport=NotificationTransport.slack)
    result = transport.send(payload, config)
    assert result.status == "error"
    assert result.error_code == "slack_post_error"
    assert result.retryable is True
    # Ensure the fake_post received the webhook URL
    assert calls[0][0] == "https://hooks.slack.com/services/T00/B00/FAKE"
    # Ensure payload has text
    assert "T" in calls[0][2]["text"]


def test_slack_transport_success_with_mocked_post() -> None:
    calls = []

    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {"ok": True}

    transport = SlackWebhookTransport(http_post=fake_post)
    payload = NotificationPayload(title="T", message="M", severity=NotificationSeverity.warning)
    config = NotificationConfig(
        transport=NotificationTransport.slack,
        slack_webhook_url="https://hooks.slack.com/services/T00/B00/FAKE",
    )
    result = transport.send(payload, config)
    assert result.status == "delivered"
    assert result.transport == NotificationTransport.slack
    assert calls[0][2]["text"]


def test_slack_transport_uses_config_url_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {"ok": True}

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/env")
    transport = SlackWebhookTransport(http_post=fake_post)
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(
        transport=NotificationTransport.slack,
        slack_webhook_url="https://hooks.slack.com/services/config",
    )
    transport.send(payload, config)
    assert calls[0][0] == "https://hooks.slack.com/services/config"


def test_slack_build_payload_includes_emoji() -> None:
    from atlas_agent.notifications.transports import SlackWebhookTransport

    payload = NotificationPayload(title="Alert", message="Test", severity=NotificationSeverity.critical)
    slack_payload = SlackWebhookTransport._build_slack_payload(payload)
    assert ":rotating_light:" in slack_payload["text"]
    assert "Alert" in slack_payload["text"]
    assert "Test" in slack_payload["text"]
