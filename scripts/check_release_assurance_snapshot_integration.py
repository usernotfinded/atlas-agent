#!/usr/bin/env python3
"""Validate the reviewer trust snapshot integration in release assurance.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or invoke broker/provider execution.

Exit codes:
  0 = integration check passed
  1 = blocking findings or operational error (e.g., missing script)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE_SCRIPT = "scripts/release_assurance.py"
BUILD_SCRIPT = "scripts/build_reviewer_trust_snapshot.py"
CHECK_SCRIPT = "scripts/check_reviewer_trust_snapshot.py"
WORKFLOW_FILE = ".github/workflows/release-assurance.yml"

SNAPSHOT_FLAG = "--include-reviewer-trust-snapshot"
SNAPSHOT_ATTR = "include_reviewer_trust_snapshot"
SNAPSHOT_MODULES = {
    "build_reviewer_trust_snapshot",
    "check_reviewer_trust_snapshot",
}
SNAPSHOT_FUNCS = {"build_snapshot", "run_checks"}

UNSAFE_COMMAND_PREFIXES = [
    "git push",
    "git tag ",
    "gh release create",
    "gh release upload",
    "twine upload",
]

BROKER_PROVIDER_LIVE_RE = re.compile(
    r"\b(broker|provider|live_trading|live_submit|submit_order|call_broker|"
    r"call_provider|execute_live|enable_live)\b",
    re.IGNORECASE,
)

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}",
        re.IGNORECASE,
    ),
]


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _find_main_function(tree: ast.AST) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    return None


def _has_snapshot_flag_argument(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == SNAPSHOT_FLAG:
                    return True
    return False


def _is_snapshot_flag_test(test: ast.AST) -> bool:
    names: set[str] = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return SNAPSHOT_ATTR in names


def _find_snapshot_if_nodes(main_func: ast.FunctionDef) -> list[ast.If]:
    return [
        node
        for node in ast.walk(main_func)
        if isinstance(node, ast.If) and _is_snapshot_flag_test(node.test)
    ]


def _is_snapshot_call(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in SNAPSHOT_FUNCS:
            return True
        if isinstance(func, ast.Name) and func.id in SNAPSHOT_FUNCS:
            return True
    return False


def _is_snapshot_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name in SNAPSHOT_MODULES for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.module in SNAPSHOT_MODULES
    return False


def _collect_command_strings(tree: ast.AST) -> list[str]:
    commands: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            func_name: str | None = None
            func = node.func
            if isinstance(func, ast.Attribute):
                func_name = func.attr
            elif isinstance(func, ast.Name):
                func_name = func.id
            if func_name in {"run_cmd", "run", "call", "Popen", "check_call"}:
                first = node.args[0]
                if isinstance(first, ast.List):
                    parts: list[str] = []
                    ok = True
                    for elt in first.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            parts.append(elt.value)
                        else:
                            ok = False
                            break
                    if ok and parts:
                        commands.append(" ".join(parts))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            commands.append(node.value)
    return commands


def _is_unsafe_command(command: str) -> bool:
    lower = command.lower()
    for unsafe in UNSAFE_COMMAND_PREFIXES:
        if not lower.startswith(unsafe):
            continue
        if unsafe == "git tag " and "-l" in lower.split():
            continue
        return True
    return False


def _check_workflow(repo_root: Path) -> list[str]:
    """Validate the release-assurance workflow if it exists."""
    errors: list[str] = []
    path = repo_root / WORKFLOW_FILE
    if not path.exists():
        return errors

    try:
        text = _read(path)
    except OSError as e:
        errors.append(f"Could not read {WORKFLOW_FILE}: {e}")
        return errors

    if "workflow_dispatch" not in text:
        errors.append(f"{WORKFLOW_FILE} is not triggered by workflow_dispatch")

    if "include_reviewer_trust_snapshot" in text:
        if "type: boolean" not in text:
            errors.append(
                f"{WORKFLOW_FILE} input include_reviewer_trust_snapshot must be type boolean"
            )
        if "default: false" not in text:
            errors.append(
                f"{WORKFLOW_FILE} input include_reviewer_trust_snapshot must default to false"
            )

    if re.search(r"\bsecrets\.", text):
        errors.append(f"{WORKFLOW_FILE} references secrets")

    if "contents: write" in text:
        errors.append(f"{WORKFLOW_FILE} must not use contents: write")
    elif "contents: read" not in text:
        errors.append(f"{WORKFLOW_FILE} must use contents: read")

    lower = text.lower()
    for unsafe in UNSAFE_COMMAND_PREFIXES:
        if unsafe in lower:
            errors.append(f"{WORKFLOW_FILE} contains unsafe command: {unsafe}")

    return errors


def _check_script_exists(repo_root: Path, rel_path: str) -> list[str]:
    errors: list[str] = []
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"Required script missing: {rel_path}")
    return errors


def check_release_assurance_snapshot_integration(
    repo_root: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_script_exists(repo_root, BUILD_SCRIPT))
    errors.extend(_check_script_exists(repo_root, CHECK_SCRIPT))
    errors.extend(_check_workflow(repo_root))

    release_assurance_path = repo_root / RELEASE_ASSURANCE_SCRIPT
    if not release_assurance_path.exists():
        errors.append(f"Required script missing: {RELEASE_ASSURANCE_SCRIPT}")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
        }

    try:
        source = _read(release_assurance_path)
    except OSError as e:
        errors.append(f"Could not read {RELEASE_ASSURANCE_SCRIPT}: {e}")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Syntax error in {RELEASE_ASSURANCE_SCRIPT}: {e}")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
        }

    if not _has_snapshot_flag_argument(tree):
        errors.append(f"{RELEASE_ASSURANCE_SCRIPT} does not expose {SNAPSHOT_FLAG}")

    main_func = _find_main_function(tree)
    if main_func is None:
        errors.append(f"{RELEASE_ASSURANCE_SCRIPT} has no main() function")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
        }

    snapshot_ifs = _find_snapshot_if_nodes(main_func)
    if not snapshot_ifs:
        errors.append(
            f"{RELEASE_ASSURANCE_SCRIPT} does not conditionally invoke the "
            "reviewer trust snapshot using "
            f"args.{SNAPSHOT_ATTR}"
        )

    parent_map = _build_parent_map(main_func)
    snapshot_if_ids = {id(if_node) for if_node in snapshot_ifs}

    def _inside_snapshot_if(node: ast.AST) -> bool:
        current: ast.AST | None = node
        while current is not None:
            current = parent_map.get(current)
            if current is not None and id(current) in snapshot_if_ids:
                return True
        return False

    for node in ast.walk(main_func):
        if _is_snapshot_call(node) or _is_snapshot_import(node):
            if not snapshot_ifs:
                errors.append(
                    "Snapshot function call or import found outside the "
                    "conditional opt-in block"
                )
                break
            if not _inside_snapshot_if(node):
                errors.append(
                    "Snapshot function call or import is not inside the "
                    f"args.{SNAPSHOT_ATTR} conditional block"
                )
                break

    for command in _collect_command_strings(tree):
        if _is_unsafe_command(command):
            errors.append(
                f"{RELEASE_ASSURANCE_SCRIPT} contains unsafe command: {command!r}"
            )

    if snapshot_ifs:
        source_lines = source.splitlines()
        for if_node in snapshot_ifs:
            segment = "\n".join(source_lines[if_node.lineno - 1 : if_node.end_lineno])
            for pattern in SECRET_PATTERNS:
                for match in pattern.finditer(segment):
                    errors.append(
                        "Secret-like reference in the reviewer trust snapshot "
                        f"integration path: {match.group(0)[:40]}"
                    )
            if BROKER_PROVIDER_LIVE_RE.search(segment):
                errors.append(
                    "Reviewer trust snapshot integration path contains a "
                    "broker/provider/live execution reference"
                )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the reviewer trust snapshot integration in "
        "release assurance. Static and local-only."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to validate. Defaults to the current repository.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    result = check_release_assurance_snapshot_integration(repo_root=args.repo_root)

    if args.json:
        summary = (
            "Release assurance snapshot integration check PASSED"
            if result["passed"]
            else "Release assurance snapshot integration check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
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
        print("Release assurance snapshot integration check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance snapshot integration check PASSED")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
