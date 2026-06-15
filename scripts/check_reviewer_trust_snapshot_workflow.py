#!/usr/bin/env python3
"""Validate the reviewer trust snapshot GitHub Actions workflow.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or execute any workflow.

Exit codes:
  0 = workflow valid
  1 = blocking findings
  2 = operational error (e.g., missing workflow file)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "reviewer-trust-snapshot.yml"

REQUIRED_SNIPPETS = [
    "scripts/build_reviewer_trust_snapshot.py",
    "scripts/check_reviewer_trust_snapshot.py",
    "actions/upload-artifact@v6",
]

REQUIRED_ENV_SNIPPETS = [
    'ENABLE_LIVE_TRADING: "false"',
    'PROVIDER_EXECUTION_ENABLED: "false"',
    'BROKER_EXECUTION_ENABLED: "false"',
]

FORBIDDEN_COMMANDS = [
    "git push",
    "git tag",
    "git commit",
    "gh release create",
    "gh release upload",
    "twine" + " upload",
    "twine" + " publish",
]

FORBIDDEN_LIVE_PATTERNS = [
    re.compile(r"\b--mode\s+live\b", re.IGNORECASE),
    re.compile(r"\bENABLE_LIVE_TRADING\s*:\s*\"?true\"?", re.IGNORECASE),
    re.compile(r"\bBROKER_EXECUTION_ENABLED\s*:\s*\"?true\"?", re.IGNORECASE),
    re.compile(r"\bPROVIDER_EXECUTION_ENABLED\s*:\s*\"?true\"?", re.IGNORECASE),
    re.compile(r"\batlas\s+run\s+--mode\s+live\b", re.IGNORECASE),
]

BROKER_PROVIDER_EXECUTION_PATTERNS = [
    re.compile(r"\batlas\s+backtest\s+run\b", re.IGNORECASE),
    re.compile(r"\batlas\s+run\s+--mode\s+paper\b", re.IGNORECASE),
]

# Commands that would actually execute broker/provider/live trading. We allow
# the workflow to reference the CLI for --help or static checks, but not to run
# a backtest or paper routine, because those touch broker/provider code paths.
EXECUTION_COMMAND_PATTERNS = [
    re.compile(r"\batlas\s+run\b", re.IGNORECASE),
    re.compile(r"\batlas\s+backtest\b", re.IGNORECASE),
    re.compile(r"\batlas\s+discipline\b", re.IGNORECASE),
    re.compile(r"\batlas\s+live\b", re.IGNORECASE),
    re.compile(r"\batlas\s+submit\b", re.IGNORECASE),
]


def _read_workflow(workflow_path: Path) -> str:
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
    return workflow_path.read_text(encoding="utf-8")


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _check_workflow_exists(workflow_path: Path) -> list[str]:
    errors: list[str] = []
    if not workflow_path.exists():
        try:
            rel = workflow_path.relative_to(REPO_ROOT)
        except ValueError:
            rel = workflow_path
        errors.append(f"Workflow file missing: {rel}")
    return errors


def _check_manual_dispatch_only(text: str) -> list[str]:
    errors: list[str] = []
    if "workflow_dispatch:" not in text:
        errors.append("Workflow must be triggered by workflow_dispatch")
    for trigger in ("push:", "pull_request:", "schedule:"):
        if trigger in text:
            errors.append(f"Workflow must not be triggered by {trigger}")
    return errors


def _check_permissions(text: str) -> list[str]:
    errors: list[str] = []
    if "permissions:" not in text:
        errors.append("Workflow must declare explicit permissions")
        return errors

    lower = text.lower()
    # Allow only contents: read and actions: read; reject broad write permissions.
    broad_write_patterns = [
        r"\bcontents\s*:\s*write\b",
        r"\bactions\s*:\s*write\b",
        r"\bpackages\s*:\s*write\b",
        r"\bchecks\s*:\s*write\b",
        r"\bdeployments\s*:\s*write\b",
        r"\bissues\s*:\s*write\b",
        r"\bpull-requests\s*:\s*write\b",
        r"\brepository-projects\s*:\s*write\b",
        r"\bsecurity-events\s*:\s*write\b",
        r"\bstatuses\s*:\s*write\b",
        r"\bcontents\s*:\s*read-all\b",
        r"\bpermissions\s*:\s*write-all\b",
    ]
    for pattern in broad_write_patterns:
        for m in re.finditer(pattern, lower):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow declares a broad/write permission")
    return errors


def _check_no_secrets(text: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()
    for m in re.finditer(r"\$\{\{\s*secrets\.\w+\s*\}\}", lower):
        line = _line_no(text, m.start())
        errors.append(f"Line {line}: workflow references a secret (${{{{ secrets.* }}}}")
    for m in re.finditer(r"\bsecrets\.\w+", lower):
        line = _line_no(text, m.start())
        errors.append(f"Line {line}: workflow references secrets.*")
    return errors


def _check_forbidden_commands(text: str) -> list[str]:
    errors: list[str] = []
    for command in FORBIDDEN_COMMANDS:
        if command in text.lower():
            idx = text.lower().find(command)
            line = _line_no(text, idx)
            errors.append(f"Line {line}: forbidden command '{command}'")
    return errors


def _check_no_live_trading(text: str) -> list[str]:
    errors: list[str] = []
    for pattern in FORBIDDEN_LIVE_PATTERNS:
        for m in pattern.finditer(text):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow may enable live trading/provider/broker execution")
    return errors


def _check_no_execution_commands(text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.lower()
        # Skip comments and innocuous help invocations.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "--help" in line:
            continue
        for pattern in EXECUTION_COMMAND_PATTERNS:
            if pattern.search(raw_line):
                errors.append(
                    f"Line {line_no}: workflow appears to invoke an execution command"
                )
                break
    return errors


def _check_required_snippets(text: str) -> list[str]:
    errors: list[str] = []
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"Workflow must reference '{snippet}'")
    return errors


def _check_required_env(text: str) -> list[str]:
    errors: list[str] = []
    for snippet in REQUIRED_ENV_SNIPPETS:
        if snippet not in text:
            errors.append(f"Workflow must declare safety env var '{snippet}'")
    return errors


def _check_python_311(text: str) -> list[str]:
    errors: list[str] = []
    if "3.11" not in text:
        errors.append("Workflow must use Python 3.11")
    return errors


def _check_artifact_upload(text: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()
    if "actions/upload-artifact" not in lower:
        errors.append("Workflow must upload an artifact")
    if "reviewer-trust-snapshot" not in lower:
        errors.append("Workflow artifact must be named or reference 'reviewer-trust-snapshot'")
    return errors


def check_workflow(workflow_path: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    workflow_path = workflow_path or DEFAULT_WORKFLOW_PATH

    try:
        text = _read_workflow(workflow_path)
    except FileNotFoundError as e:
        return {
            "passed": False,
            "errors": [str(e)],
            "warnings": [],
        }

    errors.extend(_check_workflow_exists(workflow_path))
    errors.extend(_check_manual_dispatch_only(text))
    errors.extend(_check_permissions(text))
    errors.extend(_check_no_secrets(text))
    errors.extend(_check_forbidden_commands(text))
    errors.extend(_check_no_live_trading(text))
    errors.extend(_check_no_execution_commands(text))
    errors.extend(_check_required_snippets(text))
    errors.extend(_check_required_env(text))
    errors.extend(_check_python_311(text))
    errors.extend(_check_artifact_upload(text))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the reviewer trust snapshot GitHub Actions workflow."
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=DEFAULT_WORKFLOW_PATH,
        help="Path to the workflow file to validate.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    result = check_workflow(args.workflow)

    try:
        workflow_rel = args.workflow.relative_to(REPO_ROOT)
    except ValueError:
        workflow_rel = args.workflow

    if args.json:
        summary = (
            "Reviewer trust snapshot workflow check PASSED"
            if result["passed"]
            else "Reviewer trust snapshot workflow check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "workflow": str(workflow_rel),
                    "summary": summary,
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Reviewer trust snapshot workflow check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Reviewer trust snapshot workflow check PASSED")
        print(f"  Workflow: {workflow_rel}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
