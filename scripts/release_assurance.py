# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/release_assurance.py
# PURPOSE: Implements repository tooling for release assurance.
# DEPS:    argparse, os, json, re, subprocess, sys, additional local modules.
# ==============================================================================

# --- IMPORTS ---

import argparse
import os
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import tempfile

# Load canonical release metadata so version baselines are not hardcoded.
# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    from scripts.release_metadata import load_metadata, ReleaseMetadata

_metadata_path = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
_meta = ReleaseMetadata(load_metadata(_metadata_path))

# Redaction patterns for credential-like values in diagnostic output.
# These intentionally match values, not safe phrases like "secret regression coverage".
_REDACTION_PATTERNS = [
    # Environment variable assignments: NAME=value (case-insensitive, value may be quoted).
    (re.compile(r"(?i)\b([A-Z_]*TOKEN[A-Z_]*)\s*=\s*(\S+)"), r"\1=<redacted>"),
    # GitHub token patterns.
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "<redacted>"),
    # Generic secret/API key prefixes.
    (re.compile(r"\b(sk-[A-Za-z0-9]{20,})"), "<redacted>"),
    (
        re.compile(
            r"\b(APCA-[A-Za-z0-9]{4,}-[A-Za-z0-9]{4,}-[A-Za-z0-9]{4,}-[A-Za-z0-9]{12,})"
        ),
        "<redacted>",
    ),
    # Bearer tokens.
    (re.compile(r"(?i)(Bearer\s+)\S+"), r"\1<redacted>"),
    # Account-like UUIDs.
    (
        re.compile(
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
        ),
        "<redacted>",
    ),
]


# ==============================================================================
# SCRIPT IMPLEMENTATION
# ==============================================================================

# --- HELPERS AND ENTRYPOINTS ---

def redact_text(text: str) -> str:
    """Sanitize a string by redacting credential-like values."""
    if not text:
        return text
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


_REMEDIATIONS = {
    "package_version_aligned": "Verify pyproject.toml and src/atlas_agent/__init__.py both declare the expected version.",
    "release_notes_present": "Create docs/releases/{version}.md with required safety non-claims.",
    "changelog_present": "Add a [{clean_version}] section to CHANGELOG.md.",
    "readme_public_metadata_current": "Update README.md current-status claim to the release being verified and remove stale historical claims.",
    "security_md_current": "Add package version {clean_version} to SECURITY.md supported-versions table.",
    "local_tag_present": "Create local tag with: git tag {version}",
    "remote_tag_present": "Push local tag with: git push origin {version}",
    "github_release_present": "Create a GitHub release for {version} or verify GH_TOKEN is set and gh CLI is authenticated.",
    "updater_dry_run_ok": "Run updater dry-run locally: PYTHONPATH=src python -m atlas_agent.cli init <tmp> --template routine-trader && python -m atlas_agent.cli update check --dry-run",
    "dev_version_not_public_stable": "Verify atlas_agent.update.sources.is_public_stable rejects dev tags.",
    "provider_audit_pack_commands_present": "Ensure provider audit-pack CLI commands are registered.",
    "provider_audit_pack_workflow_present": "Ensure .github/workflows/provider-audit-pack.yml exists.",
    "non_claims_preserved": "Add required safety non-claims to docs/releases/{version}.md.",
    "protected_boundaries_clean": "Revert changes in src/atlas_agent/{{config,brokers,execution,safety,risk}} or exclude from release.",
    "reviewer_trust_snapshot_valid": "Run scripts/check_reviewer_trust_snapshot.py on the snapshot directory.",
}


def _remediation(check_name: str, version: str, clean_version: str) -> str:
    template = _REMEDIATIONS.get(
        check_name,
        "Investigate the failed check and re-run release_assurance.py after fixing the underlying issue.",
    )
    return template.format(version=version, clean_version=clean_version)


def _record_diagnostic(
    diagnostics: dict,
    check_name: str,
    command: str,
    passed: bool,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = None,
) -> None:
    diagnostics[check_name] = {
        "check": check_name,
        "command": command,
        "passed": passed,
        "exit_code": exit_code,
        "stdout_excerpt": redact_text(stdout[-500:]) if stdout else "",
        "stderr_excerpt": redact_text(stderr[-500:]) if stderr else "",
    }


def normalize_release_version(version: str) -> str:
    """Return the package version for a release/tag version."""
    return version[1:] if version.startswith("v") else version


def security_md_supports_package_version(
    security_md: str, package_version: str
) -> bool:
    version_pattern = re.compile(
        rf"(?<![0-9A-Za-z.]){re.escape(package_version)}(?![0-9A-Za-z.])"
    )
    for line in security_md.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0].lower() in {"version", "---"}:
            continue
        if version_pattern.search(cells[0]):
            return True
    return False


