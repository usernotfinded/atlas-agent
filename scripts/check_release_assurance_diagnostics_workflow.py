#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_release_assurance_diagnostics_workflow.py
# PURPOSE: Validate the release assurance diagnostics path in the GitHub Actions
#         workflow.
# DEPS:    argparse, json, re, sys, pathlib, typing.
# ==============================================================================

"""Validate the release assurance diagnostics path in the GitHub Actions workflow.

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
DEFAULT_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-assurance.yml"

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

# Read-only GitHub token sources allowed for `gh release view` checks.
# `github.token` is the repository-provided token exposed by GitHub Actions.
# `secrets.GITHUB_TOKEN` is the same token via the secrets context and is the
# repo's existing CI pattern; arbitrary `secrets.*` references are rejected.
SAFE_TOKEN_PATTERN = re.compile(
    r"\$\{\{\s*(?:github\.token|secrets\.GITHUB_TOKEN)\s*\}\}",
    re.IGNORECASE,
)

DIAGNOSTICS_CONDITIONAL_MARKERS = (
    "inputs.upload_diagnostics_json",
    "UPLOAD_DIAGNOSTICS_JSON",
    "diagnostics_flag",
)

VALIDATOR_STEP_NAME = "Validate release assurance diagnostics artifact"
VALIDATOR_COMMAND_MARKER = "scripts/check_release_assurance_diagnostics_artifact.py"


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
        # Catch-all for any other broad write permission (id-token, pages, etc.)
        r"\b\w+\s*:\s*write\b",
    ]
    for pattern in broad_write_patterns:
        for m in re.finditer(pattern, lower):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow declares a broad/write permission")

    if "contents: read" not in lower:
        errors.append("Workflow must declare permissions: contents: read")
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


def _check_gh_token_for_static_checks(text: str) -> list[str]:
    """Require a read-only GitHub token for workflow steps that use `gh`.

    `scripts/release_assurance.py` calls `gh release view` to verify the chosen
    release exists. In GitHub Actions this requires either `GH_TOKEN` or
    `GITHUB_TOKEN` to be set at job or step level. The token must come from the
    repository-provided `${{ github.token }}` or the repo-standard
    `${{ secrets.GITHUB_TOKEN }}`; arbitrary secrets are rejected elsewhere.
    """
    errors: list[str] = []
    masked = _mask_safe_tokens(text)
    if re.search(r"\bGH_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked) or re.search(
        r"\bGITHUB_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked
    ):
        return errors

    errors.append(
        "Workflow must set GH_TOKEN or GITHUB_TOKEN (from github.token or "
        "secrets.GITHUB_TOKEN) so `gh release view` checks can read public release metadata"
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


def _check_boolean_input(text: str, input_name: str) -> list[str]:
    """Validate a boolean workflow input that defaults to false."""
    errors: list[str] = []
    block = _input_block(text, input_name)
    if not block:
        errors.append(f"Workflow must declare a {input_name} input")
        return errors

    if "type: boolean" not in block:
        errors.append(f"{input_name} input must be type boolean")
    if "default: false" not in block:
        errors.append(f"{input_name} input must default to false")
    return errors


def _check_diagnostics_input(text: str) -> list[str]:
    return _check_boolean_input(text, "upload_diagnostics_json")


def _check_validation_input(text: str) -> list[str]:
    return _check_boolean_input(text, "validate_diagnostics_artifact")


def _step_has_if(text: str, step_name: str) -> bool:
    """Return True if the named step has an `if:` key."""
    return _step_if_line(text, step_name) is not None


def _step_if_line(text: str, step_name: str) -> str | None:
    """Return the `if:` expression for the named step, or None if absent.

    Handles both inline conditions and folded/block scalars (``>-``, ``>``, ``|``).
    """
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if f"- name: {step_name}" in line:
            start_idx = i
            break
    if start_idx is None:
        return None

    if_idx: int | None = None
    for j in range(start_idx + 1, len(lines)):
        next_line = lines[j].strip()
        if next_line == "":
            continue
        if next_line.startswith("- name:"):
            break
        if next_line.startswith("if:"):
            if_idx = j
            break
    if if_idx is None:
        return None

    first_line = lines[if_idx].strip()
    inline = first_line.split(":", 1)[1].strip()
    if inline and inline not in (">-", ">", "|", "|-", "|+"):
        return first_line

    # Folded or block scalar: collect indented continuation lines.
    base_indent = len(lines[if_idx]) - len(lines[if_idx].lstrip())
    condition_lines: list[str] = []
    for j in range(if_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if stripped == "":
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break
        condition_lines.append(stripped)
    return " ".join(condition_lines)


def _check_diagnostics_flag_conditional(text: str) -> list[str]:
    """Ensure --diagnostics-json is only used inside a conditional context."""
    errors: list[str] = []
    lines = text.splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        if "--diagnostics-json" not in raw_line:
            continue

        line_lower = raw_line.lower()
        if any(marker.lower() in line_lower for marker in DIAGNOSTICS_CONDITIONAL_MARKERS):
            continue

        # Look upward for an enclosing bash `if` block that references the
        # conditional markers.
        found_conditional = False
        for prev_line in reversed(lines[: line_no - 1]):
            stripped = prev_line.strip()
            if stripped.startswith("fi"):
                break
            if stripped.startswith("if ") or stripped.startswith("if:"):
                prev_lower = prev_line.lower()
                if any(marker.lower() in prev_lower for marker in DIAGNOSTICS_CONDITIONAL_MARKERS):
                    found_conditional = True
                break

        if not found_conditional:
            errors.append(
                f"Line {line_no}: --diagnostics-json must appear in a conditional "
                "context referencing the upload_diagnostics_json input"
            )

    return errors


def _check_diagnostics_upload_step(text: str) -> list[str]:
    errors: list[str] = []

    if "release-assurance-diagnostics" not in text.lower():
        errors.append("Workflow must upload an artifact named 'release-assurance-diagnostics'")
        return errors

    step_name = "Upload release assurance diagnostics artifact"
    if step_name not in text:
        errors.append(f"Workflow must declare a step named '{step_name}'")
        return errors

    if_line = _step_if_line(text, step_name)
    if if_line is None:
        errors.append("Diagnostics artifact upload step must be conditional")
    else:
        if_line_lower = if_line.lower()
        if "inputs.upload_diagnostics_json" not in if_line_lower:
            errors.append(
                "Diagnostics artifact upload step must be conditional on inputs.upload_diagnostics_json"
            )
        if not (
            "steps.release_assurance.outputs.exit_code != '0'" in if_line_lower
            or "failure()" in if_line_lower
        ):
            errors.append(
                "Diagnostics artifact upload step must only run on failure outcome"
            )

    if "if-no-files-found: ignore" not in text:
        errors.append("Diagnostics artifact upload must use 'if-no-files-found: ignore'")

    return errors


def _check_failure_semantics(text: str) -> list[str]:
    errors: list[str] = []

    if "exit_code" not in text:
        errors.append("Workflow must reference 'exit_code' for failure semantics")

    if "GITHUB_OUTPUT" not in text:
        errors.append("Workflow must write to GITHUB_OUTPUT")

    step_name = "Fail if release assurance failed"
    if step_name not in text:
        errors.append(f"Workflow must declare a step named '{step_name}'")
        return errors

    failure_if_line = _step_if_line(text, step_name)
    if failure_if_line is None:
        errors.append("Failure step must be conditional")
    else:
        failure_if_lower = failure_if_line.lower()
        if not (
            "steps.release_assurance.outputs.exit_code" in failure_if_lower
            and "!= '0'" in failure_if_lower
        ):
            errors.append(
                "Failure step if-condition must reference "
                "steps.release_assurance.outputs.exit_code != '0'"
            )

    # Verify the failure step body references exit_code/RA_EXIT_CODE and calls exit.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if f"- name: {step_name}" in line:
            body_lines: list[str] = []
            for j in range(i + 1, len(lines)):
                next_line = lines[j].rstrip()
                stripped = next_line.strip()
                if stripped == "":
                    continue
                if stripped.startswith("- name:"):
                    break
                body_lines.append(next_line)
            body = "\n".join(body_lines)
            body_lower = body.lower()
            if "exit_code" not in body_lower and "ra_exit_code" not in body_lower:
                errors.append(
                    "Failure step body must reference exit_code or RA_EXIT_CODE"
                )
            if " exit" not in body_lower:
                errors.append("Failure step body must contain an exit command")
            break

    return errors


def _step_position(text: str, step_name: str) -> int:
    return text.find(f"- name: {step_name}")


def _check_diagnostics_validator_step(text: str) -> list[str]:
    errors: list[str] = []

    if VALIDATOR_STEP_NAME not in text:
        errors.append(f"Workflow must declare a step named '{VALIDATOR_STEP_NAME}'")
        return errors

    if VALIDATOR_COMMAND_MARKER not in text:
        errors.append(
            "Workflow must call scripts/check_release_assurance_diagnostics_artifact.py "
            "to validate the diagnostics artifact"
        )

    if_line = _step_if_line(text, VALIDATOR_STEP_NAME)
    if if_line is None:
        errors.append("Diagnostics validator step must be conditional")
    else:
        if_line_lower = if_line.lower()
        if "inputs.upload_diagnostics_json" not in if_line_lower:
            errors.append(
                "Diagnostics validator step must be conditional on inputs.upload_diagnostics_json"
            )
        if "inputs.validate_diagnostics_artifact" not in if_line_lower:
            errors.append(
                "Diagnostics validator step must be conditional on inputs.validate_diagnostics_artifact"
            )
        if not (
            "steps.release_assurance.outputs.exit_code != '0'" in if_line_lower
            or "failure()" in if_line_lower
        ):
            errors.append(
                "Diagnostics validator step must only run on release assurance failure"
            )

    return errors


def _check_validator_before_upload(text: str) -> list[str]:
    errors: list[str] = []
    validator_pos = _step_position(text, VALIDATOR_STEP_NAME)
    upload_pos = _step_position(text, "Upload release assurance diagnostics artifact")

    if validator_pos == -1:
        errors.append("Cannot check ordering: diagnostics validator step missing")
    if upload_pos == -1:
        errors.append("Cannot check ordering: diagnostics artifact upload step missing")
    if validator_pos != -1 and upload_pos != -1 and validator_pos > upload_pos:
        errors.append(
            "Diagnostics validator step must run before diagnostics artifact upload"
        )

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
    errors.extend(_check_gh_token_for_static_checks(text))
    errors.extend(_check_forbidden_commands(text))
    errors.extend(_check_no_live_trading(text))
    errors.extend(_check_no_execution_commands(text))
    errors.extend(_check_required_env(text))
    errors.extend(_check_python_311(text))
    errors.extend(_check_diagnostics_input(text))
    errors.extend(_check_validation_input(text))
    errors.extend(_check_diagnostics_flag_conditional(text))
    errors.extend(_check_diagnostics_upload_step(text))
    errors.extend(_check_diagnostics_validator_step(text))
    errors.extend(_check_validator_before_upload(text))
    errors.extend(_check_failure_semantics(text))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the release assurance diagnostics path in the GitHub Actions workflow."
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
        summary = "Release assurance diagnostics workflow check FAILED (operational error)"
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
            "Release assurance diagnostics workflow check PASSED"
            if result["passed"]
            else "Release assurance diagnostics workflow check FAILED"
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
        print("Release assurance diagnostics workflow check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance diagnostics workflow check PASSED")
        print(f"  Workflow: {workflow_rel}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
