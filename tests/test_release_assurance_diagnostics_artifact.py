# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_assurance_diagnostics_artifact.py
# PURPOSE: Verifies release assurance diagnostics artifact behavior and
#         regression expectations.
# DEPS:    json, subprocess, sys, zipfile, pathlib, pytest, additional local
#         modules.
# ==============================================================================

"""Tests for the release-assurance diagnostics artifact validator (CAND-013)."""

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_release_assurance_diagnostics_artifact import (
    ValidationOptions,
    validate_diagnostics_artifact,
)


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_diagnostics_artifact.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _valid_diagnostics(
    *,
    release: str = "v0.0.0-does-not-exist",
    failed_check: str = "package_version_aligned",
    passed: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "atlas-release-assurance-diagnostics/1.0",
        "passed": passed,
        "release": release,
        "failed_phase": "release_assurance",
        "failed_check": failed_check,
        "command": "internal: read pyproject.toml and src/atlas_agent/__init__.py",
        "exit_code": 0,
        "stdout_excerpt": "",
        "stderr_excerpt": "",
        "remediation": "Verify pyproject.toml and src/atlas_agent/__init__.py both declare the expected version.",
        "redactions_applied": [
            "*_TOKEN",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "Bearer tokens",
            "API keys",
            "account IDs",
        ],
    }


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _zip_directory(source_dir: Path) -> Path:
    zip_path = source_dir.parent / "diagnostics.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir.parent))
    return zip_path


