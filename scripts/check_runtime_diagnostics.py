#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_runtime_diagnostics.py
# PURPOSE: Read-only runtime diagnostics helper for local check scripts.
# DEPS:    argparse, json, sys, pathlib.
# ==============================================================================

"""Read-only runtime diagnostics helper for local check scripts.

Prints available focused check commands, expected runtime ranges,
and guidance for triaging long-running checks without running them.
"""

# --- IMPORTS ---

import argparse
import json
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

COMMANDS = [
    {
        "script": "./scripts/dev_check.sh",
        "description": "Fast local development gate",
        "expected": "~30–90s",
        "category": "core",
    },
    {
        "script": "./scripts/ci_check.sh",
        "description": "Local CI parity gate",
        "expected": "~60–180s",
        "category": "core",
    },
    {
        "script": "./scripts/release_check.sh --quick",
        "description": "Release-adjacent quick safety check",
        "expected": "~30–90s",
        "category": "core",
    },
    {
        "script": "./scripts/research_check.sh",
        "description": "Research/sandbox gate",
        "expected": "~60–300s",
        "category": "long",
    },
    {
        "script": "./scripts/release_check.sh --full",
        "description": "Full release gate (full pytest + demos)",
        "expected": "~120–600s",
        "category": "long",
    },
]

FOCUSED_SUBSETS = [
    {
        "label": "Research sandbox only",
        "command": 'PYTHONPATH=src python3.11 -m pytest tests/research/test_research_sandbox_cli.py -q',
    },
    {
        "label": "Release script tests only",
        "command": 'PYTHONPATH=src python3.11 -m pytest tests/test_release_check_scripts.py -q',
    },
    {
        "label": "CI workflow tests only",
        "command": 'PYTHONPATH=src python3.11 -m pytest tests/test_ci_workflows.py -q',
    },
    {
        "label": "Research provider adapter only",
        "command": 'PYTHONPATH=src python3.11 -m pytest tests/research/test_research_provider_adapter_interface_contract.py -q',
    },
    {
        "label": "Forbidden claims + version",
        "command": (
            'python3.11 scripts/check_version_consistency.py && '
            'python3.11 scripts/check_forbidden_claims.py'
        ),
    },
]

ENV_HINTS = [
    ("ATLAS_CHECK_FAIL_FAST=1", "Pass -x to pytest (stop on first failure)"),
    ("ATLAS_CHECK_LAST_FAILED=1", "Pass --lf to pytest (run only last failed)"),
    ("ATLAS_CHECK_PYTEST_ARGS=...", "Extra arguments appended to pytest invocations"),
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _print_text() -> None:
    print("Atlas Agent — Local Check Runtime Diagnostics")
    print("=" * 50)
    print()
    print("Available check commands and expected runtimes:")
    print()
    for cmd in COMMANDS:
        cat_label = "CORE" if cmd["category"] == "core" else "LONG"
        print(f"  [{cat_label}] {cmd['script']}")
        print(f"           {cmd['description']}")
        print(f"           Expected: {cmd['expected']}")
        print()

    print("Focused subsets (for faster iteration):")
    print()
    for subset in FOCUSED_SUBSETS:
        print(f"  {subset['label']}")
        print(f"    {subset['command']}")
        print()

    print("Environment variables that affect check behavior:")
    print()
    for var, desc in ENV_HINTS:
        print(f"  {var}")
        print(f"    {desc}")
    print()

    print("Timeout triage guidance:")
    print()
    print("  - If a LONG check times out but all CORE checks pass,")
    print("    report the LONG check as WARN / INCONCLUSIVE, not PASS.")
    print("  - Do not weaken checks, add broad '|| true', or skip tests")
    print("    to avoid timeout.")
    print("  - Use focused subsets to isolate slow steps.")
    print("  - Per-step elapsed output is printed by research_check.sh")
    print("    and release_check.sh after each step.")
    print("  - Capture full output to a log for post-hoc analysis:")
    print("      ./scripts/release_check.sh --full 2>&1 | tee /tmp/release.log")
    print()


def _print_json() -> None:
    result = {
        "artifact_type": "runtime_diagnostics",
        "schema_version": 1,
        "commands": COMMANDS,
        "focused_subsets": FOCUSED_SUBSETS,
        "environment_hints": [
            {"variable": var, "description": desc} for var, desc in ENV_HINTS
        ],
        "guidance": {
            "timeout_classification": (
                "If a long check times out but all core checks pass, "
                "report as WARN / INCONCLUSIVE, not PASS."
            ),
            "do_not_weaken": (
                "Do not weaken checks, add broad '|| true', or skip tests "
                "to avoid timeout."
            ),
            "capture_logs": (
                "Capture full output to a log for post-hoc analysis: "
                "./scripts/release_check.sh --full 2>&1 | tee /tmp/release.log"
            ),
        },
    }
    print(json.dumps(result, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only runtime diagnostics for local check scripts."
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.json:
        _print_json()
    else:
        _print_text()

    return 0


if __name__ == "__main__":
    sys.exit(main())
