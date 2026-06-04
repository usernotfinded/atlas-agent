#!/usr/bin/env python3
"""Local packaging/distribution dry-run verification.

Performs a local-only build and metadata check. Does not:
- publish to PyPI
- upload packages
- create GitHub releases
- push tags
- call network inside Atlas runtime
- load credentials
- modify risk gates or broker behavior

Exit codes:
    0 - verification passed
    1 - CLI argument or setup error
    2 - verification failure
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# Expected package version (PEP 440).
EXPECTED_PACKAGE_VERSION = "0.5.9.4"
EXPECTED_PUBLIC_TAG = "v0.5.9.4"
EXPECTED_NAME = "atlas-agent"
EXPECTED_NORMALIZED_NAME = "atlas_agent"
EXPECTED_TEMPLATE_FILES = (
    "templates/routine-trader/README.md",
    "templates/routine-trader/.env.example",
    "templates/routine-trader/.gitignore",
    "templates/routine-trader/configs/market.example.yaml",
    "templates/routine-trader/memory/portfolio.md",
    "templates/routine-trader/routines/prompts/pre_market.md",
    "templates/routine-trader/skills/risk_review.md",
)

# Forbidden output fragments.
FORBIDDEN_OUTPUT_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "/var/folders/",
    "/tmp/",
    "/var/tmp/",
)

# Forbidden positive claims about live trading / provider execution.
FORBIDDEN_METADATA_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
]

_CURRENT_TEMP_DIR: str | None = None


def _redact(text: str) -> str:
    """Redact user-specific absolute paths from output."""
    replacements: list[tuple[str, str]] = []
    if _CURRENT_TEMP_DIR is not None:
        replacements.append((_CURRENT_TEMP_DIR, "<temp>"))
    home = str(Path.home())
    if home != "/":
        replacements.append((home, "~"))
    repo = str(REPO_ROOT)
    replacements.append((repo, "<repo>"))
    for prefix in ("/var/folders/", "/private/var/", "/tmp/", "/var/tmp/"):
        replacements.append((prefix, "<temp>/"))
    replacements.append(("/Users/", "<users>/"))
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _error(msg: str) -> int:
    print(f"ERROR: {_redact(msg)}", file=sys.stderr)
    return 2


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


def _check_build_available() -> tuple[bool, str]:
    result = _run([sys.executable, "-m", "build", "--help"])
    if result.returncode != 0:
        return False, "python -m build is not available"
    return True, ""


def _check_twine_available() -> tuple[bool, str]:
    result = _run([sys.executable, "-m", "twine", "check", "--help"])
    if result.returncode != 0:
        return False, "python -m twine is not available"
    return True, ""


def _build_artifacts(output_dir: Path, no_isolation: bool = True) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "build",
        "--sdist",
        "--wheel",
        "--outdir",
        str(output_dir),
    ]
    if no_isolation:
        cmd.append("--no-isolation")
    result = _run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        # Redact before returning so callers print safe text only
        redacted_stdout = _redact(stdout)
        redacted_stderr = _redact(stderr)
        return False, f"Build failed:\n{redacted_stdout}\n{redacted_stderr}"
    return True, ""


def _find_artifacts(dist_dir: Path) -> tuple[Path | None, Path | None]:
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))
    wheel = wheels[0] if wheels else None
    sdist = sdists[0] if sdists else None
    return wheel, sdist


def _check_wheel_metadata(wheel_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(wheel_path, "r") as zf:
            metadata_files = [n for n in zf.namelist() if n.endswith("/METADATA")]
            if not metadata_files:
                errors.append("No METADATA file found in wheel")
                return False, errors

            metadata_text = zf.read(metadata_files[0]).decode("utf-8", errors="replace")

            # Check name
            name_match = None
            for line in metadata_text.splitlines():
                if line.lower().startswith("name:"):
                    name_match = line.split(":", 1)[1].strip()
                    break
            if name_match is None:
                errors.append("Name not found in wheel METADATA")
            elif name_match not in (EXPECTED_NAME, EXPECTED_NORMALIZED_NAME):
                errors.append(
                    f"Wheel name {name_match!r} != expected {EXPECTED_NAME!r}"
                )

            # Check version
            version_match = None
            for line in metadata_text.splitlines():
                if line.lower().startswith("version:"):
                    version_match = line.split(":", 1)[1].strip()
                    break
            if version_match is None:
                errors.append("Version not found in wheel METADATA")
            elif version_match != EXPECTED_PACKAGE_VERSION:
                errors.append(
                    f"Wheel version {version_match!r} != expected {EXPECTED_PACKAGE_VERSION!r}"
                )

            # Check entry points
            entry_files = [n for n in zf.namelist() if n.endswith("/entry_points.txt")]
            if entry_files:
                entry_text = zf.read(entry_files[0]).decode("utf-8", errors="replace")
                if "atlas" not in entry_text:
                    errors.append("atlas entry point not found in wheel entry_points.txt")
            else:
                # entry_points.txt is optional if no console scripts declared;
                # atlas is expected so flag it.
                errors.append("entry_points.txt not found in wheel")

            # Check for forbidden claims in metadata
            lower_meta = metadata_text.lower()
            for claim in FORBIDDEN_METADATA_CLAIMS:
                if claim in lower_meta:
                    errors.append(f"Forbidden claim in wheel METADATA: {claim}")

    except zipfile.BadZipFile as exc:
        errors.append(f"Bad wheel file: {exc}")
    except Exception as exc:
        errors.append(f"Error reading wheel: {exc}")

    return len(errors) == 0, errors


def _check_wheel_templates(wheel_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(wheel_path, "r") as zf:
            names = set(zf.namelist())
            for rel in EXPECTED_TEMPLATE_FILES:
                member = f"atlas_agent/{rel}"
                if member not in names:
                    errors.append(f"Template file missing from wheel: {member}")
    except zipfile.BadZipFile as exc:
        errors.append(f"Bad wheel file: {exc}")
    except Exception as exc:
        errors.append(f"Error reading wheel templates: {exc}")
    return len(errors) == 0, errors


def _check_sdist_metadata(sdist_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        with tarfile.open(sdist_path, "r:gz") as tf:
            # Find the PKG-INFO file safely (top-level or inside a directory)
            pkg_info_members = [
                m for m in tf.getmembers()
                if m.name.endswith("/PKG-INFO") or m.name == "PKG-INFO"
            ]
            if not pkg_info_members:
                errors.append("No PKG-INFO found in sdist")
                return False, errors

            # Read without extracting to disk (guard path traversal)
            member = pkg_info_members[0]
            if member.issym() or member.islnk():
                errors.append("Symlink found in sdist; skipping unsafe member")
                return False, errors

            fobj = tf.extractfile(member)
            if fobj is None:
                errors.append("Could not read PKG-INFO from sdist")
                return False, errors

            pkg_info_text = fobj.read().decode("utf-8", errors="replace")

            # Check name
            name_match = None
            for line in pkg_info_text.splitlines():
                if line.lower().startswith("name:"):
                    name_match = line.split(":", 1)[1].strip()
                    break
            if name_match is None:
                errors.append("Name not found in sdist PKG-INFO")
            elif name_match not in (EXPECTED_NAME, EXPECTED_NORMALIZED_NAME):
                errors.append(
                    f"Sdist name {name_match!r} != expected {EXPECTED_NAME!r}"
                )

            # Check version
            version_match = None
            for line in pkg_info_text.splitlines():
                if line.lower().startswith("version:"):
                    version_match = line.split(":", 1)[1].strip()
                    break
            if version_match is None:
                errors.append("Version not found in sdist PKG-INFO")
            elif version_match != EXPECTED_PACKAGE_VERSION:
                errors.append(
                    f"Sdist version {version_match!r} != expected {EXPECTED_PACKAGE_VERSION!r}"
                )

            # Check for forbidden claims in metadata (name, summary, description)
            lower_meta = pkg_info_text.lower()
            for claim in FORBIDDEN_METADATA_CLAIMS:
                if claim in lower_meta:
                    errors.append(f"Forbidden claim in sdist PKG-INFO: {claim}")

    except tarfile.TarError as exc:
        errors.append(f"Bad sdist file: {exc}")
    except Exception as exc:
        errors.append(f"Error reading sdist: {exc}")

    return len(errors) == 0, errors


def _check_sdist_templates(sdist_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        with tarfile.open(sdist_path, "r:gz") as tf:
            names = {m.name for m in tf.getmembers()}
            for rel in EXPECTED_TEMPLATE_FILES:
                suffix = f"/src/atlas_agent/{rel}"
                if not any(name.endswith(suffix) for name in names):
                    errors.append(f"Template file missing from sdist: src/atlas_agent/{rel}")
    except tarfile.TarError as exc:
        errors.append(f"Bad sdist file: {exc}")
    except Exception as exc:
        errors.append(f"Error reading sdist templates: {exc}")
    return len(errors) == 0, errors


def _find_venv_bin(venv_dir: Path, name: str) -> Path:
    candidates = [
        venv_dir / "bin" / name,
        venv_dir / "Scripts" / f"{name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find {name} in venv: {venv_dir}")


def _check_wheel_template_install(wheel_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="atlas-wheel-template-check-"))
    global _CURRENT_TEMP_DIR
    previous_temp = _CURRENT_TEMP_DIR
    _CURRENT_TEMP_DIR = str(temp_dir)
    try:
        venv_dir = temp_dir / "venv"
        workspace = temp_dir / "workspace"
        venv_result = _run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)]
        )
        if venv_result.returncode != 0:
            return False, [f"venv creation failed: {_redact(venv_result.stderr or '')}"]

        python = _find_venv_bin(venv_dir, "python")
        install_result = _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(wheel_path),
            ]
        )
        if install_result.returncode != 0:
            return False, [f"wheel install failed: {_redact(install_result.stderr or '')}"]

        atlas_bin = _find_venv_bin(venv_dir, "atlas")
        init_result = _run(
            [str(atlas_bin), "init", str(workspace), "--template", "routine-trader"],
            cwd=temp_dir,
        )
        if init_result.returncode != 0:
            return False, [
                f"atlas init from wheel failed: {_redact((init_result.stdout or '') + (init_result.stderr or ''))}"
            ]

        expected_workspace_files = (
            "README.md",
            ".env.example",
            "configs/market.example.yaml",
            "memory/portfolio.md",
            "routines/prompts/pre_market.md",
            "skills/risk_review.md",
        )
        missing = [rel for rel in expected_workspace_files if not (workspace / rel).exists()]
        if missing:
            errors.append(f"wheel-installed template workspace missing files: {', '.join(missing)}")
        if (workspace / ".env").exists():
            errors.append("wheel-installed template workspace unexpectedly contains .env")
    except Exception as exc:
        errors.append(f"wheel template install check failed: {_redact(str(exc))}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        _CURRENT_TEMP_DIR = previous_temp
    return len(errors) == 0, errors


def _check_artifact_filenames(wheel: Path | None, sdist: Path | None) -> list[str]:
    errors: list[str] = []
    if wheel is not None:
        # Normalized wheel name: atlas_agent-0.5.7rc3-py3-none-any.whl
        if EXPECTED_PACKAGE_VERSION not in wheel.name and EXPECTED_PACKAGE_VERSION.replace("rc", "rc") not in wheel.name:
            # Try normalized form
            norm_version = EXPECTED_PACKAGE_VERSION.replace("rc", "rc")
            if norm_version not in wheel.name:
                errors.append(f"Wheel filename does not contain expected version: {wheel.name}")
    if sdist is not None:
        if EXPECTED_PACKAGE_VERSION not in sdist.name:
            errors.append(f"Sdist filename does not contain expected version: {sdist.name}")
    return errors


def _check_no_staged_artifacts() -> list[str]:
    errors: list[str] = []
    result = _run(["git", "diff", "--cached", "--name-only"], cwd=REPO_ROOT)
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden_prefixes = ("dist/", "build/")
    for f in staged:
        if f.startswith(forbidden_prefixes) or f.endswith(".egg-info/"):
            errors.append(f"Package artifact staged: {f}")
    return errors


def _build_plan(args: argparse.Namespace) -> dict:
    return {
        "repo_root": str(REPO_ROOT),
        "keep_artifacts": args.keep_artifacts,
        "output_dir": str(args.output_dir) if args.output_dir else "<temp>",
        "expected_version": EXPECTED_PACKAGE_VERSION,
        "expected_tag": EXPECTED_PUBLIC_TAG,
        "steps": [
            "verify build module availability",
            "python -m build --no-isolation --sdist --wheel --outdir <dist>",
            "verify wheel exists",
            "verify sdist exists",
            "verify artifact filenames contain expected version",
            "verify wheel METADATA (name, version, entry points)",
            "verify wheel contains packaged routine-trader templates",
            "verify sdist PKG-INFO (name, version)",
            "verify sdist contains packaged routine-trader templates",
            "install wheel into a temporary venv and run atlas init outside repo",
            "verify no forbidden claims in metadata",
            "verify no package artifacts staged",
            *(["python -m twine check <dist>/*"] if not args.skip_twine else []),
            *([] if args.keep_artifacts else ["remove temporary output directory"]),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local packaging/distribution dry-run verification for Atlas Agent."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the verification plan and exit without building.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the temporary output directory after verification.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Use a specific output directory instead of a temporary one.",
    )
    parser.add_argument(
        "--skip-twine",
        action="store_true",
        help="Skip twine check even if twine is available.",
    )
    parser.add_argument(
        "--allow-network-build",
        action="store_true",
        help="Allow the build to fetch build dependencies from PyPI. Default is no-network.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        plan = _build_plan(args)
        print("Package distribution verification plan:")
        print(f"  repo_root: {_redact(plan['repo_root'])}")
        print(f"  expected_version: {plan['expected_version']}")
        print(f"  expected_tag: {plan['expected_tag']}")
        print(f"  keep_artifacts: {plan['keep_artifacts']}")
        print(f"  output_dir: {_redact(plan['output_dir'])}")
        print("  steps:")
        for step in plan["steps"]:
            print(f"    - {_redact(step)}")
        print("Dry-run complete. No artifacts built.")
        return 0

    output_dir: Path | None = None
    errors: list[str] = []
    wheel: Path | None = None
    sdist: Path | None = None

    try:
        if args.output_dir is not None:
            output_dir = args.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path(tempfile.mkdtemp(prefix="atlas-dist-check-"))

        global _CURRENT_TEMP_DIR
        _CURRENT_TEMP_DIR = str(output_dir)
        print(f"Output directory: {_redact(str(output_dir))}")

        # 1. Check build module
        print("Checking build module availability...")
        build_ok, build_msg = _check_build_available()
        if not build_ok:
            errors.append(build_msg)
            print(f"  build missing: {build_msg}")
        else:
            print("  build module: OK")

        if not build_ok:
            print("Package distribution verification FAILED", file=sys.stderr)
            for e in errors:
                print(f"  - {_redact(e)}", file=sys.stderr)
            return 2

        # 2. Build artifacts
        print("Building wheel and sdist...")
        build_ok, build_msg = _build_artifacts(
            output_dir, no_isolation=not args.allow_network_build
        )
        if not build_ok:
            errors.append(build_msg)
            print(f"  build failed: {build_msg}")
        else:
            print("  build: OK")

        if not build_ok:
            print("Package distribution verification FAILED", file=sys.stderr)
            for e in errors:
                print(f"  - {_redact(e)}", file=sys.stderr)
            return 2

        # 3. Find artifacts
        print("Locating artifacts...")
        wheel, sdist = _find_artifacts(output_dir)
        if wheel is None:
            errors.append("No wheel found in output directory")
        else:
            print(f"  wheel: {_redact(wheel.name)}")
        if sdist is None:
            errors.append("No sdist found in output directory")
        else:
            print(f"  sdist: {_redact(sdist.name)}")

        # 4. Check filenames
        print("Checking artifact filenames...")
        filename_errors = _check_artifact_filenames(wheel, sdist)
        if filename_errors:
            errors.extend(filename_errors)
            for e in filename_errors:
                print(f"  filename error: {e}")
        else:
            print("  filenames: OK")

        # 5. Check wheel metadata
        if wheel is not None:
            print("Checking wheel metadata...")
            wheel_ok, wheel_errors = _check_wheel_metadata(wheel)
            if not wheel_ok:
                errors.extend(wheel_errors)
                for e in wheel_errors:
                    print(f"  wheel error: {e}")
            else:
                print("  wheel metadata: OK")

            print("Checking wheel template resources...")
            wheel_templates_ok, wheel_template_errors = _check_wheel_templates(wheel)
            if not wheel_templates_ok:
                errors.extend(wheel_template_errors)
                for e in wheel_template_errors:
                    print(f"  wheel template error: {e}")
            else:
                print("  wheel templates: OK")

        # 6. Check sdist metadata
        if sdist is not None:
            print("Checking sdist metadata...")
            sdist_ok, sdist_errors = _check_sdist_metadata(sdist)
            if not sdist_ok:
                errors.extend(sdist_errors)
                for e in sdist_errors:
                    print(f"  sdist error: {e}")
            else:
                print("  sdist metadata: OK")

            print("Checking sdist template resources...")
            sdist_templates_ok, sdist_template_errors = _check_sdist_templates(sdist)
            if not sdist_templates_ok:
                errors.extend(sdist_template_errors)
                for e in sdist_template_errors:
                    print(f"  sdist template error: {e}")
            else:
                print("  sdist templates: OK")

        # 7. Check wheel-installed template initialization
        if wheel is not None:
            print("Checking wheel-installed template initialization...")
            wheel_install_ok, wheel_install_errors = _check_wheel_template_install(wheel)
            if not wheel_install_ok:
                errors.extend(wheel_install_errors)
                for e in wheel_install_errors:
                    print(f"  wheel install template error: {e}")
            else:
                print("  wheel-installed template init: OK")

        # 8. Check no staged artifacts
        print("Checking for staged package artifacts...")
        staged_errors = _check_no_staged_artifacts()
        if staged_errors:
            errors.extend(staged_errors)
            for e in staged_errors:
                print(f"  staged error: {e}")
        else:
            print("  no staged artifacts: OK")

        # 9. Optional twine check
        if not args.skip_twine:
            print("Checking twine availability...")
            twine_ok, twine_msg = _check_twine_available()
            if twine_ok:
                print("Running twine check...")
                twine_cmd = [
                    sys.executable,
                    "-m",
                    "twine",
                    "check",
                    str(output_dir / "*"),
                ]
                # shell glob will not work without shell invocation; use explicit paths instead
                artifact_paths = list(output_dir.glob("*.whl")) + list(output_dir.glob("*.tar.gz"))
                if artifact_paths:
                    twine_cmd = [
                        sys.executable,
                        "-m",
                        "twine",
                        "check",
                    ] + [str(p) for p in artifact_paths]
                    twine_result = _run(twine_cmd)
                    if twine_result.returncode != 0:
                        redacted_stderr = _redact(twine_result.stderr or "")
                        errors.append(f"twine check failed: {redacted_stderr}")
                        print(f"  twine check failed: {redacted_stderr}")
                    else:
                        print("  twine check: OK")
                else:
                    print("  twine check skipped: no artifacts")
            else:
                print(f"  twine not available: {twine_msg}")
        else:
            print("Twine check skipped by --skip-twine")

        if errors:
            print("Package distribution verification FAILED", file=sys.stderr)
            for e in errors:
                print(f"  - {_redact(e)}", file=sys.stderr)
            return 2

        print("Package distribution verification PASSED")
        print(f"  Package version: {EXPECTED_PACKAGE_VERSION}")
        print(f"  Public tag: {EXPECTED_PUBLIC_TAG}")
        print(f"  Wheel: {wheel.name if wheel else 'N/A'}")
        print(f"  Sdist: {sdist.name if sdist else 'N/A'}")
        print(f"  Build isolation: {'enabled' if args.allow_network_build else 'disabled'}")
        print(f"  Network allowed: {args.allow_network_build}")
        print(f"  Template resources checked: yes")
        print(f"  Wheel-installed template init checked: yes")
        print(f"  No forbidden claims in metadata")
        print(f"  No package artifacts staged")
        return 0

    except Exception as exc:
        print(f"ERROR: {_redact(str(exc))}", file=sys.stderr)
        return 2

    finally:
        if output_dir is not None and not args.keep_artifacts and args.output_dir is None:
            shutil.rmtree(output_dir, ignore_errors=True)
            print(f"Cleaned up output directory: {_redact(str(output_dir))}")
        elif output_dir is not None and args.keep_artifacts:
            print(f"Kept output directory: {_redact(str(output_dir))}")


if __name__ == "__main__":
    sys.exit(main())
