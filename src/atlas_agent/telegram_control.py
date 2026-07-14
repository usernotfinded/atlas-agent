# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    telegram_control.py
# PURPOSE: Pure parsing and authorisation logic for the Telegram control plane.
#          Deliberately network-free: this module decides *whether* a message is
#          allowed to do something, never does it. That keeps the authorisation
#          boundary unit-testable without a bot, a token or a socket.
# DEPS:    safety.kill_switch (valid modes), safety.totp (second factor)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from atlas_agent.safety.kill_switch import KILL_SWITCH_MODES
from atlas_agent.safety.totp import verify_totp


# --- CONFIGURATIONS & CONSTANTS ---

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


# ==============================================================================
# DIAGNOSTICS
# ==============================================================================

@dataclass(frozen=True)
class TelegramDiagnostics:
    # Booleans, never the values themselves: this struct exists precisely so that
    # `atlas telegram doctor` can confirm a token is configured without printing it.
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


# ==============================================================================
# AUTHORISATION
# ==============================================================================

def is_authorized_user(user_id: str | int, allowed_user_ids: str | None) -> bool:
    # Unconfigured means "nobody", not "everybody". If the allowlist is missing the
    # bot must be inert — the failure mode of the opposite default is a stranger on
    # Telegram holding the kill switch.
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


# ==============================================================================
# COMMAND PARSING
# ==============================================================================

def parse_kill_command_mode(command_text: str) -> str | None:
    parts = command_text.strip().split()
    if not parts:
        return None
    if parts[0].lower() != "/kill":
        return None
    # A bare `/kill` means "soft": the mildest mode, because the operator who typed
    # it under pressure did not ask to liquidate anything. Escalating to flatten must
    # be spelled out.
    if len(parts) == 1:
        return "soft"
    mode = parts[1].strip().lower()
    # Validated against the canonical mode set rather than passed through, so a typo
    # (`/kill flatn`) returns None and is rejected instead of reaching the switch as
    # an unrecognised — and possibly mis-handled — mode.
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


# ==============================================================================
# RESUME SECOND FACTOR
# ==============================================================================

def should_require_totp_for_resume(state_mode: str | None = None) -> bool:
    # Killing is cheap; *un*-killing is the dangerous direction. Anyone who has
    # grabbed the chat can stop the agent — only a second factor should be able to
    # start it trading again. Unknown mode (None) requires TOTP too: fail closed.
    return True if state_mode is None else state_mode.lower() in {"soft", "cancel", "flatten"}


def verify_resume_totp_from_env(
    totp_code: str,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env if env is not None else os.environ
    secret = values.get("ATLAS_TOTP_SECRET", "").strip()
    # No secret configured → resume is impossible, not automatic. An unconfigured
    # second factor must never degrade into no second factor.
    if not secret:
        return False
    return verify_totp(secret, totp_code)