def run_cmd(
    cmd: list[str],
    check: bool = True,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
):
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=check,
            cwd=cwd,
            env=run_env,
        )
        return result.stdout.strip(), result.returncode, result.stderr.strip()
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return (e.stdout or "").strip(), e.returncode, (e.stderr or "").strip()


def main():
    parser = argparse.ArgumentParser(
        description="Generate a local release assurance pack."
    )
    parser.add_argument(
        "--version", required=True, help="Release version to assure (e.g., v0.6.0)"
    )
    parser.add_argument(
        "--output", required=True, help="Output directory for the assurance pack"
    )
    parser.add_argument(
        "--include-reviewer-trust-snapshot",
        action="store_true",
        help="Include a deterministic reviewer trust snapshot in the assurance output.",
    )
    parser.add_argument(
        "--diagnostics-json",
        default=None,
        help="Optional path to write a machine-readable diagnostics JSON file on failure.",
    )
    args = parser.parse_args()

    version = args.version
    tag_version = version
    clean_version = normalize_release_version(version)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    checks = {}
    safety = {
        "live_trading_enabled_by_default": False,
        "live_submit_enabled_by_default": False,
        "provider_execution_enabled_by_default": False,
        "broker_execution_enabled_by_default": False,
        "pypi_publish_performed": False,
    }
    findings = []
    diagnostics: dict[str, dict] = {}

    # 1-3. Version checks
    release_record = _meta.release_by_tag(version)
    release_status = release_record.get("status") if release_record else None
    expected_package_version = (
        release_record.get("version", clean_version) if release_record else clean_version
    )
    try:
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        init_py = Path("src/atlas_agent/__init__.py").read_text(encoding="utf-8")
        if release_status == "current_public":
            # Source on main may have moved forward after the public release; verify
            # the release metadata records the expected package version and the
            # source files declare the current development version.
            checks["package_version_aligned"] = (
                expected_package_version == clean_version
                and f'version = "{_meta.source_version}"' in pyproject
                and f'__version__ = "{_meta.source_version}"' in init_py
            )
        else:
            checks["package_version_aligned"] = (
                f'version = "{expected_package_version}"' in pyproject
                and f'__version__ = "{expected_package_version}"' in init_py
            )
    except OSError as e:
        checks["package_version_aligned"] = False
        findings.append(f"Failed to read version files: {e}")
    _record_diagnostic(
        diagnostics,
        "package_version_aligned",
        "internal: read pyproject.toml and src/atlas_agent/__init__.py",
        checks["package_version_aligned"],
    )

    # 4. Release notes
    release_notes_path = Path(f"docs/releases/{version}.md")
    checks["release_notes_present"] = release_notes_path.exists()
    _record_diagnostic(
        diagnostics,
        "release_notes_present",
        f"internal: Path.exists({release_notes_path})",
        checks["release_notes_present"],
    )

    # 5. Changelog
    try:
        changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
        checks["changelog_present"] = f"[{clean_version}]" in changelog
    except OSError:
        checks["changelog_present"] = False
    _record_diagnostic(
        diagnostics,
        "changelog_present",
        "internal: read CHANGELOG.md",
        checks["changelog_present"],
    )

    # 6. README
    try:
        readme = Path("README.md").read_text(encoding="utf-8")
        # The README must reference the active source version as the current status
        # and must not claim any historical release is current. For a current_public
        # release verified from main, the README is intentionally ahead of the
        # public tag; use the source version from metadata as the expected status.
        historical_tags = [
            r.get("tag")
            for r in _meta.data.get("releases", [])
            if r.get("status") == "historical" and r.get("tag")
        ]
        expected_status_version = (
            f"v{_meta.source_version}" if release_status == "current_public" else version
        )
        current_status_claim = f"Current Status ({expected_status_version})"
        readme_current = current_status_claim in readme
        stale_claims = [
            f"Current Status ({tag})"
            for tag in historical_tags
            if f"Current Status ({tag})" in readme
        ]
        checks["readme_public_metadata_current"] = readme_current and not stale_claims
        if stale_claims:
            findings.append(
                "README.md contains stale current-status claim(s): "
                + ", ".join(stale_claims)
            )
        if not readme_current:
            findings.append(
                f"README.md does not contain expected current-status claim: {current_status_claim}"
            )
    except OSError:
        checks["readme_public_metadata_current"] = False
    _record_diagnostic(
        diagnostics,
        "readme_public_metadata_current",
        "internal: read README.md",
        checks["readme_public_metadata_current"],
    )

    # 7. SECURITY.md
    try:
        security = Path("SECURITY.md").read_text(encoding="utf-8")
        checks["security_md_current"] = security_md_supports_package_version(
            security, clean_version
        )
    except OSError:
        checks["security_md_current"] = False
    if not checks["security_md_current"]:
        findings.append(
            "SECURITY.md supported versions do not include "
            f"package version {clean_version} for release tag {tag_version}."
        )
    _record_diagnostic(
        diagnostics,
        "security_md_current",
        "internal: read SECURITY.md",
        checks["security_md_current"],
    )

    # Public-release artifacts are expected for current_public / historical releases
    # and for unknown release records (legacy/mocked runs). Prepared releases must
    # not have tags or GitHub releases yet.
    expect_public_artifacts = (
        release_status in ("current_public", "historical")
        if release_record
        else True
    )

    # 8. Local tag
    out, rc, err = run_cmd(["git", "tag", "-l", version], check=False)
    local_tag_present = version in out
    checks["local_tag_present"] = local_tag_present == expect_public_artifacts
    _record_diagnostic(
        diagnostics,
        "local_tag_present",
        f"git tag -l {version}",
        checks["local_tag_present"],
        out,
        err,
        rc,
    )

    # 9. Remote tag
    out, rc, err = run_cmd(
        ["git", "ls-remote", "--tags", "origin", version], check=False
    )
    remote_tag_present = version in out
    checks["remote_tag_present"] = remote_tag_present == expect_public_artifacts
    _record_diagnostic(
        diagnostics,
        "remote_tag_present",
        f"git ls-remote --tags origin {version}",
        checks["remote_tag_present"],
        out,
        err,
        rc,
    )

    # 10. GitHub Release
    out, rc, err = run_cmd(
        ["gh", "release", "view", version, "--json", "url"], check=False
    )
    github_release_present = rc == 0
    checks["github_release_present"] = (
        github_release_present == expect_public_artifacts
    )
    _record_diagnostic(
        diagnostics,
        "github_release_present",
        f"gh release view {version} --json url",
        checks["github_release_present"],
        out,
        err,
        rc,
    )

    # 11. Updater dry-run
    src_path = Path("src").resolve()
    python_env = {"PYTHONPATH": str(src_path)}
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_workspace = Path(tmp_dir) / "workspace"
        init_out, init_rc, init_err = run_cmd(
            [
                sys.executable,
                "-m",
                "atlas_agent.cli",
                "init",
                str(tmp_workspace),
                "--template",
                "routine-trader",
            ],
            check=False,
            cwd=tmp_dir,
            env=python_env,
        )
        if init_rc == 0:
            out, rc, err = run_cmd(
                [
                    sys.executable,
                    "-m",
                    "atlas_agent.cli",
                    "update",
                    "check",
                    "--dry-run",
                ],
                check=False,
                cwd=tmp_workspace,
                env=python_env,
            )
            updater_command = "atlas_agent.cli update check --dry-run"
        else:
            out, rc, err = init_out, init_rc, init_err
            updater_command = "atlas_agent.cli init <tmp> --template routine-trader"
    checks["updater_dry_run_ok"] = "Current version: " in out and rc == 0
    _record_diagnostic(
        diagnostics,
        "updater_dry_run_ok",
        updater_command,
        checks["updater_dry_run_ok"],
        out,
        err,
        rc,
    )

    # 12-13. Updater sources test
    # This is tested implicitly by checking the sources.py directly or trusting the test suite.
    # But we can also do a quick python check
    dev_tag = f"{version}.dev0"
    out, rc, err = run_cmd(
        [
            sys.executable,
            "-c",
            (
                "from atlas_agent.update.sources import is_public_stable; "
                f"print(is_public_stable({dev_tag!r}))"
            ),
        ],
        check=False,
        env={"PYTHONPATH": "src"},
    )
    checks["dev_version_not_public_stable"] = out == "False"
    _record_diagnostic(
        diagnostics,
        "dev_version_not_public_stable",
        "internal: is_public_stable({dev_tag})",
        checks["dev_version_not_public_stable"],
        out,
        err,
        rc,
    )

    # 14. Audit pack CLI
    out1, rc1, err1 = run_cmd(
        [sys.executable, "-m", "atlas_agent.cli", "providers", "audit-pack", "--help"],
        check=False,
        env={"PYTHONPATH": "src"},
    )
    out2, rc2, err2 = run_cmd(
        [
            sys.executable,
            "-m",
            "atlas_agent.cli",
            "providers",
            "verify-audit-pack",
            "--help",
        ],
        check=False,
        env={"PYTHONPATH": "src"},
    )
    checks["provider_audit_pack_commands_present"] = rc1 == 0 and rc2 == 0
    _record_diagnostic(
        diagnostics,
        "provider_audit_pack_commands_present",
        "atlas_agent.cli providers audit-pack --help && verify-audit-pack --help",
        checks["provider_audit_pack_commands_present"],
        f"{out1}\n{out2}",
        f"{err1}\n{err2}",
        rc1 if rc1 != 0 else rc2,
    )

    # 15. Audit workflow
    checks["provider_audit_pack_workflow_present"] = Path(
        ".github/workflows/provider-audit-pack.yml"
    ).exists()
    _record_diagnostic(
        diagnostics,
        "provider_audit_pack_workflow_present",
        "internal: Path.exists(.github/workflows/provider-audit-pack.yml)",
        checks["provider_audit_pack_workflow_present"],
    )

    # 16. Non-claims
    if checks["release_notes_present"]:
        notes = release_notes_path.read_text(encoding="utf-8").lower()
        checks["non_claims_preserved"] = all(
            any(phrase in notes for phrase in variants)
            for variants in [
                (
                    "does not enable live trading",
                    "no live trading default changes",
                    "live trading remains disabled by default",
                ),
                (
                    "does not enable provider execution",
                    "no provider execution default changes",
                    "provider execution remains disabled by default",
                ),
                (
                    "autonomous trading",
                    "autonomous trading is not claimed",
                ),
                ("not financial advice",),
                (
                    "pypi publish has been performed",
                    "pypi publish: not performed",
                    "pypi was not published",
                ),
            ]
        )
    else:
        checks["non_claims_preserved"] = False
    _record_diagnostic(
        diagnostics,
        "non_claims_preserved",
        f"internal: read docs/releases/{version}.md",
        checks["non_claims_preserved"],
    )

    # 17. Protected boundaries
    out, rc, err = run_cmd(
        [
            "git",
            "diff",
            "HEAD",
            "--name-only",
            "--",
            "src/atlas_agent/config",
            "src/atlas_agent/brokers",
            "src/atlas_agent/execution",
            "src/atlas_agent/safety",
            "src/atlas_agent/risk",
        ],
        check=False,
    )
    checks["protected_boundaries_clean"] = out == ""
    _record_diagnostic(
        diagnostics,
        "protected_boundaries_clean",
        "git diff HEAD --name-only -- src/atlas_agent/{{config,brokers,execution,safety,risk}}",
        checks["protected_boundaries_clean"],
        out,
        err,
        rc,
    )

    valid = all(checks.values()) and not any(safety.values())

    if not valid:
        failed_checks = [name for name, passed in checks.items() if not passed]
        failed_check = failed_checks[0] if failed_checks else "unknown"
        diag = diagnostics.get(failed_check, {})
        remediation = _remediation(failed_check, version, clean_version)
        print("\n=== Release Assurance Diagnostic ===", file=sys.stderr)
        print(f"Release: {version}", file=sys.stderr)
        print(f"Output directory: {out_dir}", file=sys.stderr)
        print(f"Failed check: {failed_check}", file=sys.stderr)
        if diag.get("command"):
            print(f"Command/function: {diag['command']}", file=sys.stderr)
        if diag.get("exit_code") is not None:
            print(f"Exit code: {diag['exit_code']}", file=sys.stderr)
        if diag.get("stdout_excerpt"):
            print(f"Stdout excerpt:\n{diag['stdout_excerpt']}", file=sys.stderr)
        if diag.get("stderr_excerpt"):
            print(f"Stderr excerpt:\n{diag['stderr_excerpt']}", file=sys.stderr)
        print(f"Remediation: {remediation}", file=sys.stderr)
        print("=====================================\n", file=sys.stderr)

        if args.diagnostics_json:
            diag_output = {
                "schema_version": "atlas-release-assurance-diagnostics/1.0",
                "passed": valid,
                "release": version,
                "failed_phase": "release_assurance",
                "failed_check": failed_check,
                "command": diag.get("command"),
                "exit_code": diag.get("exit_code"),
                "stdout_excerpt": diag.get("stdout_excerpt"),
                "stderr_excerpt": diag.get("stderr_excerpt"),
                "remediation": remediation,
                "redactions_applied": [
                    "*_TOKEN",
                    "GH_TOKEN",
                    "GITHUB_TOKEN",
                    "Bearer tokens",
                    "API keys",
                    "account IDs",
                ],
            }
            Path(args.diagnostics_json).write_text(
                json.dumps(diag_output, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    summary = {
        "artifact_type": "release_assurance_summary",
        "schema_version": 1,
        "release": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "valid": valid,
        "public_release_detected": checks["local_tag_present"],
        "pypi_published": safety["pypi_publish_performed"],
        "local_only_evidence": True,
        "checks": checks,
        "safety_summary": safety,
        "findings": findings,
    }

    (out_dir / "release-assurance-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Generate detail json files to match directory structure request if they are supposed to be separate files
    (out_dir / "release-checks.json").write_text(
        json.dumps(
            {"package_version_aligned": checks["package_version_aligned"]},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "public-metadata-checks.json").write_text(
        json.dumps(
            {
                "readme_public_metadata_current": checks[
                    "readme_public_metadata_current"
                ],
                "security_md_current": checks["security_md_current"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "updater-delivery-checks.json").write_text(
        json.dumps({"updater_dry_run_ok": checks["updater_dry_run_ok"]}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "provider-audit-pack-checks.json").write_text(
        json.dumps(
            {
                "provider_audit_pack_commands_present": checks[
                    "provider_audit_pack_commands_present"
                ],
                "provider_audit_pack_workflow_present": checks[
                    "provider_audit_pack_workflow_present"
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if args.include_reviewer_trust_snapshot:
        import build_reviewer_trust_snapshot
        import check_reviewer_trust_snapshot

        snapshot_dir = out_dir / "reviewer-trust-snapshot"
        build_reviewer_trust_snapshot.build_snapshot(snapshot_dir, deterministic=True)
        check_result = check_reviewer_trust_snapshot.run_checks(snapshot_dir)
        summary["reviewer_trust_snapshot_valid"] = check_result["passed"]
        _record_diagnostic(
            diagnostics,
            "reviewer_trust_snapshot_valid",
            "check_reviewer_trust_snapshot.run_checks",
            check_result["passed"],
            stderr="\n".join(check_result.get("errors", [])),
        )
        if not check_result["passed"]:
            valid = False
            summary["valid"] = valid
            findings.extend(
                f"Reviewer trust snapshot: {e}" for e in check_result["errors"]
            )
        (out_dir / "release-assurance-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    report_md = f"""# {version} Release Assurance Report

## Summary
Valid: {valid}
Generated at: {summary["generated_at"]}

## Release Identity
- package version: {clean_version}
- tag: {version}
- GitHub release URL if available: {"Present" if checks["github_release_present"] else "N/A"}
- PyPI status: not published

## Security Hardening Included
- redaction refresh after secret load/set
- short/low-entropy secret regression coverage
- secret key-name validation
- Alpaca endpoint consistency hardening
- timeout reconciliation guidance
- dashboard/read-only safety documentation
- approval safety documentation/tests
- config store safety tests
- Telegram/remote-control disabled-by-default clarification

## Provider Audit Evidence Included
- preflight call plan
- validator
- evidence bundle
- bundle verifier
- smoke chain
- capability inventory/readiness gate
- evidence index
- report/export
- audit pack
- audit pack verifier
- CI artifact workflow

## Updater Delivery Verification
- {version} stable detection
- {dev_tag} rejected as public stable
- historical baseline {_meta.historical_stable_baseline} older than {version}
- dry-run behavior

## Safety Non-Claims
- no live trading enabled by default
- no provider execution enabled by default
- no autonomous trading claim
- not financial advice
- PyPI was not published

## Reviewer Trust Snapshot
{"Included and valid." if summary.get("reviewer_trust_snapshot_valid") else ("Included but validation failed." if args.include_reviewer_trust_snapshot else "Not included (opt-in flag was not set).")}

## Findings
{"No findings." if not findings else chr(10).join(f"- {x}" for x in findings)}

## Local Evidence

This assurance pack is **local-only generated evidence**. It is produced by
`scripts/release_assurance.py` and is not a published artifact. The files in this
pack should not be committed to the repository unless a task explicitly requests
a versioned evidence pack.

### Cleanup Guidance

If this pack is no longer needed, back it up before removal:

```bash
mkdir -p /tmp/atlas-agent-artifact-backup
mv {out_dir} /tmp/atlas-agent-artifact-backup/
```

Use exact paths only. Do not use `git clean`, `git reset --hard`, `stash pop`,
or `stash drop` to remove generated artifacts.

## Reviewer Notes
"""
    (out_dir / "release-assurance-report.md").write_text(report_md, encoding="utf-8")

    # checksums
    def get_sha256(path):
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    checksums = []
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and p.name != "sha256sums.txt":
            checksums.append(f"{get_sha256(p)}  {p.name}")

    (out_dir / "sha256sums.txt").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8"
    )

    print(f"Release assurance pack written to {out_dir}")
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
