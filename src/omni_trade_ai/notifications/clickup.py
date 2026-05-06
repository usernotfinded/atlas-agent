from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable


class NotificationConfigurationError(RuntimeError):
    pass


HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class ClickUpNotifier:
    def __init__(
        self,
        *,
        token: str | None = None,
        task_id: str | None = None,
        list_id: str | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        self.token = token if token is not None else os.getenv("CLICKUP_API_TOKEN")
        self.task_id = task_id if task_id is not None else os.getenv("CLICKUP_TASK_ID")
        self.list_id = list_id if list_id is not None else os.getenv("CLICKUP_LIST_ID")
        self.http_post = http_post or _default_http_post

    def send(self, message: str) -> dict[str, Any]:
        if not self.token:
            raise NotificationConfigurationError("CLICKUP_API_TOKEN is not configured")
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        if self.task_id:
            return self.http_post(
                f"https://api.clickup.com/api/v2/task/{self.task_id}/comment",
                headers,
                {"comment_text": message},
            )
        if self.list_id:
            return self.http_post(
                f"https://api.clickup.com/api/v2/list/{self.list_id}/task",
                headers,
                {"name": "OmniTradeAI routine update", "description": message},
            )
        raise NotificationConfigurationError(
            "CLICKUP_TASK_ID or CLICKUP_LIST_ID must be configured"
        )


def _default_http_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")

