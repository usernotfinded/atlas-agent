# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_cli_command_compatibility.py
# PURPOSE: Verifies cli command compatibility behavior and regression
#         expectations.
# DEPS:    argparse, importlib, json, os, subprocess, sys, additional local
#         modules.
# ==============================================================================

"""Tests for the CLI command compatibility check.

These tests verify that:
- The compatibility script passes against the current parser.
- The contract JSON is well-formed and contains required fields.
- Mutated/temporary contracts correctly fail when commands are missing.
- The check script itself remains safe (no shell=True, no network calls).
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_cli_command_compatibility.py"
CONTRACT_PATH = REPO_ROOT / "tests" / "fixtures" / "cli_command_contract.json"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_check_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_cli_command_compatibility", CHECK_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_cli_command_compatibility"] = mod
    spec.loader.exec_module(mod)
    return mod


CHECK_MOD = _load_check_module()


@pytest.fixture
def contract() -> dict:
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_parser() -> argparse.ArgumentParser:
    from atlas_agent.cli import build_parser

    return build_parser()


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------

def test_check_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_check_script_json_output_has_passed_true() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_contract_has_required_fields(contract: dict) -> None:
    assert "version" in contract
    assert "package_series" in contract
    assert "top_level_commands" in contract
    assert "subcommands" in contract
    assert "configless_research_commands" in contract
    assert "safety_sensitive_commands" in contract
    assert "forbidden_default_behaviors" in contract


def test_contract_package_series_matches_current_version(contract: dict) -> None:
    """Contract package_series must match the current package version.

    Prevents stale contract metadata after version bumps.
    """
    from atlas_agent import __version__

    assert contract["package_series"] == __version__, (
        f"CLI contract package_series ({contract['package_series']!r}) "
        f"does not match current package version ({__version__!r}). "
        f"Update tests/fixtures/cli_command_contract.json after version bumps."
    )


def test_contract_forbidden_default_behaviors_present(contract: dict) -> None:
    forbidden = contract["forbidden_default_behaviors"]
    required = {
        "live_trading_enabled_by_default",
        "provider_execution_enabled_by_default",
        "broker_execution_enabled_by_default",
        "credential_loading_in_cli_contract_check",
        "network_calls_in_cli_contract_check",
    }
    assert required.issubset(set(forbidden))


def test_doctor_is_in_contract(contract: dict) -> None:
    assert "doctor" in contract["top_level_commands"]


def test_safety_sensitive_commands_present_in_contract(contract: dict) -> None:
    assert len(contract["safety_sensitive_commands"]) > 0
    for item in contract["safety_sensitive_commands"]:
        parts = item.split()
        assert len(parts) in (1, 2)
        if len(parts) == 1:
            assert parts[0] in contract["top_level_commands"]
        else:
            family, sub = parts
            assert family in contract["subcommands"]
            assert sub in contract["subcommands"][family]


def test_agent_autonomous_commands_present_in_contract_and_parser(
    contract: dict, real_parser: argparse.ArgumentParser
) -> None:
    """FINDING-02: autonomous-paper and autonomous-scorecard must not silently disappear."""
    required = {"autonomous-paper", "autonomous-scorecard"}

    contract_agent = contract.get("subcommands", {}).get("agent", [])
    missing_in_contract = required - set(contract_agent)
    assert not missing_in_contract, (
        f"Missing agent subcommands in contract: {sorted(missing_in_contract)}"
    )

    actual = CHECK_MOD._collect_parser_commands(real_parser)
    parser_agent = actual.get("agent", [])
    missing_in_parser = required - set(parser_agent)
    assert not missing_in_parser, (
        f"Missing agent subcommands in parser: {sorted(missing_in_parser)}"
    )


def test_agent_autonomous_paper_stateful_options_present(
    real_parser: argparse.ArgumentParser,
) -> None:
    """Stateful autonomous-paper CLI options must be present on the parser."""
    subparsers = None
    for action in real_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers = action
            break
    assert subparsers is not None
    agent_parser = subparsers._name_parser_map["agent"]
    agent_sub = None
    for action in agent_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            agent_sub = action
            break
    assert agent_sub is not None
    paper_parser = agent_sub._name_parser_map["autonomous-paper"]
    option_names = {a.dest for a in paper_parser._actions if hasattr(a, "dest")}
    required = {
        "state_dir",
        "resume",
        "initial_cash",
        "commission_bps",
        "slippage_bps",
        "fill_timing",
    }
    missing = required - option_names
    assert not missing, f"Missing autonomous-paper stateful options: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Negative cases with temporary mutated contracts
# ---------------------------------------------------------------------------

def _check_with_contract_override(
    contract_override: dict,
    parser: argparse.ArgumentParser,
) -> dict:
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        temp_contract = json.load(f)
    temp_contract.update(contract_override)
    return CHECK_MOD._check_contract(parser, temp_contract)


def test_missing_top_level_command_fails(real_parser: argparse.ArgumentParser) -> None:
    # Add a fake top-level command to the contract that does not exist in the parser
    result = _check_with_contract_override(
        {"top_level_commands": ["init", "setup", "validate", "fake-missing-command"]},
        real_parser,
    )
    assert result["passed"] is False
    assert any("Missing top-level command: fake-missing-command" in e for e in result["errors"])


def test_missing_research_subcommand_fails(real_parser: argparse.ArgumentParser) -> None:
    result = _check_with_contract_override(
        {"subcommands": {"research": ["run", "list", "fake-missing-research"]}},
        real_parser,
    )
    assert result["passed"] is False
    assert any("Missing subcommand: research fake-missing-research" in e for e in result["errors"])


def test_stale_configless_research_command_fails(
    real_parser: argparse.ArgumentParser,
) -> None:
    # Temporarily monkeypatch the spec set so it includes a fake command
    # that does not exist in the parser.  This simulates a stale spec.
    from atlas_agent.research import command_specs

    original = command_specs.CONFIGLESS_RESEARCH_COMMANDS
    fake = frozenset([*original, "fake-stale-configless-command"])
    command_specs.CONFIGLESS_RESEARCH_COMMANDS = fake  # type: ignore[misc]
    try:
        result = CHECK_MOD._check_contract(real_parser, json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))
    finally:
        command_specs.CONFIGLESS_RESEARCH_COMMANDS = original  # type: ignore[misc]
    assert result["passed"] is False
    assert any("fake-stale-configless-command" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Script source safety checks
# ---------------------------------------------------------------------------

def test_script_source_no_shell_true() -> None:
    source = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_network_client_calls() -> None:
    source = CHECK_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in check script"


def test_script_source_no_subprocess() -> None:
    source = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert "subprocess" not in source


def test_check_does_not_require_credentials() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True


# ---------------------------------------------------------------------------
# Parser introspection safety
# ---------------------------------------------------------------------------

def test_parser_build_does_not_execute_handlers() -> None:
    """build_parser() only constructs argparse objects; it does not run handlers."""
    from atlas_agent.cli import build_parser

    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    sp = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            sp = action
            break
    assert sp is not None
    assert len(sp._name_parser_map) > 0
