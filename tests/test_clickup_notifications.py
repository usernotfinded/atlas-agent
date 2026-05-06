from __future__ import annotations

import pytest

from omni_trade_ai.notifications.clickup import (
    ClickUpNotifier,
    NotificationConfigurationError,
)


def test_clickup_wrapper_fails_safely_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    with pytest.raises(NotificationConfigurationError, match="CLICKUP_API_TOKEN"):
        ClickUpNotifier(task_id="task").send("summary")


def test_clickup_wrapper_uses_mocked_http_without_printing_token() -> None:
    calls = []

    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {"ok": True}

    response = ClickUpNotifier(
        token="token",
        task_id="task123",
        http_post=fake_post,
    ).send("daily recap")

    assert response == {"ok": True}
    assert "task123/comment" in calls[0][0]
    assert calls[0][1]["Authorization"] == "token"
    assert calls[0][2]["comment_text"] == "daily recap"

