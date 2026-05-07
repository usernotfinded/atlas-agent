from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


TELEGRAM_COMMANDS = (
    "/status",
    "/plan",
    "/run",
    "/learn",
    "/reflect",
    "/positions",
    "/pending",
    "/approve <order_id>",
    "/reject <order_id>",
    "/kill",
    "/resume",
    "/memory <query>",
    "/skills",
)


@dataclass(frozen=True)
class TelegramDiagnostics:
    token_present: bool
    allowed_users_present: bool
    mode: str

    def format(self) -> str:
        return "\n".join(
            (
                "Telegram control plane diagnostics",
                f"TELEGRAM_BOT_TOKEN present: {'yes' if self.token_present else 'no'}",
                (
                    "TELEGRAM_ALLOWED_USER_IDS present: "
                    f"{'yes' if self.allowed_users_present else 'no'}"
                ),
                f"mode: {self.mode}",
                "network: not contacted",
            )
        )


def get_telegram_diagnostics(
    env: Mapping[str, str] | None = None,
) -> TelegramDiagnostics:
    values = env if env is not None else os.environ
    return TelegramDiagnostics(
        token_present=bool(values.get("TELEGRAM_BOT_TOKEN")),
        allowed_users_present=bool(values.get("TELEGRAM_ALLOWED_USER_IDS")),
        mode=values.get("TELEGRAM_CONTROL_MODE", "disabled"),
    )


def get_telegram_commands() -> tuple[str, ...]:
    return TELEGRAM_COMMANDS


def is_authorized_user(user_id: str | int, allowed_user_ids: str | None) -> bool:
    if not allowed_user_ids:
        return False
    requested = str(user_id).strip()
    allowed = {part.strip() for part in allowed_user_ids.split(",") if part.strip()}
    return requested in allowed


def is_authorized_user_from_env(
    user_id: str | int,
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env if env is not None else os.environ
    return is_authorized_user(user_id, values.get("TELEGRAM_ALLOWED_USER_IDS"))
