"""Notification dispatcher.

Routes notifications to the appropriate transport based on configuration.
Safe defaults: disabled or dry-run. Never real delivery unless explicitly configured.
"""
from __future__ import annotations

from atlas_agent.notifications.models import (
    NotificationConfig,
    NotificationPayload,
    NotificationResult,
    NotificationTransport,
)
from atlas_agent.notifications.transports import (
    DisabledTransport,
    DryRunTransport,
    SlackWebhookTransport,
)


_TRANSPORTS: dict[NotificationTransport, type] = {
    NotificationTransport.disabled: DisabledTransport,
    NotificationTransport.dry_run: DryRunTransport,
    NotificationTransport.slack: SlackWebhookTransport,
}


def get_transport(config: NotificationConfig) -> DisabledTransport | DryRunTransport | SlackWebhookTransport:
    """Get the transport instance for the configured transport mode."""
    transport_cls = _TRANSPORTS.get(config.transport, DisabledTransport)
    return transport_cls()


def send_notification(
    payload: NotificationPayload,
    config: NotificationConfig | None = None,
) -> NotificationResult:
    """Send a notification through the configured transport.

    Defaults to disabled if no config is provided.
    """
    if config is None:
        config = NotificationConfig()

    if not config.enabled:
        config.transport = NotificationTransport.disabled

    transport = get_transport(config)
    return transport.send(payload, config)
