# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_redaction.py
# PURPOSE: Verifies redaction behavior and regression expectations.
# DEPS:    os, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import pytest
from atlas_agent.redaction import redact_text, refresh_redaction_secrets, default_redaction_engine
from atlas_agent.config.secrets import set_secret


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_short_low_entropy_secret_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "atlas_agent.config.secrets.get_env_atlas_path", lambda: tmp_path / ".env.atlas"
    )
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    set_secret("TEST_API_KEY", "abc12")
    
    engine = default_redaction_engine()
    assert "abc12" in engine.known_secrets
    
    text = "Here is my key: abc12"
    redacted = redact_text(text)
    assert "abc12" not in redacted
    assert "[REDACTED]" in redacted


def test_short_low_entropy_loaded_secret_redacted(monkeypatch):
    """A short, low-entropy secret loaded into the environment (simulating
    load_atlas_secrets) is redacted after refresh_redaction_secrets()."""
    monkeypatch.setenv("TEST_TOKEN", "xy99")

    refresh_redaction_secrets()

    engine = default_redaction_engine()
    assert "xy99" in engine.known_secrets

    text = "token=xy99 is here"
    redacted = redact_text(text)
    assert "xy99" not in redacted
    assert "[REDACTED]" in redacted
