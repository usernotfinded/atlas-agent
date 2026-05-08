from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from atlas_agent.safety.kill_switch import KILL_SWITCH_MODES
from atlas_agent.safety.totp import verify_totp


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
    "/kill flatten",
    "/resume <totp>",
    "/heartbeat",
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
    allowed_user_ids = values.get("ATLAS_TELEGRAM_ALLOWED_USERS") or values.get(
        "TELEGRAM_ALLOWED_USER_IDS",
        "",
    )
    return TelegramDiagnostics(
        token_present=bool(values.get("TELEGRAM_BOT_TOKEN")),
        allowed_users_present=bool(allowed_user_ids),
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
    allowed = values.get("ATLAS_TELEGRAM_ALLOWED_USERS") or values.get(
        "TELEGRAM_ALLOWED_USER_IDS"
    )
    return is_authorized_user(user_id, allowed)


def parse_kill_command_mode(command_text: str) -> str | None:
    parts = command_text.strip().split()
    if not parts:
        return None
    if parts[0].lower() != "/kill":
        return None
    if len(parts) == 1:
        return "soft"
    mode = parts[1].strip().lower()
    if mode in KILL_SWITCH_MODES:
        return mode
    return None


def parse_resume_totp(command_text: str) -> str | None:
    parts = command_text.strip().split()
    if not parts or parts[0].lower() != "/resume":
        return None
    if len(parts) < 2:
        return None
    return parts[1].strip()


def should_require_totp_for_resume(state_mode: str | None = None) -> bool:
    # Resume is always sensitive. Flatten is explicitly mandatory.
    return True if state_mode is None else state_mode.lower() in {"soft", "cancel", "flatten"}


def verify_resume_totp_from_env(
    totp_code: str,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env if env is not None else os.environ
    secret = values.get("ATLAS_TOTP_SECRET", "").strip()
    if not secret:
        return False
    return verify_totp(secret, totp_code)
