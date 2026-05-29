#!/usr/bin/env python3
"""Deterministic reviewer golden-path smoke test.

Creates a temporary workspace outside the repo, runs the safe onboarding
command sequence, and verifies that each step exits cleanly. This script
does not call providers, brokers, or network endpoints, and it does not
load credentials or modify the repo.

Usage:
    python3.11 scripts/smoke_reviewer_golden_path.py
    python3.11 scripts/smoke_reviewer_golden_path.py --json
    python3.11 scripts/smoke_reviewer_golden_path.py --keep-temp
    python3.11 scripts/smoke_reviewer_golden_path.py --skip-release-check
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_BIN = os.environ.get("PYTHON_BIN", sys.executable)
SAMPLE_DATA = REPO_ROOT / "data" / "sample" / "ohlcv.csv"
DEMO_SYMBOL = os.environ.get("DEMO_SYMBOL", "DEMO-SYMBOL")

# Commands to run inside the temp workspace after init
_GOLDEN_PATH_COMMANDS: list[list[str]] = [
    ["discipline", "setup", "--manual", "--yes"],
    ["config", "set", "market.symbol", DEMO_SYMBOL],
    ["validate"],
    ["backtest", "run", "--data", str(SAMPLE_DATA), "--symbol", DEMO_SYMBOL, "--json"],
    ["research", "run", "--symbol", DEMO_SYMBOL, "--json"],
    ["research", "summary", "--json"],
    ["memory", "doctor", "--json"],
    ["events", "doctor"],
]

# Diagnostic category and suggested fix for each step
_STEP_DIAGNOSTICS: dict[str, tuple[str, str]] = {
    "atlas --help": (
        "install",
        "Check that Python and the repo src/ are on PYTHONPATH. Try: python3.11 -m atlas_agent.cli --help",
    ),
    "atlas init": (
        "install",
        "Check that template files exist under src/atlas_agent/templates/ and that the temp directory is writable.",
    ),
    "discipline": (
        "config",
        "Check that discipline profile files exist under configs/ and that the workspace is initialized.",
    ),
    "config set": (
        "config",
        "Check that the workspace .atlas/ directory exists and is writable.",
    ),
    "validate": (
        "validate",
        "Check that required config files (market.yaml, strategy.yaml) are present in the workspace.",
    ),
    "backtest": (
        "backtest",
        "Check that sample data exists at data/sample/ohlcv.csv and that market.symbol is configured.",
    ),
    "research run": (
        "research",
        "Check that research artifacts directory exists and that the provider config is valid.",
    ),
    "research summary": (
        "research",
        "Check that a research session was created successfully before running summary.",
    ),
    "memory doctor": (
        "memory",
        "Check that the memory directory exists and that SQLite FTS5 is available.",
    ),
    "events doctor": (
        "audit",
        "Check that the events directory exists and is writable.",
    ),
    "release_check.sh": (
        "release",
        "Run ./scripts/release_check.sh --quick manually to see which sub-check failed.",
    ),
}


def _get_diagnostic(command: str) -> tuple[str, str]:
    """Return (category, suggestion) for a given command string."""
    for prefix, (category, suggestion) in _STEP_DIAGNOSTICS.items():
        if prefix in command:
            return category, suggestion
    return "unknown", "Review the command output and workspace state for clues."



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redact(text: str, temp_path: Path) -> str:
    """Redact absolute temp paths and common secret-like patterns from output."""
    redacted = text.replace(str(temp_path), "<TEMP_WORKSPACE>")
    redacted = redacted.replace(str(temp_path.resolve()), "<TEMP_WORKSPACE>")
    redacted = redacted.replace(str(REPO_ROOT), "<REPO_ROOT>")
    # Redact any line that looks like an API key or credential
    lines = []
    for line in redacted.splitlines(keepends=True):
        lower = line.lower()
        if any(k in lower for k in ("api_key", "apikey", "secret", "password", "token")):
            # Keep the label but redact the value
            if ":" in line:
                label, _ = line.rsplit(":", 1)
                lines.append(f"{label}: <REDACTED>\n")
            else:
                lines.append("<REDACTED>\n")
        else:
            lines.append(line)
    return "".join(lines)


def _run_atlas(
    args: list[str],
    cwd: Path,
    env: dict[str, str],
) -> tuple[int, str, str]:
    """Run atlas via the local module. Returns (returncode, stdout, stderr)."""
    cmd = [PYTHON_BIN, "-m", "atlas_agent.cli", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _init_workspace(temp_path: Path, env: dict[str, str]) -> tuple[int, str, str]:
    """Initialize the workspace."""
    return _run_atlas(
        ["init", str(temp_path), "--template", "routine-trader"],
        cwd=REPO_ROOT,
        env=env,
    )


def _help_check(env: dict[str, str]) -> tuple[int, str, str]:
    """Run atlas --help from repo root."""
    return _run_atlas(["--help"], cwd=REPO_ROOT, env=env)


# ---------------------------------------------------------------------------
# Main smoke logic
# ---------------------------------------------------------------------------


def _smoke(
    *,
    keep_temp: bool,
    skip_release_check: bool,
) -> dict[str, Any]:
    env = {
        **dict(os.environ),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ATLAS_CI": "1",
    }

    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    temp_path: Path | None = None

    # --help sanity check (from repo root, no workspace needed)
    rc, out, err = _help_check(env)
    category, suggestion = _get_diagnostic("atlas --help")
    steps.append(
        {
            "command": "atlas --help",
            "returncode": rc,
            "ok": rc == 0,
            "category": category,
            "suggestion": suggestion,
        }
    )
    if rc != 0:
        errors.append(f"[install] atlas --help failed with exit code {rc}. {suggestion}")

    # Create temp workspace
    temp_path = Path(tempfile.mkdtemp(prefix="atlas-smoke-"))

    try:
        rc, out, err = _init_workspace(temp_path, env)
        category, suggestion = _get_diagnostic("atlas init")
        steps.append(
            {
                "command": _redact(f"atlas init {temp_path.name} --template routine-trader", temp_path),
                "returncode": rc,
                "ok": rc == 0,
                "category": category,
                "suggestion": suggestion,
            }
        )
        if rc != 0:
            errors.append(f"[{category}] atlas init failed with exit code {rc}. {suggestion}")
            # Short-circuit: without a workspace the rest will fail
            return {
                "passed": False,
                "errors": errors,
                "steps": steps,
                "temp_workspace": str(temp_path),
                "keep_temp": keep_temp,
            }

        # Run golden-path commands inside the workspace
        for args in _GOLDEN_PATH_COMMANDS:
            rc, out, err = _run_atlas(args, cwd=temp_path, env=env)
            cmd_str = _redact("atlas " + " ".join(args), temp_path)
            ok = rc == 0
            category, suggestion = _get_diagnostic(cmd_str)
            step: dict[str, Any] = {
                "command": cmd_str,
                "returncode": rc,
                "ok": ok,
                "category": category,
                "suggestion": suggestion,
            }
            steps.append(step)
            if not ok:
                errors.append(f"[{category}] {cmd_str} failed with exit code {rc}. {suggestion}")

        # Optional release check from repo root
        if not skip_release_check:
            rc, out, err = subprocess.run(
                ["./scripts/release_check.sh", "--quick"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            ).returncode, "", ""
            category, suggestion = _get_diagnostic("release_check.sh")
            steps.append(
                {
                    "command": "./scripts/release_check.sh --quick",
                    "returncode": rc,
                    "ok": rc == 0,
                    "category": category,
                    "suggestion": suggestion,
                }
            )
            if rc != 0:
                errors.append(f"[{category}] release_check.sh --quick failed with exit code {rc}. {suggestion}")

    finally:
        if not keep_temp and temp_path is not None and temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "steps": steps,
        "temp_workspace": str(temp_path) if (keep_temp and temp_path is not None) else None,
        "keep_temp": keep_temp,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reviewer golden-path smoke test for Atlas Agent"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve the temporary workspace after the run",
    )
    parser.add_argument(
        "--skip-release-check",
        action="store_true",
        help="Skip the release_check.sh --quick step (faster local iteration)",
    )
    args = parser.parse_args()

    result = _smoke(
        keep_temp=args.keep_temp,
        skip_release_check=args.skip_release_check,
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("=" * 60)
        print("Reviewer Golden-Path Smoke Test")
        print("=" * 60)
        for step in result["steps"]:
            status = "OK" if step["ok"] else "FAIL"
            cat = step.get("category", "unknown")
            print(f"  [{status}] [{cat}] {step['command']} (exit {step['returncode']})")
        if result["errors"]:
            print("-" * 60)
            print("Errors:")
            for e in result["errors"]:
                print(f"  - {e}")
            print("-" * 60)
            print("Diagnostics: each error above includes a category and suggested fix.")
            print("Run the failing command in isolation to see full output.")
        print("=" * 60)
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"Result: {status}")
        if result["temp_workspace"]:
            print(f"Temp workspace kept at: {result['temp_workspace']}")
        print("=" * 60)

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
