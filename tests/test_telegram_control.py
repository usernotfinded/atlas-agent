from __future__ import annotations

from atlas_agent.safety.totp import generate_totp
from atlas_agent.telegram_control import (
    get_telegram_diagnostics,
    parse_kill_command_mode,
    parse_resume_totp,
    verify_resume_totp_from_env,
)


def test_parse_kill_command_mode() -> None:
    assert parse_kill_command_mode("/kill") == "soft"
    assert parse_kill_command_mode("/kill flatten") == "flatten"
    assert parse_kill_command_mode("/kill cancel") == "cancel"
    assert parse_kill_command_mode("/kill nope") is None


def test_parse_resume_totp() -> None:
    assert parse_resume_totp("/resume 123456") == "123456"
    assert parse_resume_totp("/resume") is None
    assert parse_resume_totp("/kill") is None


def test_verify_resume_totp_from_env() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    code = generate_totp(secret)
    env = {"ATLAS_TOTP_SECRET": secret}
    assert verify_resume_totp_from_env(code, env=env)
    assert not verify_resume_totp_from_env("000000", env=env)


def test_diagnostics_reads_new_allowed_users_env() -> None:
    env = {
        "TELEGRAM_BOT_TOKEN": "x",
        "ATLAS_TELEGRAM_ALLOWED_USERS": "1,2",
        "TELEGRAM_CONTROL_MODE": "enabled",
    }
    diagnostics = get_telegram_diagnostics(env=env)
    assert diagnostics.token_present is True
    assert diagnostics.allowed_users_present is True
    assert diagnostics.mode == "enabled"
