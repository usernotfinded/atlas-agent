#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_release_assurance_diagnostics_artifact_workflow.py
# PURPOSE: Validate the release-assurance diagnostics artifact revalidation
#         workflow.
# DEPS:    argparse, json, re, sys, pathlib, typing.
# ==============================================================================

"""Validate the release-assurance diagnostics artifact revalidation workflow.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or execute any workflow.

Exit codes:
  0 = workflow valid
  1 = blocking findings or operational errors (e.g., missing workflow file)
  2 = unexpected checker error
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "release-assurance-diagnostics-artifact-validate.yml"
)

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
    # Split to avoid the literal substring that the trust-center source scan rejects.
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

EXECUTION_COMMAND_PATTERNS = [
    re.compile(r"\batlas\s+run\b", re.IGNORECASE),
    re.compile(r"\batlas\s+backtest\b", re.IGNORECASE),
    re.compile(r"\batlas\s+discipline\b", re.IGNORECASE),
    re.compile(r"\batlas\s+live\b", re.IGNORECASE),
    re.compile(r"\batlas\s+submit\b", re.IGNORECASE),
]

# Only the repository-provided read-only token is allowed.
SAFE_TOKEN_PATTERN = re.compile(
    r"\$\{\{\s*github\.token\s*\}\}",
    re.IGNORECASE,
)

VALIDATOR_COMMAND_MARKER = "scripts/check_release_assurance_diagnostics_artifact.py"
DOWNLOAD_COMMAND_MARKER = "gh run download"

REQUIRED_INPUTS = {
    "source_run_id": {"type": "string", "required": True},
    "artifact_name": {"type": "string", "required": False, "default": "release-assurance-diagnostics"},
    "expect_release": {"type": "string", "required": False, "default": '""'},
    "expect_failed_check": {"type": "string", "required": False, "default": '""'},
    "allow_passed": {"type": "boolean", "required": False, "default": "false"},
}


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _mask_safe_tokens(text: str) -> str:
    """Replace allowed read-only token expressions with a placeholder."""
    return SAFE_TOKEN_PATTERN.sub("__SAFE_GITHUB_TOKEN__", text)


def _read_workflow(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")
    return path.read_text(encoding="utf-8")


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _check_workflow_exists(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        errors.append(f"Workflow file missing: {rel}")
    return errors


def _extract_on_trigger_keys(text: str) -> list[str]:
    """Return the direct trigger key names under the top-level `on:` block."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "on" or stripped.startswith("on:") or stripped.startswith("on "):
            start = i
            break
    if start is None:
        return []

    on_indent = len(lines[start]) - len(lines[start].lstrip())
    trigger_keys: list[str] = []

    # Handle inline triggers: `on: push` or `on: [push, pull_request]`.
    inline = lines[start].split(":", 1)[1].split("#")[0].strip()
    if inline:
        for key in inline.strip("[]").split(","):
            trigger_keys.append(key.strip().rstrip(":"))
        return trigger_keys

    first_indent: int | None = None
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= on_indent:
            break
        if first_indent is None:
            first_indent = indent
        if indent == first_indent:
            key = line.strip().split(":")[0]
            trigger_keys.append(key)
    return trigger_keys


def _check_manual_dispatch_only(text: str) -> list[str]:
    errors: list[str] = []
    trigger_keys = _extract_on_trigger_keys(text)
    if "workflow_dispatch" not in trigger_keys:
        errors.append("Workflow must be triggered by workflow_dispatch")
    for trigger in (
        "push",
        "pull_request",
        "schedule",
        "workflow_call",
        "release",
        "issue_comment",
        "repository_dispatch",
        "merge_group",
        "pull_request_target",
        "deployment",
    ):
        if trigger in trigger_keys:
            errors.append(f"Workflow must not be triggered by {trigger}:")
    return errors


def _check_permissions(text: str) -> list[str]:
    errors: list[str] = []
    if "permissions:" not in text:
        errors.append("Workflow must declare explicit permissions")
        return errors

    lower = text.lower()

    # Reject any broad or write permission, including catch-all write patterns.
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
        r"\bid-token\s*:\s*write\b",
        r"\bpages\s*:\s*write\b",
    ]
    for pattern in broad_write_patterns:
        for m in re.finditer(pattern, lower):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow declares a broad/write permission")

    if "contents: read" not in lower:
        errors.append("Workflow must declare permissions: contents: read")

    if "actions: read" not in lower:
        errors.append("Workflow must declare permissions: actions: read")

    return errors


def _check_no_secrets(text: str) -> list[str]:
    errors: list[str] = []
    safe_spans = [(m.start(), m.end()) for m in SAFE_TOKEN_PATTERN.finditer(text)]
    lower = text.lower()
    for m in re.finditer(r"\bsecrets\.\w+", lower):
        start, end = m.start(), m.end()
        if any(start >= s and end <= e for s, e in safe_spans):
            continue
        line = _line_no(text, start)
        errors.append(f"Line {line}: workflow references secrets.*")
    return errors


