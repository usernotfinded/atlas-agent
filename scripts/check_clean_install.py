#!/usr/bin/env python3
"""Verify clean install of the current repo without credentials or network by default.

Default mode uses the current worktree (``--from-current-worktree``), creates a
temporary virtual environment, and installs the package in editable mode without
accessing PyPI. No network calls, no credentials, no broker/provider contact,
no live trading enablement.

Exit codes:
    0 - clean install verification passed
    1 - CLI argument or setup error
    2 - verification failure
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# Expected package version (PEP 440).
EXPECTED_PACKAGE_VERSION = "0.6.7"

# Safety phrases expected in ``atlas validate`` output when run without config.
EXPECTED_VALIDATE_PHRASES = (
    "not ready",
    "risk gates",
)

EXPECTED_TEMPLATE_FILES = (
    "README.md",
    ".env.example",
    "configs/market.example.yaml",
    "memory/portfolio.md",
    "routines/prompts/pre_market.md",
    "skills/risk_review.md",
)

# Fragments indicating local absolute paths that must not leak.
FORBIDDEN_OUTPUT_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "/var/folders/",
    "/tmp/",
    "/var/tmp/",
)

# Network tools the script must not invoke.
NETWORK_TOOLS = ("curl", "wget", "git clone", "git fetch", "git pull")


def _error(msg: str) -> int:
    print(f"ERROR: {_redact(msg)}", file=sys.stderr)
    return 2


_CURRENT_TEMP_DIR: str | None = None


def _redact(text: str) -> str:
    """Redact user-specific absolute paths from output."""
    # Order matters: replace most specific first
    replacements: list[tuple[str, str]] = []
    if _CURRENT_TEMP_DIR is not None:
        replacements.append((_CURRENT_TEMP_DIR, "<temp>"))
    home = str(Path.home())
    if home != "/":
        replacements.append((home, "~"))
    repo = str(REPO_ROOT)
    replacements.append((repo, "<repo>"))
    # Generic temp prefixes
    for prefix in ("/var/folders/", "/private/var/", "/tmp/", "/var/tmp/"):
        replacements.append((prefix, "<temp>/"))
    # Redact any remaining /Users/ references
    replacements.append(("/Users/", "<home>/"))
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    kwargs: dict = {"cwd": cwd, "text": True}
    if capture:
        kwargs["capture_output"] = True
    if env is not None:
        kwargs["env"] = env
    return subprocess.run(cmd, **kwargs)


def _check_forbidden_in_output(text: str) -> list[str]:
    violations: list[str] = []
    for frag in FORBIDDEN_OUTPUT_FRAGMENTS:
        if frag in text:
            violations.append(f"Forbidden fragment '{frag}' found in output")
    return violations


def _find_venv_python(venv_dir: Path) -> Path:
    """Locate the python executable inside a venv."""
    candidates = [
        venv_dir / "bin" / "python",
        venv_dir / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    raise FileNotFoundError(f"Could not find python in venv: {venv_dir}")


def _find_venv_atlas(venv_dir: Path) -> Path:
    """Locate the installed atlas console entrypoint inside a venv."""
    candidates = [
        venv_dir / "bin" / "atlas",
        venv_dir / "Scripts" / "atlas.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    raise FileNotFoundError(f"Could not find atlas entrypoint in venv: {venv_dir}")


def _check_atlas_help(atlas_bin: Path) -> tuple[bool, str]:
    result = _run([str(atlas_bin), "--help"])
    if result.returncode != 0:
        return False, f"atlas --help failed: {result.stderr}"
    violations = _check_forbidden_in_output(result.stdout)
    if violations:
        return False, "; ".join(violations)
    if "Atlas Agent" not in result.stdout:
        return False, "atlas --help missing expected branding"
    return True, ""


def _check_atlas_validate(atlas_bin: Path, cwd: Path | None = None) -> tuple[bool, str]:
    result = _run([str(atlas_bin), "validate"], cwd=cwd)
    combined = result.stdout + result.stderr
    for phrase in EXPECTED_VALIDATE_PHRASES:
        if phrase.lower() not in combined.lower():
            return False, f"atlas validate missing expected safety phrase: {phrase!r}"
    violations = _check_forbidden_in_output(combined)
    if violations:
        return False, "; ".join(violations)
    return True, ""


def _check_template_init(atlas_bin: Path, parent_dir: Path) -> tuple[bool, str]:
    workspace = parent_dir / "template-workspace"
    result = _run(
        [str(atlas_bin), "init", str(workspace), "--template", "routine-trader"],
        cwd=parent_dir,
    )
    if result.returncode != 0:
        return False, f"atlas init failed: {result.stdout}{result.stderr}"

    missing = [
        rel for rel in EXPECTED_TEMPLATE_FILES if not (workspace / rel).exists()
    ]
    if missing:
        return False, f"template workspace missing files: {', '.join(missing)}"
    if (workspace / ".env").exists():
        return False, "template workspace unexpectedly contains .env"

    validate_result = _run(
        [str(atlas_bin), "--workspace", str(workspace), "validate"],
        cwd=parent_dir,
    )
    validate_combined = validate_result.stdout + validate_result.stderr
    if validate_result.returncode != 0:
        return False, f"atlas validate --workspace failed: {validate_combined}"
    violations = _check_forbidden_in_output(_redact(validate_combined))
    if violations:
        return False, "; ".join(violations)
    return True, ""


def _check_package_version(python: Path) -> tuple[bool, str]:
    result = _run(
        [str(python), "-c", "import atlas_agent; print(atlas_agent.__version__)"]
    )
    if result.returncode != 0:
        return False, f"Package version check failed: {result.stderr}"
    version = result.stdout.strip()
    if version != EXPECTED_PACKAGE_VERSION:
        return False, f"Installed version {version!r} != expected {EXPECTED_PACKAGE_VERSION!r}"
    violations = _check_forbidden_in_output(result.stdout)
    if violations:
        return False, "; ".join(violations)
    return True, ""


def _check_readme_quickstart(repo_root: Path) -> tuple[bool, str]:
    script = repo_root / "scripts" / "verify_readme_quickstart.py"
    if not script.exists():
        return True, "verify_readme_quickstart.py not found; skipping"
    result = _run([sys.executable, str(script)])
    if result.returncode != 0:
        return False, f"README quickstart verification failed: {result.stdout}{result.stderr}"
    return True, ""


def _build_plan(args: argparse.Namespace) -> dict:
    """Return a dry-run plan without executing anything."""
    return {
        "repo_root": str(REPO_ROOT),
        "skip_venv": args.skip_venv,
        "keep_temp": args.keep_temp,
        "allow_network": args.allow_network,
        "expected_version": EXPECTED_PACKAGE_VERSION,
        "steps": [
            "create temporary directory",
            *([] if args.skip_venv else ["create virtual environment (system-site-packages for no-network build deps)"]),
            "pip install --no-index --no-build-isolation -e <repo>" if not args.allow_network else "pip install -e <repo>",
            "verify installed atlas console entrypoint: atlas --help",
            "verify installed atlas console entrypoint: atlas validate",
            "verify atlas init --template routine-trader outside repo",
            "verify package version",
            "verify README quickstart",
            *([] if args.keep_temp else ["remove temporary directory"]),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify clean install of the current Atlas Agent repo."
    )
    parser.add_argument(
        "--from-current-worktree",
        action="store_true",
        default=True,
        help="Use the current worktree (default).",
    )
    parser.add_argument(
        "--skip-venv",
        action="store_true",
        help="Skip virtual environment creation (dry-run only). Not allowed for real installs because a clean install must use an isolated virtual environment.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary directory after verification for debugging.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow pip to access the package index. Default is no-network.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the verification plan and exit without creating files.",
    )
    args = parser.parse_args(argv)

    if args.skip_venv and not args.dry_run:
        print(
            "ERROR: --skip-venv is only allowed with --dry-run. "
            "A clean install must use an isolated virtual environment.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        plan = _build_plan(args)
        print("Clean install verification plan:")
        print(f"  repo_root: {_redact(plan['repo_root'])}")
        print(f"  expected_version: {plan['expected_version']}")
        print(f"  skip_venv: {plan['skip_venv']}")
        print(f"  keep_temp: {plan['keep_temp']}")
        print(f"  allow_network: {plan['allow_network']}")
        print("  steps:")
        for step in plan["steps"]:
            print(f"    - {_redact(step)}")
        print("Dry-run complete. No files created.")
        return 0

    temp_dir: Path | None = None
    errors: list[str] = []
    network_allowed = args.allow_network
    console_entrypoint_checked = False
    atlas_validate_checked = False
    template_init_checked = False

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="atlas-clean-install-"))
        global _CURRENT_TEMP_DIR
        _CURRENT_TEMP_DIR = str(temp_dir)
        print(f"Temp directory: {_redact(str(temp_dir))}")

        if args.skip_venv:
            python = Path(sys.executable)
            atlas_path = shutil.which("atlas")
            atlas_bin = Path(atlas_path) if atlas_path else Path("atlas")
            print("Using current Python (skip-venv)")
        else:
            venv_dir = temp_dir / "venv"
            print("Creating virtual environment...")
            # Use system-site-packages so build backend and runtime deps are
            # available without network access.
            venv_result = _run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)]
            )
            if venv_result.returncode != 0:
                return _error(f"venv creation failed: {venv_result.stderr}")

            python = _find_venv_python(venv_dir)
            print(f"Using venv Python: {_redact(str(python))}")

        print("Installing package in editable mode...")
        install_cmd = [str(python), "-m", "pip", "install", "--quiet"]
        if not network_allowed:
            install_cmd.extend(["--no-index", "--no-build-isolation"])
        install_cmd.extend(["-e", str(REPO_ROOT)])
        install_result = _run(install_cmd)
        if install_result.returncode != 0:
            msg = f"pip install failed: {install_result.stderr}"
            if not network_allowed:
                msg += (
                    "\nHint: If local build dependencies are missing, rerun with "
                    "--allow-network or ensure the build environment has the "
                    "required build backend installed."
                )
            return _error(msg)

        if not args.skip_venv:
            atlas_bin = _find_venv_atlas(venv_dir)
        print(f"Atlas entrypoint: {_redact(str(atlas_bin))}")

        # 1. Console entrypoint: atlas --help
        print("Checking atlas --help (installed console entrypoint)...")
        ok, msg = _check_atlas_help(atlas_bin)
        if not ok:
            errors.append(f"atlas --help: {msg}")
        else:
            console_entrypoint_checked = True
            print("  atlas --help: OK")

        # 2. Console entrypoint: atlas validate
        print("Checking atlas validate (installed console entrypoint)...")
        ok, msg = _check_atlas_validate(atlas_bin, cwd=temp_dir)
        if not ok:
            errors.append(f"atlas validate: {msg}")
        else:
            atlas_validate_checked = True
            print("  atlas validate: OK")

        # 3. Package version
        print("Checking atlas init template from outside repo...")
        ok, msg = _check_template_init(atlas_bin, temp_dir)
        if not ok:
            errors.append(f"atlas init template: {msg}")
        else:
            template_init_checked = True
            print("  atlas init template: OK")

        # 4. Package version
        print("Checking package version...")
        ok, msg = _check_package_version(python)
        if not ok:
            errors.append(f"package version: {msg}")
        else:
            print(f"  package version: OK")

        # 5. README quickstart
        print("Checking README quickstart...")
        ok, msg = _check_readme_quickstart(REPO_ROOT)
        if not ok:
            errors.append(f"README quickstart: {msg}")
        else:
            print("  README quickstart: OK")

        if errors:
            print("Clean install verification FAILED", file=sys.stderr)
            for e in errors:
                print(f"  - {_redact(e)}", file=sys.stderr)
            return 2

        print("Clean install verification PASSED")
        print(f"  Package version: {EXPECTED_PACKAGE_VERSION}")
        print(f"  Network allowed: {network_allowed}")
        print(f"  Console entrypoint checked: {console_entrypoint_checked}")
        print(f"  atlas validate checked: {atlas_validate_checked}")
        print(f"  atlas init template checked: {template_init_checked}")
        print(f"  No forbidden fragments in output")
        return 0

    except Exception as exc:
        # Avoid leaking raw tracebacks with absolute paths
        print(f"ERROR: {_redact(str(exc))}", file=sys.stderr)
        return 2

    finally:
        if temp_dir is not None and not args.keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Cleaned up temp directory: {_redact(str(temp_dir))}")
        elif temp_dir is not None and args.keep_temp:
            print(f"Kept temp directory: {_redact(str(temp_dir))}")


if __name__ == "__main__":
    sys.exit(main())
