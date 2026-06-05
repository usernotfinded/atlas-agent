"""Tests for notification dispatcher."""
from __future__ import annotations

from atlas_agent.notifications.models import (
    NotificationConfig,
    NotificationPayload,
    NotificationSeverity,
    NotificationTransport,
)
from atlas_agent.notifications.dispatcher import get_transport, send_notification
from atlas_agent.notifications.transports import (
    DisabledTransport,
    DryRunTransport,
    SlackWebhookTransport,
)


def test_get_transport_disabled() -> None:
    config = NotificationConfig(transport=NotificationTransport.disabled)
    transport = get_transport(config)
    assert isinstance(transport, DisabledTransport)


def test_get_transport_dry_run() -> None:
    config = NotificationConfig(transport=NotificationTransport.dry_run)
    transport = get_transport(config)
    assert isinstance(transport, DryRunTransport)


def test_get_transport_slack() -> None:
    config = NotificationConfig(transport=NotificationTransport.slack)
    transport = get_transport(config)
    assert isinstance(transport, SlackWebhookTransport)


def test_send_notification_defaults_to_disabled() -> None:
    payload = NotificationPayload(title="T", message="M")
    result = send_notification(payload)
    assert result.status == "disabled"
    assert result.transport == NotificationTransport.disabled


def test_send_notification_disabled_when_config_enabled_false() -> None:
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(enabled=False, transport=NotificationTransport.slack)
    result = send_notification(payload, config)
    assert result.status == "disabled"


def test_send_notification_dry_run() -> None:
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(enabled=True, transport=NotificationTransport.dry_run)
    result = send_notification(payload, config)
    assert result.status == "dry_run"
    assert result.transport == NotificationTransport.dry_run


def test_send_notification_slack_without_webhook_fails_closed() -> None:
    payload = NotificationPayload(title="T", message="M")
    config = NotificationConfig(
        enabled=True,
        transport=NotificationTransport.slack,
        slack_webhook_url="",
        slack_webhook_url_env="NONEXISTENT",
    )
    result = send_notification(payload, config)
    assert result.status == "failed"
    assert result.error_code == "slack_webhook_missing"