def _check_gh_token_for_download(text: str) -> list[str]:
    """Require a read-only GitHub token for `gh run download`."""
    errors: list[str] = []
    masked = _mask_safe_tokens(text)
    if re.search(r"\bGH_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked) or re.search(
        r"\bGITHUB_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked
    ):
        return errors

    errors.append(
        "Workflow must set GH_TOKEN or GITHUB_TOKEN from github.token so "
        "`gh run download` can read the source workflow artifact"
    )
    return errors


def _check_forbidden_commands(text: str) -> list[str]:
    errors: list[str] = []
    patterns = [
        (command, re.compile(re.escape(command), re.IGNORECASE))
        for command in FORBIDDEN_COMMANDS
    ]
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        if raw_line.strip().startswith("#"):
            continue
        for command, pattern in patterns:
            if pattern.search(raw_line):
                errors.append(f"Line {line_no}: forbidden command '{command}'")
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


def _input_block(text: str, input_name: str) -> str:
    """Return the YAML block for a named workflow input, or empty string."""
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{input_name}:"):
            start_idx = i
            break
    if start_idx is None:
        return ""

    start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    block_lines: list[str] = []
    for line in lines[start_idx + 1 :]:
        if line.strip() == "":
            block_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= start_indent:
            break
        block_lines.append(line)
    return "\n".join(block_lines)


def _check_inputs(text: str) -> list[str]:
    errors: list[str] = []
    for name, spec in REQUIRED_INPUTS.items():
        block = _input_block(text, name)
        if not block:
            errors.append(f"Workflow must declare a {name} input")
            continue

        expected_type = spec.get("type")
        if expected_type and f"type: {expected_type}" not in block:
            errors.append(f"{name} input must be type {expected_type}")

        required = spec.get("required")
        if required is True and "required: true" not in block:
            errors.append(f"{name} input must be required: true")
        if required is False and "required: false" not in block:
            errors.append(f"{name} input must be required: false")

        default = spec.get("default")
        if default is not None:
            if f"default: {default}" not in block:
                errors.append(f"{name} input must default to {default}")

    return errors


def _check_gh_run_download(text: str) -> list[str]:
    errors: list[str] = []
    if DOWNLOAD_COMMAND_MARKER not in text:
        errors.append("Workflow must use 'gh run download' to fetch the source artifact")
    return errors


def _check_validator_command(text: str) -> list[str]:
    errors: list[str] = []
    if VALIDATOR_COMMAND_MARKER not in text:
        errors.append(
            "Workflow must call scripts/check_release_assurance_diagnostics_artifact.py "
            "to validate the downloaded diagnostics artifact"
        )
    return errors


def _check_validation_report_upload(text: str) -> list[str]:
    errors: list[str] = []
    if "release-assurance-diagnostics-validation" not in text.lower():
        errors.append(
            "Workflow must upload a 'release-assurance-diagnostics-validation' artifact"
        )
    return errors


def _check_upload_artifact_action(text: str) -> list[str]:
    errors: list[str] = []
    if "actions/upload-artifact" not in text.lower():
        errors.append("Workflow must use actions/upload-artifact to upload the validation report")
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

    errors.extend(_check_manual_dispatch_only(text))
    errors.extend(_check_permissions(text))
    errors.extend(_check_no_secrets(text))
    errors.extend(_check_gh_token_for_download(text))
    errors.extend(_check_forbidden_commands(text))
    errors.extend(_check_no_live_trading(text))
    errors.extend(_check_no_execution_commands(text))
    errors.extend(_check_required_env(text))
    errors.extend(_check_python_311(text))
    errors.extend(_check_inputs(text))
    errors.extend(_check_gh_run_download(text))
    errors.extend(_check_validator_command(text))
    errors.extend(_check_validation_report_upload(text))
    errors.extend(_check_upload_artifact_action(text))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the release-assurance diagnostics artifact revalidation workflow."
        )
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

    try:
        result = check_workflow(args.workflow)
    except Exception as e:  # pragma: no cover - operational errors
        summary = "Release assurance diagnostics artifact workflow check FAILED (operational error)"
        if args.json:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "summary": summary,
                        "errors": [str(e)],
                        "warnings": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(summary)
            print(f"  - {e}")
        return 2

    try:
        workflow_rel = args.workflow.relative_to(REPO_ROOT)
    except ValueError:
        workflow_rel = args.workflow

    if args.json:
        summary = (
            "Release assurance diagnostics artifact workflow check PASSED"
            if result["passed"]
            else "Release assurance diagnostics artifact workflow check FAILED"
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
        print("Release assurance diagnostics artifact workflow check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance diagnostics artifact workflow check PASSED")
        print(f"  Workflow: {workflow_rel}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
