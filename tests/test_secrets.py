# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_secrets.py
# PURPOSE: Verifies secrets behavior and regression expectations.
# DEPS:    os, pytest, unittest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import pytest
from unittest.mock import patch
from atlas_agent.config.secrets import (
    set_secret,
    load_atlas_secrets,
    _validate_secret_key,
    InvalidSecretValueError,
)
from atlas_agent.redaction import default_redaction_engine


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_set_secret_refreshes_redaction(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "atlas_agent.config.secrets.get_env_atlas_path", lambda: tmp_path / ".env.atlas"
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    set_secret("OPENAI_API_KEY", "short123")
    assert "short123" in default_redaction_engine().known_secrets


def test_load_atlas_secrets_refreshes_redaction(tmp_path, monkeypatch):
    """load_atlas_secrets() must call refresh_redaction_secrets() so that
    secrets loaded from .env.atlas are immediately available for redaction."""
    env_file = tmp_path / ".env.atlas"
    env_file.write_text("MY_API_KEY=loadtest99\n", encoding="utf-8")

    # Patch the path resolver so load_atlas_secrets reads our temp file
    monkeypatch.setattr(
        "atlas_agent.config.secrets.get_env_atlas_path", lambda: env_file
    )

    # Remove from process env if present so load_dotenv picks it up
    monkeypatch.delenv("MY_API_KEY", raising=False)

    load_atlas_secrets()
    assert "loadtest99" in default_redaction_engine().known_secrets


def test_short_low_entropy_set_secret_redacted(tmp_path, monkeypatch):
    """A short, low-entropy secret set via set_secret() must appear in known_secrets."""
    monkeypatch.setattr(
        "atlas_agent.config.secrets.get_env_atlas_path", lambda: tmp_path / ".env.atlas"
    )
    monkeypatch.delenv("TEST_SECRET", raising=False)
    set_secret("TEST_SECRET", "ab12")
    engine = default_redaction_engine()
    assert "ab12" in engine.known_secrets


def test_invalid_secret_key_names():
    with pytest.raises(ValueError):
        _validate_secret_key("BAD=KEY")
    with pytest.raises(ValueError):
        _validate_secret_key("BAD KEY")
    with pytest.raises(ValueError):
        _validate_secret_key("BAD\nKEY")
    with pytest.raises(ValueError):
        _validate_secret_key("BAD/KEY")
    with pytest.raises(ValueError):
        _validate_secret_key("1BAD")
    with pytest.raises(ValueError):
        _validate_secret_key("")


def test_valid_secret_key_names():
    _validate_secret_key("GOOD_KEY")
    _validate_secret_key("GOOD_KEY_1")
    _validate_secret_key("_GOOD_KEY")


def test_secret_value_not_in_error_message(tmp_path, monkeypatch):
    """Error messages from secret validation must never contain the rejected value."""
    monkeypatch.setattr(
        "atlas_agent.config.secrets.get_env_atlas_path", lambda: tmp_path / ".env.atlas"
    )
    bad_value = "line1\nline2"
    with pytest.raises(InvalidSecretValueError) as exc_info:
        set_secret("OPENAI_API_KEY", bad_value)
    # The error message must not contain the actual secret value
    assert bad_value not in str(exc_info.value)
    assert "line1" not in str(exc_info.value)
    assert "line2" not in str(exc_info.value)
