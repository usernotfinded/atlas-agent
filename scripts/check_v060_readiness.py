#!/usr/bin/env python3
"""Read-only v0.6.0 readiness checker.

Verifies that required docs, source modules, test files, CLI commands,
CHANGELOG entries, version identity, and safety checks are present and
consistent before any v0.6.0 version bump or release cutover.

Exit codes:
  0 = valid
  1 = blocking findings
  2 = operational error

Deterministic and local. Does not:
- call network
- call GitHub API
- publish
- upload
- tag
- push
- require credentials
- run live trading
- call brokers/providers
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGE_VERSION = "0.5.9.5"
PUBLIC_TAG = "v0.5.9.5"

REQUIRED_DOCS = [
    REPO_ROOT / "docs" / "releases" / "v0.6.0-readiness.md",
    REPO_ROOT / "docs" / "v0.6-capability-inventory.md",
    REPO_ROOT / "docs" / "v0.6-roadmap.md",
    REPO_ROOT / "docs" / "broker-roadmap.md",
    REPO_ROOT / "docs" / "reports.md",
    REPO_ROOT / "docs" / "reflection.md",
    REPO_ROOT / "docs" / "skills.md",
    REPO_ROOT / "docs" / "learning-loop.md",
    REPO_ROOT / "docs" / "dashboard.md",
    REPO_ROOT / "docs" / "notifications.md",
]

REQUIRED_SOURCE_MODULES = [
    REPO_ROOT / "src" / "atlas_agent" / "backtest" / "engine.py",
    REPO_ROOT / "src" / "atlas_agent" / "backtest" / "strategy.py",
    REPO_ROOT / "src" / "atlas_agent" / "reports" / "generator.py",
    REPO_ROOT / "src" / "atlas_agent" / "reflection" / "models.py",
    REPO_ROOT / "src" / "atlas_agent" / "skills" / "models.py",
    REPO_ROOT / "src" / "atlas_agent" / "learning" / "models.py",
    REPO_ROOT / "src" / "atlas_agent" / "dashboard" / "collectors.py",
    REPO_ROOT / "src" / "atlas_agent" / "notifications" / "models.py",
    REPO_ROOT / "src" / "atlas_agent" / "brokers" / "status.py",
    REPO_ROOT / "src" / "atlas_agent" / "brokers" / "guards.py",
]

REQUIRED_TEST_FILES = [
    REPO_ROOT / "tests" / "backtest" / "test_backtest_engine.py",
    REPO_ROOT / "tests" / "backtest" / "test_strategy_pack.py",
    REPO_ROOT / "tests" / "reports" / "test_report_generator.py",
    REPO_ROOT / "tests" / "reflection" / "test_reflection_models.py",
    REPO_ROOT / "tests" / "skills" / "test_skill_models.py",
    REPO_ROOT / "tests" / "learning" / "test_learning_models.py",
    REPO_ROOT / "tests" / "dashboard" / "test_dashboard_models.py",
    REPO_ROOT / "tests" / "notifications" / "test_notification_models.py",
    REPO_ROOT / "tests" / "brokers" / "test_broker_status.py",
    REPO_ROOT / "tests" / "brokers" / "test_broker_guards.py",
    REPO_ROOT / "tests" / "cli" / "test_backtest_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_report_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_reflection_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_skills_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_learning_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_dashboard_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_notifications_cli.py",
    REPO_ROOT / "tests" / "cli" / "test_brokers_cli.py",
]

REQUIRED_CLI_SUBCOMMANDS = {
    "broker": ["status"],
    "notifications": ["send", "test"],
    "reflection": ["approve", "archive", "create", "list", "reject", "show", "submit"],
    "skills": [
        "approve-candidate",
        "archive-candidate",
        "create-candidate",
        "list-candidates",
        "list-library",
        "promote-candidate",
        "reject-candidate",
        "show-candidate",
        "show-library",
        "submit-candidate",
    ],
    "learning": [
        "accept-suggestion",
        "archive-suggestion",
        "list-suggestions",
        "reject-suggestion",
        "show-suggestion",
        "submit-suggestion",
        "suggest",
    ],
    "report": ["daily", "generate"],
}

CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PATH = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
CLI_CONTRACT_PATH = REPO_ROOT / "tests" / "fixtures" / "cli_command_contract.json"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _check_required_files(files: list[Path], label: str) -> list[str]:
    errors = []
    for f in files:
        if not f.exists():
            errors.append(f"Missing {label}: {f.relative_to(REPO_ROOT)}")
    return errors


def _check_changelog_unreleased() -> list[str]:
    errors = []
    if not CHANGELOG_PATH.exists():
        errors.append("CHANGELOG.md not found")
        return errors
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    if "## [Unreleased]" not in text:
        errors.append("CHANGELOG.md missing [Unreleased] section")
    # Ensure there is no premature v0.6.0 release section
    if "## [0.6.0]" in text or "## [v0.6.0]" in text:
        errors.append("CHANGELOG.md contains a premature v0.6.0 release section")
    return errors


def _check_version_identity() -> list[str]:
    errors = []
    if not PYPROJECT_PATH.exists():
        errors.append("pyproject.toml not found")
    else:
        text = PYPROJECT_PATH.read_text(encoding="utf-8")
        if f'version = "{PACKAGE_VERSION}"' not in text:
            errors.append(f"pyproject.toml version is not {PACKAGE_VERSION}")
    if not INIT_PATH.exists():
        errors.append("src/atlas_agent/__init__.py not found")
    else:
        text = INIT_PATH.read_text(encoding="utf-8")
        if f'__version__ = "{PACKAGE_VERSION}"' not in text:
            errors.append(f"src/atlas_agent/__init__.py version is not {PACKAGE_VERSION}")
    return errors


def _check_cli_contract() -> list[str]:
    errors = []
    if not CLI_CONTRACT_PATH.exists():
        errors.append("CLI command contract not found")
        return errors
    try:
        contract = _load_json(CLI_CONTRACT_PATH)
    except Exception as exc:
        errors.append(f"CLI contract JSON error: {exc}")
        return errors
    subcommands = contract.get("subcommands", {})
    for command, required in REQUIRED_CLI_SUBCOMMANDS.items():
        actual = subcommands.get(command, [])
        for sub in required:
            if sub not in actual:
                errors.append(f"CLI contract missing subcommand: {command} {sub}")
    return errors


def _check_no_v060_tag() -> list[str]:
    errors = []
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "v0.6.0"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            errors.append("v0.6.0 tag already exists")
    except Exception as exc:
        errors.append(f"git tag check failed: {exc}")
    return errors


def _check_forbidden_claims() -> list[str]:
    errors = []
    script = REPO_ROOT / "scripts" / "check_forbidden_claims.py"
    if not script.exists():
        errors.append("Forbidden claims checker not found")
        return errors
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            errors.append("Forbidden claims check failed")
    except Exception as exc:
        errors.append(f"Forbidden claims check error: {exc}")
    return errors


def _check_generated_artifacts() -> list[str]:
    errors = []
    script = REPO_ROOT / "scripts" / "check_generated_artifacts.py"
    if not script.exists():
        errors.append("Generated artifacts checker not found")
        return errors
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            errors.append("Generated artifacts check failed")
    except Exception as exc:
        errors.append(f"Generated artifacts check error: {exc}")
    return errors


def run_check(json_output: bool = False) -> tuple[int, dict]:
    errors: list[str] = []
    errors.extend(_check_required_files(REQUIRED_DOCS, "doc"))
    errors.extend(_check_required_files(REQUIRED_SOURCE_MODULES, "source module"))
    errors.extend(_check_required_files(REQUIRED_TEST_FILES, "test file"))
    errors.extend(_check_changelog_unreleased())
    errors.extend(_check_version_identity())
    errors.extend(_check_cli_contract())
    errors.extend(_check_no_v060_tag())
    errors.extend(_check_forbidden_claims())
    errors.extend(_check_generated_artifacts())

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "checks": {
            "docs": len(REQUIRED_DOCS),
            "source_modules": len(REQUIRED_SOURCE_MODULES),
            "test_files": len(REQUIRED_TEST_FILES),
            "cli_subcommands": sum(len(v) for v in REQUIRED_CLI_SUBCOMMANDS.values()),
        },
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if result["valid"]:
            print("v0.6.0 readiness: PASS")
            print(f"  docs={result['checks']['docs']} "
                  f"source_modules={result['checks']['source_modules']} "
                  f"test_files={result['checks']['test_files']} "
                  f"cli_subcommands={result['checks']['cli_subcommands']}")
        else:
            print("v0.6.0 readiness: FAIL")
            for e in errors:
                print(f"  - {e}")

    return 0 if result["valid"] else 1, result


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.6.0 readiness checker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    code, _ = run_check(json_output=args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
