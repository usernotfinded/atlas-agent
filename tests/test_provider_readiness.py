"""Tests for provider readiness gate and capability inventory."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atlas_agent.providers.provider_preflight import PreflightValidationError
from atlas_agent.providers.provider_readiness import (
    evaluate_provider_readiness,
    generate_capability_inventory,
)


def test_capability_inventory_structure(monkeypatch):
    monkeypatch.setenv("ATLAS_OPENROUTER_API_KEY", "sk-fake-key-12345")
    inventory = generate_capability_inventory()

    assert inventory["artifact_type"] == "provider_capability_inventory"
    assert "generated_at" in inventory
    assert isinstance(inventory["providers"], list)

    assert len(inventory["providers"]) > 0

    for p in inventory["providers"]:
        assert p["execution_enabled_by_default"] is False
        assert p["network_used"] is False
        assert p["credentials_loaded"] is False
        assert "real-provider-call" in p["blocked_current_modes"]

    assert inventory["global_safety_summary"]["provider_execution_enabled"] is False

    inv_str = json.dumps(inventory)
    assert "sk-fake-key" not in inv_str


def test_evaluate_provider_readiness_valid(monkeypatch):
    monkeypatch.setenv("ATLAS_OPENROUTER_API_KEY", "sk-fake-key-12345")
    report = evaluate_provider_readiness(
        provider_id="openrouter",
        model_id="openrouter/auto",
        purpose="research-summary",
        max_context_chars=4000,
    )

    assert report["valid"] is True
    assert report["decision"] == "preflight_only"
    assert report["provider_execution_allowed"] is False
    assert report["network_allowed"] is False
    assert report["credentials_allowed"] is False
    assert report["broker_allowed"] is False
    assert report["live_trading_allowed"] is False
    assert report["manual_review_required"] is True
    assert report["safety_summary"]["provider_call_made"] is False

    rep_str = json.dumps(report)
    assert "sk-fake-key" not in rep_str


def test_evaluate_provider_readiness_invalid():
    with pytest.raises(PreflightValidationError):
        evaluate_provider_readiness(
            provider_id="",
            model_id="openrouter/auto",
            purpose="test",
            max_context_chars=4000,
        )

    with pytest.raises(PreflightValidationError):
        evaluate_provider_readiness(
            provider_id="openrouter",
            model_id="secret_key_123",
            purpose="test",
            max_context_chars=4000,
        )

    with pytest.raises(PreflightValidationError):
        evaluate_provider_readiness(
            provider_id="openrouter",
            model_id="model",
            purpose="test",
            max_context_chars=-1,
        )


def test_cli_capability_inventory(tmp_path):
    out_file = tmp_path / "cap.json"
    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "providers",
        "capability-inventory",
        "--output",
        str(out_file),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    assert out_file.exists()

    data = json.loads(out_file.read_text())
    assert data["artifact_type"] == "provider_capability_inventory"


def test_cli_readiness_check(tmp_path):
    out_file = tmp_path / "ready.json"
    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "providers",
        "readiness-check",
        "--provider",
        "openrouter",
        "--model",
        "openrouter/auto",
        "--purpose",
        "research",
        "--output",
        str(out_file),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    assert out_file.exists()

    data = json.loads(out_file.read_text())
    assert data["artifact_type"] == "provider_readiness_report"
    assert data["decision"] == "preflight_only"
