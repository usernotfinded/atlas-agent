#!/usr/bin/env python3
"""CLI command compatibility check — parser-only, no execution.

This script introspects the argparse parser built by atlas_agent.cli.build_parser
and verifies that expected top-level commands, subcommands, and research commands
are present. It does not call providers, brokers, or network endpoints, and it
does not load credentials or modify workspace files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _get_subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _collect_parser_commands(parser: argparse.ArgumentParser) -> dict[str, list[str] | None]:
    """Return mapping of top-level command -> list of subcommands (or None)."""
    result: dict[str, list[str] | None] = {}
    sp = _get_subparsers(parser)
    if sp is None:
        return result
    for name, sub in sp._name_parser_map.items():
        sub_sp = _get_subparsers(sub)
        if sub_sp is not None:
            result[name] = sorted(sub_sp._name_parser_map.keys())
        else:
            result[name] = None
    return result


def _load_contract(repo_root: Path) -> dict:
    env_path = os.environ.get("ATLAS_CLI_CONTRACT_PATH")
    if env_path:
        contract_path = Path(env_path)
    else:
        contract_path = repo_root / "tests" / "fixtures" / "cli_command_contract.json"
    if not contract_path.exists():
        raise FileNotFoundError(f"Contract not found: {contract_path}")
    with open(contract_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_configless_from_specs() -> set[str]:
    """Load configless research command names from command_specs.py."""
    # Delayed import to avoid pulling in heavy CLI dependencies until needed.
    # build_parser itself is imported at check time, but this function only
    # touches the lightweight spec module.
    from atlas_agent.research.command_specs import CONFIGLESS_RESEARCH_COMMANDS

    return set(CONFIGLESS_RESEARCH_COMMANDS)


def _check_contract(parser: argparse.ArgumentParser, contract: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    actual = _collect_parser_commands(parser)

    # 1. Top-level commands
    expected_top = set(contract["top_level_commands"])
    actual_top = set(actual.keys())
    missing_top = expected_top - actual_top
    extra_top = actual_top - expected_top
    if missing_top:
        for cmd in sorted(missing_top):
            errors.append(f"Missing top-level command: {cmd}")
    if extra_top:
        for cmd in sorted(extra_top):
            warnings.append(f"Extra top-level command (not in contract): {cmd}")

    # 2. Subcommands for major families
    expected_subs = contract.get("subcommands", {})
    for family, expected_list in expected_subs.items():
        actual_subs = actual.get(family)
        if actual_subs is None:
            errors.append(f"Missing subparser family: {family}")
            continue
        expected_set = set(expected_list)
        actual_set = set(actual_subs)
        missing = expected_set - actual_set
        extra = actual_set - expected_set
        if missing:
            for cmd in sorted(missing):
                errors.append(f"Missing subcommand: {family} {cmd}")
        if extra:
            for cmd in sorted(extra):
                warnings.append(f"Extra subcommand (not in contract): {family} {cmd}")

    # 3. Configless research commands from specs
    spec_configless = _get_configless_from_specs()
    # All configless commands should exist in the research subparser
    research_subs = actual.get("research")
    if research_subs is None:
        errors.append("Missing research subparser family")
    else:
        research_set = set(research_subs)
        missing_configless = spec_configless - research_set
        if missing_configless:
            for cmd in sorted(missing_configless):
                errors.append(
                    f"Configless research command from specs missing in parser: {cmd}"
                )

    # 4. Safety-sensitive commands presence (coarse check)
    safety = contract.get("safety_sensitive_commands", [])
    for item in safety:
        parts = item.split()
        if len(parts) == 1:
            if parts[0] not in actual_top:
                errors.append(f"Safety-sensitive top-level command missing: {parts[0]}")
        elif len(parts) == 2:
            family, sub = parts
            subs = actual.get(family)
            if subs is None:
                errors.append(f"Safety-sensitive family missing: {family}")
            elif sub not in subs:
                errors.append(f"Safety-sensitive subcommand missing: {family} {sub}")

    # 5. Forbidden default behaviors (presence in contract)
    forbidden = contract.get("forbidden_default_behaviors", [])
    if not forbidden:
        errors.append("Missing forbidden_default_behaviors in contract")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "top_level_count": len(actual_top),
        "subcommand_family_count": sum(
            1 for v in actual.values() if v is not None
        ),
        "research_command_count": len(research_subs) if research_subs is not None else 0,
        "configless_research_command_count": len(spec_configless),
    }


def main() -> int:
    use_json = "--json" in sys.argv[1:]

    repo_root = Path(__file__).resolve().parent.parent
    contract = _load_contract(repo_root)

    # Import here so we fail gracefully if the module is broken
    from atlas_agent.cli import build_parser

    parser = build_parser()
    result = _check_contract(parser, contract)

    if use_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("=" * 50)
        print("CLI Command Compatibility Check")
        print("=" * 50)
        print(f"Top-level commands: {result['top_level_count']}")
        print(f"Subcommand families: {result['subcommand_family_count']}")
        print(f"Research commands: {result['research_command_count']}")
        print(f"Configless research commands: {result['configless_research_command_count']}")
        if result["warnings"]:
            print("-" * 50)
            print("Warnings:")
            for w in result["warnings"]:
                print(f"  - {w}")
        if result["errors"]:
            print("-" * 50)
            print("Errors:")
            for e in result["errors"]:
                print(f"  - {e}")
        print("=" * 50)
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"Result: {status}")
        print("=" * 50)

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
