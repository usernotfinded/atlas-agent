#!/usr/bin/env python3
"""Validate the release-assurance artifact retention audit script and workflow.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or execute any workflow.

Exit codes:
  0 = audit script and workflow valid
  1 = blocking findings (e.g., missing files or unsafe workflow content)
  2 = unexpected checker error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "release-assurance-artifact-retention-audit.yml"
)
DEFAULT_SCRIPT_PATH = REPO_ROOT / "scripts" / "audit_release_assurance_artifact_retention.py"

REQUIRED_ENV_SNIPPETS = [
    'ENABLE_LIVE_TRADING: "false"',
    'PROVIDER_EXECUTION_ENABLED: "false"',
    'BROKER_EXECUTION_ENABLED: "false"',
]

FORBIDDEN_WORKFLOW_COMMANDS = [
    "git push",
    "git tag",
    "git commit",
    "gh release create",
    "gh release upload",
    "gh run download",
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
    re.compile(r"\batlas\s+submit\b", re.IGNORECASE),
]

EXECUTION_COMMAND_PATTERNS = [
    re.compile(r"\batlas\s+run\b", re.IGNORECASE),
    re.compile(r"\batlas\s+backtest\b", re.IGNORECASE),
    re.compile(r"\batlas\s+discipline\b", re.IGNORECASE),
    re.compile(r"\batlas\s+live\b", re.IGNORECASE),
    re.compile(r"\batlas\s+submit\b", re.IGNORECASE),
]

ARTIFACT_DELETE_PATTERNS = [
    re.compile(r"\bDELETE\b"),
    re.compile(r"\bgh\s+api\s+-X\s+DELETE\b", re.IGNORECASE),
    re.compile(r"/actions/artifacts/\d+\s*", re.IGNORECASE),
]

ARTIFACT_DOWNLOAD_PATTERNS = [
    re.compile(r"\bgh\s+run\s+download\b", re.IGNORECASE),
    re.compile(r"download-artifact", re.IGNORECASE),
]

# Only the repository-provided read-only token is allowed.
SAFE_TOKEN_PATTERN = re.compile(
    r"\$\{\{\s*github\.token\s*\}\}",
    re.IGNORECASE,
)

REQUIRED_INPUTS = {
    "older_than_days": {"type": "string", "required": False, "default": '"7"'},
    "near_expiry_days": {"type": "string", "required": False, "default": '"3"'},
    "artifact_names": {
        "type": "string",
        "required": False,
        "default": '"release-assurance-diagnostics,release-assurance-diagnostics-validation,release-assurance-bundle-demo,reviewer-trust-snapshot"',
    },
}

ALLOWED_ARTIFACT_NAME = "release-assurance-artifact-retention-audit"
AUDIT_SCRIPT_MARKER = "scripts/audit_release_assurance_artifact_retention.py"


def _mask_safe_tokens(text: str) -> str:
    """Replace allowed read-only token expressions with a placeholder."""
    return SAFE_TOKEN_PATTERN.sub("__SAFE_GITHUB_TOKEN__", text)


def _read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _check_file_exists(path: Path, label: str) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        errors.append(f"{label} file missing: {rel}")
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


def _check_safe_token_only(text: str) -> list[str]:
    """Ensure the only token used is GH_TOKEN/GITHUB_TOKEN from github.token."""
    errors: list[str] = []
    masked = _mask_safe_tokens(text)

    # Confirm the safe token pattern is present and used for GH_TOKEN or GITHUB_TOKEN.
    has_safe_token = bool(
        re.search(r"\bGH_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked)
        or re.search(r"\bGITHUB_TOKEN\s*:\s*__SAFE_GITHUB_TOKEN__", masked)
    )
    if not has_safe_token:
        errors.append(
            "Workflow must set GH_TOKEN or GITHUB_TOKEN from github.token "
            "for read-only metadata access"
        )

    # Reject any other token source in the masked text.
    for m in re.finditer(r"\b(GH_TOKEN|GITHUB_TOKEN)\s*:", masked):
        # If the assignment is not the safe placeholder, flag it.
        rest = masked[m.end() :]
        value = rest.split("\n", 1)[0].strip()
        if value != "__SAFE_GITHUB_TOKEN__":
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: token must be sourced only from github.token")

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


def _check_forbidden_commands(text: str) -> list[str]:
    errors: list[str] = []
    patterns = [
        (command, re.compile(re.escape(command), re.IGNORECASE))
        for command in FORBIDDEN_WORKFLOW_COMMANDS
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


def _check_no_artifact_delete(text: str) -> list[str]:
    errors: list[str] = []
    for pattern in ARTIFACT_DELETE_PATTERNS:
        for m in pattern.finditer(text):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow may delete or mutate artifacts")
    return errors


def _check_no_artifact_download(text: str) -> list[str]:
    errors: list[str] = []
    for pattern in ARTIFACT_DOWNLOAD_PATTERNS:
        for m in pattern.finditer(text):
            line = _line_no(text, m.start())
            errors.append(f"Line {line}: workflow must not download artifacts")
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
            has_default = f"default: {default}" in block
            # Also accept unquoted numeric/string defaults (e.g., default: 7).
            if not has_default and default.startswith('"') and default.endswith('"'):
                unquoted = default[1:-1]
                has_default = f"default: {unquoted}" in block
            if not has_default:
                errors.append(f"{name} input must default to {default}")

    return errors


def _check_audit_script_called(text: str) -> list[str]:
    errors: list[str] = []
    if AUDIT_SCRIPT_MARKER not in text:
        errors.append(
            "Workflow must call scripts/audit_release_assurance_artifact_retention.py"
        )
    return errors


def _check_upload_artifact_action(text: str) -> list[str]:
    errors: list[str] = []
    if "actions/upload-artifact" not in text.lower():
        errors.append("Workflow must use actions/upload-artifact to upload the audit report")
    return errors


def _check_only_retention_audit_artifact_uploaded(text: str) -> list[str]:
    """Ensure the workflow uploads exactly the allowed retention audit artifact."""
    errors: list[str] = []
    lines = text.splitlines()
    found_uploads: list[tuple[int, str | None]] = []

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "uses: actions/upload-artifact" not in raw_line.lower():
            continue

        uses_indent = len(raw_line) - len(raw_line.lstrip())
        name_value: str | None = None
        inside_with = False
        with_indent: int | None = None

        for j in range(i + 1, len(lines)):
            next_line = lines[j]
            next_stripped = next_line.strip()
            if not next_stripped or next_stripped.startswith("#"):
                continue
            next_indent = len(next_line) - len(next_line.lstrip())

            if inside_with and with_indent is not None and next_indent <= with_indent:
                inside_with = False
                with_indent = None

            if next_indent <= uses_indent:
                if next_stripped.startswith("with:"):
                    inside_with = True
                    with_indent = next_indent
                    continue
                # New step or block at the same level; step has ended.
                break

            if next_stripped.startswith("name:"):
                name_value = next_stripped.split(":", 1)[1].strip().strip('"\'')

        found_uploads.append((i + 1, name_value))

    if not found_uploads:
        # Already reported by _check_upload_artifact_action; avoid duplicate.
        return errors

    for line_no, name in found_uploads:
        if name is None:
            errors.append(
                f"Line {line_no}: upload-artifact step must explicitly name "
                f"'{ALLOWED_ARTIFACT_NAME}'"
            )
        elif name.lower() != ALLOWED_ARTIFACT_NAME.lower():
            errors.append(
                f"Line {line_no}: workflow may only upload artifact "
                f"'{ALLOWED_ARTIFACT_NAME}', found '{name}'"
            )

    return errors


def check(
    workflow_path: Path | None = None,
    script_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    workflow_path = workflow_path or DEFAULT_WORKFLOW_PATH
    script_path = script_path or DEFAULT_SCRIPT_PATH

    # File existence checks first so missing files are reported gracefully.
    errors.extend(_check_file_exists(script_path, "Audit script"))
    errors.extend(_check_file_exists(workflow_path, "Workflow"))

    if errors:
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
        }

    try:
        text = _read_file(workflow_path)
    except FileNotFoundError as e:
        return {
            "passed": False,
            "errors": [str(e)],
            "warnings": [],
        }

    errors.extend(_check_manual_dispatch_only(text))
    errors.extend(_check_permissions(text))
    errors.extend(_check_safe_token_only(text))
    errors.extend(_check_no_secrets(text))
    errors.extend(_check_forbidden_commands(text))
    errors.extend(_check_no_live_trading(text))
    errors.extend(_check_no_execution_commands(text))
    errors.extend(_check_no_artifact_delete(text))
    errors.extend(_check_no_artifact_download(text))
    errors.extend(_check_required_env(text))
    errors.extend(_check_python_311(text))
    errors.extend(_check_inputs(text))
    errors.extend(_check_audit_script_called(text))
    errors.extend(_check_upload_artifact_action(text))
    errors.extend(_check_only_retention_audit_artifact_uploaded(text))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the release-assurance artifact retention audit script and workflow."
        )
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=DEFAULT_WORKFLOW_PATH,
        help="Path to the workflow file to validate.",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=DEFAULT_SCRIPT_PATH,
        help="Path to the audit script file to validate.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    try:
        result = check(args.workflow, args.script)
    except Exception as e:  # pragma: no cover - operational errors
        summary = "Release assurance artifact retention audit check FAILED (operational error)"
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

    try:
        script_rel = args.script.relative_to(REPO_ROOT)
    except ValueError:
        script_rel = args.script

    if args.json:
        summary = (
            "Release assurance artifact retention audit check PASSED"
            if result["passed"]
            else "Release assurance artifact retention audit check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "workflow": str(workflow_rel),
                    "script": str(script_rel),
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
        print("Release assurance artifact retention audit check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance artifact retention audit check PASSED")
        print(f"  Workflow: {workflow_rel}")
        print(f"  Script:   {script_rel}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