class TestValidateFile:
    def test_valid_json_file_passes(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is True, result["errors"]
        assert result["diagnostics_path"] == str(diag_path)

    def test_any_json_file_name_passes(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "my-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is True, result["errors"]

    def test_invalid_json_file_fails(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        diag_path.write_text("not json", encoding="utf-8")
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert result.get("operational_error") is True
        assert "invalid json" in " ".join(result["errors"]).lower()


class TestValidateDirectory:
    def test_valid_directory_passes(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = validate_diagnostics_artifact(tmp_path)
        assert result["passed"] is True, result["errors"]
        assert result["diagnostics_path"] == str(diag_path)

    def test_missing_json_in_directory_fails(self, tmp_path: Path) -> None:
        result = validate_diagnostics_artifact(tmp_path)
        assert result["passed"] is False
        assert result.get("operational_error") is True
        assert "not found" in " ".join(result["errors"]).lower()

    def test_nested_directory_passes(self, tmp_path: Path) -> None:
        nested = tmp_path / "release-assurance-diagnostics"
        nested.mkdir()
        diag_path = nested / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = validate_diagnostics_artifact(tmp_path)
        assert result["passed"] is True, result["errors"]
        assert result["diagnostics_path"] == str(diag_path)


class TestValidateZip:
    def test_valid_zip_passes(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "release-assurance-diagnostics"
        artifact_dir.mkdir()
        diag_path = artifact_dir / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        zip_path = _zip_directory(artifact_dir)
        result = validate_diagnostics_artifact(zip_path)
        assert result["passed"] is True, result["errors"]
        assert result["artifact_path"] == str(zip_path)

    def test_bad_zip_fails(self, tmp_path: Path) -> None:
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip", encoding="utf-8")
        result = validate_diagnostics_artifact(bad_zip)
        assert result["passed"] is False
        assert result.get("operational_error") is True
        assert "zip" in " ".join(result["errors"]).lower()


class TestSchemaValidation:
    def test_wrong_schema_version_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["schema_version"] = "atlas-release-assurance-diagnostics/2.0"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("schema_version" in e for e in result["errors"])

    def test_missing_required_field_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        del data["remediation"]
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("remediation" in e for e in result["errors"])

    def test_passed_true_fails_by_default(self, tmp_path: Path) -> None:
        data = _valid_diagnostics(passed=True, failed_check="")
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("allow-passed" in e.lower() for e in result["errors"])

    def test_passed_true_passes_with_allow_passed(self, tmp_path: Path) -> None:
        data = _valid_diagnostics(passed=True, failed_check="")
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        options = ValidationOptions(allow_passed=True)
        result = validate_diagnostics_artifact(diag_path, options)
        assert result["passed"] is True, result["errors"]

    def test_empty_failed_check_when_failed_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["failed_check"] = ""
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("failed_check" in e for e in result["errors"])

    def test_empty_remediation_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["remediation"] = ""
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("remediation" in e for e in result["errors"])

    def test_empty_redactions_applied_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["redactions_applied"] = []
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("redactions_applied" in e for e in result["errors"])


class TestExpectations:
    def test_expect_release_mismatch_fails(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(release="v0.6.11"))
        options = ValidationOptions(expect_release="v0.6.12")
        result = validate_diagnostics_artifact(diag_path, options)
        assert result["passed"] is False
        assert any("mismatch" in e.lower() for e in result["errors"])

    def test_expect_release_match_passes(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(release="v0.6.11"))
        options = ValidationOptions(expect_release="v0.6.11")
        result = validate_diagnostics_artifact(diag_path, options)
        assert result["passed"] is True, result["errors"]

    def test_expect_failed_check_mismatch_fails(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(failed_check="package_version_aligned"))
        options = ValidationOptions(expect_failed_check="github_release_present")
        result = validate_diagnostics_artifact(diag_path, options)
        assert result["passed"] is False
        assert any("mismatch" in e.lower() for e in result["errors"])

    def test_expect_failed_check_match_passes(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(failed_check="package_version_aligned"))
        options = ValidationOptions(expect_failed_check="package_version_aligned")
        result = validate_diagnostics_artifact(diag_path, options)
        assert result["passed"] is True, result["errors"]


class TestSafetyScan:
    def test_raw_gh_token_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "error: GH_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("gh_token" in e.lower() or "token assignment" in e.lower() for e in result["errors"])

    def test_redacted_gh_token_passes(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "error: GH_TOKEN=<redacted>"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is True, result["errors"]

    def test_raw_github_token_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stdout_excerpt"] = "GITHUB_TOKEN=ghs_99999999999999999999999999999999999999"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("github_token" in e.lower() or "token assignment" in e.lower() for e in result["errors"])

    def test_arbitrary_token_assignment_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stdout_excerpt"] = "MY_API_TOKEN=supersecretvalue12345"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("token assignment" in e.lower() for e in result["errors"])

    def test_github_token_prefix_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "header: ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("github token prefix" in e.lower() for e in result["errors"])

    def test_sk_api_key_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stdout_excerpt"] = "sk-12345678901234567890abcdef"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("api key" in e.lower() for e in result["errors"])

    def test_apca_key_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        # Non-hex segment prevents the UUID pattern from matching first.
        data["stdout_excerpt"] = "APCA-ABGD1234-1234-1234-123456789012"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("alpaca" in e.lower() for e in result["errors"])

    def test_bearer_token_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "Authorization: Bearer abcdef1234567890"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("bearer" in e.lower() for e in result["errors"])

    def test_bearer_tokens_redaction_label_passes(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["redactions_applied"] = list(data["redactions_applied"]) + ["Bearer tokens"]
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is True, result["errors"]

    def test_uuid_account_id_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stdout_excerpt"] = "account 123e4567-e89b-12d3-a456-426614174000"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("uuid" in e.lower() for e in result["errors"])

    def test_unsafe_git_push_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "git push origin main"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("git push" in e.lower() for e in result["errors"])

    def test_unsafe_git_tag_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "git tag v0.0.0"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("git tag" in e.lower() for e in result["errors"])

    def test_unsafe_gh_release_create_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "gh release create v0.0.0 --title test"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("gh release create" in e.lower() for e in result["errors"])

    def test_unsafe_gh_release_upload_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "gh release upload v0.0.0 dist/*"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("gh release upload" in e.lower() for e in result["errors"])

    def test_unsafe_twine_upload_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "twine upload dist/*"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("twine upload" in e.lower() for e in result["errors"])

    def test_unsafe_twine_publish_fails(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        data["stderr_excerpt"] = "twine publish dist/*"
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = validate_diagnostics_artifact(diag_path)
        assert result["passed"] is False
        assert any("twine publish" in e.lower() for e in result["errors"])


class TestCLI:
    def _run(self, *args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(a) for a in args],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=60,
        )

    def test_help_works(self) -> None:
        result = self._run(sys.executable, CHECK_SCRIPT, "--help", cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()

    def test_unknown_option_fails(self) -> None:
        result = self._run(sys.executable, CHECK_SCRIPT, "--bad-option", cwd=REPO_ROOT)
        assert result.returncode != 0
        assert "unrecognized" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_cli_passes_on_valid_file(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = self._run(sys.executable, CHECK_SCRIPT, str(diag_path), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert "PASSED" in result.stdout

    def test_cli_fails_on_validation_error(self, tmp_path: Path) -> None:
        data = _valid_diagnostics()
        del data["remediation"]
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, data)
        result = self._run(sys.executable, CHECK_SCRIPT, str(diag_path), cwd=REPO_ROOT)
        assert result.returncode == 1

    def test_cli_fails_on_operational_error(self, tmp_path: Path) -> None:
        result = self._run(sys.executable, CHECK_SCRIPT, str(tmp_path / "missing.json"), cwd=REPO_ROOT)
        assert result.returncode == 2

    def test_cli_json_output(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics())
        result = self._run(sys.executable, CHECK_SCRIPT, str(diag_path), "--json", cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output["passed"] is True
        assert "artifact_path" in output
        assert "diagnostics_path" in output
        assert "errors" in output

    def test_cli_expect_release(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(release="v0.0.0-does-not-exist"))
        result = self._run(
            sys.executable,
            CHECK_SCRIPT,
            str(diag_path),
            "--expect-release",
            "v0.0.0-does-not-exist",
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr

    def test_cli_expect_failed_check(self, tmp_path: Path) -> None:
        diag_path = tmp_path / "release-assurance-diagnostics.json"
        _write_json(diag_path, _valid_diagnostics(failed_check="package_version_aligned"))
        result = self._run(
            sys.executable,
            CHECK_SCRIPT,
            str(diag_path),
            "--expect-failed-check",
            "package_version_aligned",
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr


class TestRealRepo:
    def test_checker_passes_on_real_repo_fixture(self, tmp_path: Path) -> None:
        """Generate a real diagnostics JSON and validate it end-to-end."""
        from scripts.release_assurance import main as release_assurance_main

        diagnostics_path = tmp_path / "release-assurance-diagnostics.json"
        output_dir = tmp_path / "assurance"

        old_argv = sys.argv
        try:
            sys.argv = [
                "release_assurance.py",
                "--version",
                "v0.0.0-does-not-exist",
                "--output",
                str(output_dir),
                "--diagnostics-json",
                str(diagnostics_path),
            ]
            with pytest.raises(SystemExit) as exc_info:
                release_assurance_main()
            assert exc_info.value.code == 1
        finally:
            sys.argv = old_argv

        result = validate_diagnostics_artifact(diagnostics_path)
        assert result["passed"] is True, result["errors"]

    def test_expect_release_matches_real_fixture(self, tmp_path: Path) -> None:
        from scripts.release_assurance import main as release_assurance_main

        diagnostics_path = tmp_path / "release-assurance-diagnostics.json"
        output_dir = tmp_path / "assurance"

        old_argv = sys.argv
        try:
            sys.argv = [
                "release_assurance.py",
                "--version",
                "v0.0.0-does-not-exist",
                "--output",
                str(output_dir),
                "--diagnostics-json",
                str(diagnostics_path),
            ]
            with pytest.raises(SystemExit):
                release_assurance_main()
        finally:
            sys.argv = old_argv

        options = ValidationOptions(expect_release="v0.0.0-does-not-exist")
        result = validate_diagnostics_artifact(diagnostics_path, options)
        assert result["passed"] is True, result["errors"]
