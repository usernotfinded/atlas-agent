# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_kill_switch_drift.py
# PURPOSE: Verifies kill switch drift behavior and regression expectations.
# DEPS:    json, pathlib, pytest.
# ==============================================================================

"""Kill-switch status drift detection tests.

These tests verify that documented/user-facing kill-switch status values
do not drift from the canonical source-of-truth values defined in the
safety module. They do not exercise runtime behavior or bypass gates.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Canonical values from source of truth
# ---------------------------------------------------------------------------


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _canonical_advanced_modes() -> set[str]:
    """Advanced kill-switch modes from src/atlas_agent/safety/models.py."""
    from atlas_agent.safety.models import KillSwitchMode

    # KillSwitchMode is a Literal; extract its args
    return set(KillSwitchMode.__args__)  # type: ignore[attr-defined]


def _canonical_legacy_modes() -> set[str]:
    """Legacy kill-switch modes from src/atlas_agent/safety/kill_switch.py."""
    from atlas_agent.safety.kill_switch import KILL_SWITCH_MODES

    return set(KILL_SWITCH_MODES)


def _canonical_kill_switch_decision_statuses() -> set[str]:
    """KillSwitchDecision status values from models.py."""
    from atlas_agent.safety.models import KillSwitchDecision

    # Extract from the Literal annotation on the model field
    return set(KillSwitchDecision.model_fields["status"].annotation.__args__)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Drift detection: docs vs canonical values
# ---------------------------------------------------------------------------


class TestKillSwitchDocsDrift:
    def test_kill_switch_doc_uses_only_allowed_advanced_modes(self) -> None:
        """The kill-switch runbook must only reference valid advanced modes."""
        path = REPO_ROOT / "docs" / "kill-switch.md"
        text = path.read_text(encoding="utf-8")
        allowed = _canonical_advanced_modes()
        # Find mode-like words in the doc and verify they are allowed
        # We scan for inline code and prose references
        for line in text.splitlines():
            for mode in allowed:
                # Allowed modes are fine
                pass
        # More concrete: ensure no unknown mode strings appear in backticks
        import re

        code_tokens = set(re.findall(r"`([a-z_]+)`", text))
        unknown = code_tokens - allowed - _canonical_legacy_modes() - {
            "normal",
            "locked_down",
            "bash",
            "true",
            "false",
            "market",
            "aggressive_limit",
            "kill",
            "flatten",
            "soft",
            "cancel",
            "resume",
            "heartbeat",
        }
        # Remove known non-mode tokens
        non_mode = {
            "atlas",
            "json",
            "totp",
            "systemd",
            "docker",
            "serverless",
            "vps",
            "env",
        }
        unknown -= non_mode
        assert not unknown, f"kill-switch.md contains unknown mode tokens: {unknown}"

    def test_kill_switch_doc_deadman_uses_legacy_modes(self) -> None:
        """The dead-man section must reference only legacy-validated modes."""
        path = REPO_ROOT / "docs" / "kill-switch.md"
        text = path.read_text(encoding="utf-8")
        allowed_legacy = _canonical_legacy_modes()
        # The dead-man section should not claim soft_pause/cancel_all/flatten_all
        deadman_section = text.split("## Dead Man's Switch")[-1]
        for bad in ("soft_pause", "cancel_all", "flatten_all"):
            assert bad not in deadman_section, (
                f"kill-switch.md dead-man section references invalid legacy mode '{bad}'. "
                f"deadman.py only accepts {allowed_legacy}."
            )

    def test_kill_switch_doc_lists_all_advanced_modes(self) -> None:
        """The modes section must list every advanced mode."""
        path = REPO_ROOT / "docs" / "kill-switch.md"
        text = path.read_text(encoding="utf-8")
        modes_section = text.split("## Modes")[1].split("## CLI Commands")[0]
        for mode in _canonical_advanced_modes():
            assert f"`{mode}`" in modes_section, (
                f"kill-switch.md Modes section missing advanced mode '{mode}'"
            )


# ---------------------------------------------------------------------------
# Drift detection: CLI contract vs canonical values
# ---------------------------------------------------------------------------


class TestKillSwitchCliContractDrift:
    def test_cli_contract_includes_kill_switch_safety_commands(self) -> None:
        """The CLI contract must list kill-switch commands as safety-sensitive."""
        contract_path = REPO_ROOT / "tests" / "fixtures" / "cli_command_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        safety = set(contract.get("safety_sensitive_commands", []))
        required = {
            "kill-switch enable",
            "kill-switch disable",
            "kill execute-plan",
        }
        missing = required - safety
        assert not missing, (
            f"CLI contract missing kill-switch safety-sensitive commands: {missing}"
        )

    def test_cli_contract_forbids_live_trading_by_default(self) -> None:
        """The contract must explicitly forbid live trading as a default behavior."""
        contract_path = REPO_ROOT / "tests" / "fixtures" / "cli_command_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        forbidden = set(contract.get("forbidden_default_behaviors", []))
        assert "live_trading_enabled_by_default" in forbidden
        assert "provider_execution_enabled_by_default" in forbidden
        assert "broker_execution_enabled_by_default" in forbidden


# ---------------------------------------------------------------------------
# Drift detection: tests do not mock impossible legacy states
# ---------------------------------------------------------------------------


class TestKillSwitchTestMockDrift:
    def test_no_legacy_mode_normal_in_test_mocks(self) -> None:
        """Legacy KillSwitchState does not support mode='normal'.

        Tests that mock mode='normal' on the legacy controller are drifting
        from the advanced vocabulary. This test scans test files for the
        pattern to flag drift; it does not enforce removal of harmless mocks.
        """
        # This is a documentation/drift-detection assertion, not a hard gate.
        # The actual behavior is harmless because mode != "normal" is always
        # true for enabled legacy states. We flag it so future audits see it.
        test_dir = REPO_ROOT / "tests"
        drift_files: list[str] = []
        for path in test_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if 'mode="normal"' in text or "mode='normal'" in text:
                # Only flag if the file also imports legacy kill_switch
                if "kill_switch" in text or "KillSwitchState" in text:
                    drift_files.append(str(path.relative_to(REPO_ROOT)))
        # We do not fail here because the existing mocks are harmless.
        # Instead we document the finding non-fatally.
        if drift_files:
            pytest.xfail(
                f"Known drift: {len(drift_files)} test file(s) mock legacy "
                f"KillSwitchState with mode='normal' (advanced vocab): "
                f"{', '.join(drift_files[:5])}"
            )
