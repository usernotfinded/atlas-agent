# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_assurance_artifact_retention_audit.py
# PURPOSE: Verifies release assurance artifact retention audit behavior and
#         regression expectations.
# DEPS:    json, subprocess, sys, datetime, pathlib, pytest, additional local
#         modules.
# ==============================================================================

"""Tests for the release-assurance artifact retention audit script and checker.

All audit-script tests use fixture mode with a deterministic --reference-time so
no live GitHub API calls are made. Checker tests validate the static safety
scanner against the real workflow and synthetic unsafe variants.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.check_release_assurance_artifact_retention_audit import (
    check,
)


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_release_assurance_artifact_retention.py"
CHECK_SCRIPT = (
    REPO_ROOT / "scripts" / "check_release_assurance_artifact_retention_audit.py"
)
WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "release-assurance-artifact-retention-audit.yml"
)

REFERENCE_TIME = "2024-01-05T00:00:00Z"
REPORT_JSON = "release-assurance-artifact-retention-report.json"
REPORT_MD = "release-assurance-artifact-retention-report.md"

WATCHED_NAMES = [
    "release-assurance-diagnostics",
    "release-assurance-diagnostics-validation",
    "release-assurance-bundle-demo",
    "reviewer-trust-snapshot",
]


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _artifact(
    *,
    artifact_id: int,
    name: str,
    created_at: str,
    expires_at: str,
    expired: bool = False,
    run_id: int | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": artifact_id,
        "name": name,
        "created_at": created_at,
        "expires_at": expires_at,
        "expired": expired,
    }
    if run_id is not None:
        record["workflow_run"] = {"id": run_id}
    return record


def _fixture(*artifacts: dict[str, object]) -> dict[str, object]:
    return {"total_count": len(artifacts), "artifacts": list(artifacts)}


def _write_fixture(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_audit(*extra: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), *map(str, extra)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )


class TestAuditScriptFixtureMode:
    def test_fixture_produces_json_and_markdown_reports(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-15T00:00:00Z",
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        assert (output_dir / REPORT_JSON).is_file()
        assert (output_dir / REPORT_MD).is_file()

    def test_watched_names_are_filtered(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-15T00:00:00Z",
                    run_id=101,
                ),
                _artifact(
                    artifact_id=2,
                    name="unrelated-artifact",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-15T00:00:00Z",
                    run_id=102,
                ),
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / REPORT_JSON).read_text(encoding="utf-8"))
        matched = [a for a in report["artifacts"] if a["matches_watched_names"]]
        assert len(matched) == 1
        assert matched[0]["name"] == "release-assurance-diagnostics"
        assert report["summary"]["watched"] == 1

    def test_age_and_days_until_expiry_are_deterministic(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-10T00:00:00Z",
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / REPORT_JSON).read_text(encoding="utf-8"))
        record = report["artifacts"][0]
        assert record["age_days"] == 4
        assert record["days_until_expiry"] == 5
        assert "generated_at" in report
        assert report["generated_at"].startswith("2024-01-05")

    def test_expired_artifact_labeled_expired(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-02T00:00:00Z",
                    expired=True,
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / REPORT_JSON).read_text(encoding="utf-8"))
        assert report["artifacts"][0]["retention_status"] == "expired"
        assert report["summary"]["expired"] == 1

    def test_near_expiry_artifact_labeled_near_expiry(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-07T00:00:00Z",
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / REPORT_JSON).read_text(encoding="utf-8"))
        assert report["artifacts"][0]["retention_status"] == "near_expiry"
        assert report["artifacts"][0]["days_until_expiry"] == 2
        assert report["summary"]["near_expiry"] == 1

    def test_no_matching_artifacts_produces_valid_report(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="totally-unrelated",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-15T00:00:00Z",
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / REPORT_JSON).read_text(encoding="utf-8"))
        assert report["summary"]["watched"] == 0
        assert report["summary"]["total"] == 1
        assert report["artifacts"][0]["matches_watched_names"] is False

    def test_cli_json_output(self, tmp_path: Path) -> None:
        fixture = tmp_path / "artifacts.json"
        output_dir = tmp_path / "out"
        _write_fixture(
            fixture,
            _fixture(
                _artifact(
                    artifact_id=1,
                    name="release-assurance-diagnostics",
                    created_at="2024-01-01T00:00:00Z",
                    expires_at="2024-01-15T00:00:00Z",
                    run_id=101,
                )
            ),
        )

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
            "--older-than-days",
            "0",
            "--near-expiry-days",
            "3",
            "--reference-time",
            REFERENCE_TIME,
            "--json",
        )
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output["passed"] is True
        assert "json_report" in output
        assert "markdown_report" in output
        assert "summary" in output

    def test_cli_help_works(self) -> None:
        result = _run_audit("--help")
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
        assert "--input-json" in result.stdout

    def test_bad_input_json_fails(self, tmp_path: Path) -> None:
        fixture = tmp_path / "bad.json"
        fixture.write_text("not json", encoding="utf-8")
        output_dir = tmp_path / "out"

        result = _run_audit(
            "--input-json",
            fixture,
            "--output-dir",
            output_dir,
        )
        assert result.returncode != 0
        assert "validation" in (result.stdout + result.stderr).lower()


class TestChecker:
    def _modified_workflow(self, replacement: tuple[str, str], tmp_path: Path) -> Path:
        original = WORKFLOW_PATH.read_text(encoding="utf-8")
        modified = original.replace(replacement[0], replacement[1])
        tmp = tmp_path / "retention-audit-workflow-test.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        return tmp

    def test_checker_passes_on_real_repo(self) -> None:
        result = check(WORKFLOW_PATH, AUDIT_SCRIPT)
        assert result["passed"] is True, result["errors"]

    def test_checker_json_output(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        output = json.loads(result.stdout)
        assert output["passed"] is True
        assert "summary" in output
        assert "errors" in output

    def test_checker_rejects_gh_run_download(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "      - name: Audit artifact retention",
                "      - name: Bad step\n        run: gh run download 123\n      - name: Audit artifact retention",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("download" in e.lower() for e in result["errors"])

    def test_checker_rejects_download_artifact(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "      - name: Audit artifact retention",
                "      - name: Bad step\n        uses: actions/download-artifact@v4\n      - name: Audit artifact retention",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("download" in e.lower() for e in result["errors"])

    def test_checker_rejects_delete_method(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "      - name: Audit artifact retention",
                "      - name: Bad step\n        run: gh api -X DELETE repos/owner/repo/actions/artifacts/1\n      - name: Audit artifact retention",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("delete" in e.lower() or "mutate" in e.lower() for e in result["errors"])

    def test_checker_rejects_contents_write(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: write\n  actions: read",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_rejects_arbitrary_secrets(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: read\n  actions: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_rejects_release_tag_pypi_commands(self, tmp_path: Path) -> None:
        tmp = self._modified_workflow(
            (
                "      - name: Upload retention audit report",
                "      - name: Bad step\n        run: |\n          git tag v0.0.0\n          gh release create v0.0.0\n          twine upload dist/*\n      - name: Upload retention audit report",
            ),
            tmp_path,
        )
        result = check(tmp, AUDIT_SCRIPT)
        assert result["passed"] is False
        assert any("git tag" in e.lower() for e in result["errors"])
        assert any("release create" in e.lower() for e in result["errors"])
        assert any("twine upload" in e.lower() for e in result["errors"])


class TestWorkflowFile:
    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW_PATH.exists(), "release-assurance-artifact-retention-audit.yml must exist"

    def test_workflow_is_workflow_dispatch_only(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "workflow_dispatch:" in text
        assert "push:" not in text
        assert "pull_request:" not in text
        assert "schedule:" not in text

    def test_workflow_permissions_read_only(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "permissions:" in text
        assert "contents: read" in text
        assert "actions: read" in text
        assert "contents: write" not in text
        assert "actions: write" not in text
