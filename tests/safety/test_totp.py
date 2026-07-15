# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_totp.py
# PURPOSE: Verifies totp behavior and regression expectations.
# DEPS:    datetime, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from datetime import UTC, datetime

from atlas_agent.safety.totp import generate_totp, verify_totp


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_totp_generate_and_verify() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    code = generate_totp(secret, for_time=now)

    assert verify_totp(secret, code, for_time=now)


def test_totp_rejects_wrong_code() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert not verify_totp(secret, "000000", for_time=now)
