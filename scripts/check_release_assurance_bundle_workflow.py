#!/usr/bin/env python3
"""Validate the release assurance bundle demo path in the GitHub Actions workflow.

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

EXECUTION_COMMAND_PATTERNS = [
    re.compile(r"\batlas\s+run\b", re.IGNORECASE),
    re.compile(r"\batlas\s+backtest\b", re.IGNORECASE),
    re.compile(r"\batlas\s+discipline\b", re.IGNORECASE),
    re.compile(r"\batlas\s+live\b", re.IGNORECASE),
    re.compile(r"\batlas\s+submit\b", re.IGNORECASE),
]

DEMO_SCRIPT = "scripts/demo_release_assurance_snapshot_bundle.sh"
MANIFEST_CHECK_SCRIPT = "scripts/check_release_assurance_bundle_manifest.py"


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


# Read-only GitHub token sources allowed for `gh release view` checks.
# `github.token` is the repository-provided token exposed by GitHub Actions.
# `secrets.GITHUB_TOKEN` is the same token via the secrets context and is the
# repo's existing CI pattern; arbitrary `secrets.*` references are rejected.
SAFE_TOKEN_SOURCES = ("github.token", "secrets.GITHUB_TOKEN")
SAFE_TOKEN_PATTERN = re.compile(
    r"\$\{\{\s*(?:github\.token|secrets\.GITHUB_TOKEN)\s*\}\}",
    re.IGNORECASE,
)


def _mask_safe_tokens(text: str) -> str:
    """Replace allowed read-only token expressions with a placeholder."""
    return SAFE_TOKEN_PATTERN.sub("__SAFE_GITHUB_TOKEN__", text)


def _check_no_secrets(text: str) -> list[str]:
    errors: list[str] = []
    masked = _mask_safe_tokens(text)
    lower = masked.lower()
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


def _check_gh_token_for_static_checks(text: str) -> list[str]:
    """Require a read-only GitHub token for workflow steps that use `gh`.

    `scripts/check_v0611_release_prep.py --post-release` and
    `scripts/release_assurance.py` call `gh release view` to verify the chosen
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


def _check_python_311(text: str) -> list[str]:
    errors: list[str] = []
    if "3.11" not in text:
        errors.append("Workflow must use Python 3.11")
    return errors


def _check_bundle_demo_input(text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().startswith("run_bundle_demo:"):
            start_idx = i
            break
    if start_idx is None:
        errors.append("Workflow must declare a run_bundle_demo input")
        return errors

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
    block = "\n".join(block_lines)

    if "type: boolean" not in block:
        errors.append("run_bundle_demo input must be type boolean")
    if "default: false" not in block:
        errors.append("run_bundle_demo input must default to false")
    return errors


def _step_has_if(text: str, step_name: str) -> bool:
    """Return True if the named step has an `if:` key."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if f"- name: {step_name}" in line:
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if next_line == "":
                    continue
                if next_line.startswith("- name:"):
                    break
                if next_line.startswith("if:"):
                    return True
            break
    return False


def _check_bundle_demo_steps(text: str) -> list[str]:
    errors: list[str] = []

    if DEMO_SCRIPT not in text:
        errors.append(f"Workflow must reference '{DEMO_SCRIPT}'")

    if MANIFEST_CHECK_SCRIPT not in text:
        errors.append(f"Workflow must reference '{MANIFEST_CHECK_SCRIPT}'")

    if "release-assurance-bundle-demo" not in text.lower():
        errors.append("Workflow must upload an artifact named 'release-assurance-bundle-demo'")

    demo_idx = text.find(DEMO_SCRIPT)
    manifest_idx = text.find(MANIFEST_CHECK_SCRIPT)
    artifact_name_idx = text.lower().find("release-assurance-bundle-demo")

    if demo_idx != -1:
        if not _step_has_if(text, "Run release assurance bundle demo"):
            errors.append("Bundle demo script step must be conditional on inputs.run_bundle_demo")

    if manifest_idx != -1:
        if not _step_has_if(text, "Validate release assurance bundle manifest"):
            errors.append("Manifest checker step must be conditional on inputs.run_bundle_demo")

    if artifact_name_idx != -1:
        if not _step_has_if(text, "Upload release assurance bundle demo artifact"):
            errors.append("Bundle demo artifact upload step must be conditional on inputs.run_bundle_demo")

    # Manifest checker must run before artifact upload.
    if manifest_idx != -1 and artifact_name_idx != -1:
        if manifest_idx > artifact_name_idx:
            errors.append("Manifest checker must run before the bundle demo artifact upload")

    # Demo script must run before manifest checker.
    if demo_idx != -1 and manifest_idx != -1:
        if demo_idx > manifest_idx:
            errors.append("Bundle demo script must run before the manifest checker")

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
    errors.extend(_check_gh_token_for_static_checks(text))
    errors.extend(_check_forbidden_commands(text))
    errors.extend(_check_no_live_trading(text))
    errors.extend(_check_no_execution_commands(text))
    errors.extend(_check_required_env(text))
    errors.extend(_check_python_311(text))
    errors.extend(_check_bundle_demo_input(text))
    errors.extend(_check_bundle_demo_steps(text))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the release assurance bundle demo path in the GitHub Actions workflow."
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
            "Release assurance bundle workflow check PASSED"
            if result["passed"]
            else "Release assurance bundle workflow check FAILED"
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
        print("Release assurance bundle workflow check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance bundle workflow check PASSED")
        print(f"  Workflow: {workflow_rel}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
