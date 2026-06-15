"""Static tests for the reviewer trust snapshot workflow and its checker."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_reviewer_trust_snapshot_workflow import check_workflow


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _workflow_path() -> Path:
    return _repo_root() / ".github" / "workflows" / "reviewer-trust-snapshot.yml"


def _workflow_text() -> str:
    return _workflow_path().read_text(encoding="utf-8")


class TestReviewerTrustSnapshotWorkflow:
    def test_workflow_file_exists(self) -> None:
        assert _workflow_path().exists(), "reviewer-trust-snapshot.yml must exist"

    def test_uses_python_311(self) -> None:
        assert "3.11" in _workflow_text()

    def test_triggers_workflow_dispatch_only(self) -> None:
        text = _workflow_text()
        assert "workflow_dispatch:" in text
        assert "push:" not in text
        assert "pull_request:" not in text
        assert "schedule:" not in text

    def test_permissions_are_read_only(self) -> None:
        text = _workflow_text()
        assert "permissions:" in text
        assert "contents: read" in text
        assert "contents: write" not in text
        assert "actions: write" not in text

    def test_does_not_reference_secrets(self) -> None:
        assert "secrets." not in _workflow_text().lower()

    def test_does_not_publish_or_release(self) -> None:
        text = _workflow_text().lower()
        assert "twine upload" not in text
        assert "gh release create" not in text
        assert "gh release upload" not in text
        assert "git push" not in text
        assert "git tag" not in text

    def test_uploads_artifact(self) -> None:
        text = _workflow_text().lower()
        assert "actions/upload-artifact" in text
        assert "reviewer-trust-snapshot" in text

    def test_calls_builder(self) -> None:
        assert "scripts/build_reviewer_trust_snapshot.py" in _workflow_text()

    def test_calls_checker(self) -> None:
        assert "scripts/check_reviewer_trust_snapshot.py" in _workflow_text()

    def test_disables_live_trading(self) -> None:
        text = _workflow_text()
        assert 'ENABLE_LIVE_TRADING: "false"' in text
        assert 'PROVIDER_EXECUTION_ENABLED: "false"' in text
        assert 'BROKER_EXECUTION_ENABLED: "false"' in text


class TestReviewerTrustSnapshotWorkflowChecker:
    def test_checker_passes_on_valid_workflow(self) -> None:
        result = check_workflow(_workflow_path())
        assert result["passed"], f"Expected workflow to pass, got errors: {result['errors']}"

    def test_checker_fails_on_missing_workflow(self) -> None:
        result = check_workflow(_repo_root() / ".github" / "workflows" / "nonexistent.yml")
        assert not result["passed"]
        assert any("not found" in e.lower() for e in result["errors"])

    def _modified_workflow(self, replacement: tuple[str, str]) -> Path:
        original = _workflow_text()
        modified = original.replace(replacement[0], replacement[1])
        tmp = _repo_root() / ".pytest_cache" / "reviewer-trust-snapshot-test.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        return tmp

    def test_checker_fails_on_injected_secrets(self) -> None:
        tmp = self._modified_workflow(
            ("permissions:\n  contents: read", "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}")
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_push(self) -> None:
        tmp = self._modified_workflow(
            ("- name: Validate reviewer trust snapshot", "- name: Bad step\n        run: git push origin main\n      - name: Validate reviewer trust snapshot")
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git push" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_release_creation(self) -> None:
        tmp = self._modified_workflow(
            ("- name: Validate reviewer trust snapshot", "- name: Bad step\n        run: gh release create v0.0.0 --title test\n      - name: Validate reviewer trust snapshot")
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release create" in e.lower() for e in result["errors"])

    def test_checker_fails_on_pypi_publish_command(self) -> None:
        tmp = self._modified_workflow(
            ("- name: Validate reviewer trust snapshot", "- name: Bad step\n        run: twine upload dist/*\n      - name: Validate reviewer trust snapshot")
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine upload" in e.lower() for e in result["errors"])

    def test_checker_fails_if_artifact_upload_removed(self) -> None:
        text = _workflow_text()
        modified = text.replace("actions/upload-artifact@v6", "")
        modified = modified.replace("name: reviewer-trust-snapshot", "")
        tmp = _repo_root() / ".pytest_cache" / "reviewer-trust-snapshot-no-upload.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("upload" in e.lower() for e in result["errors"])

    def test_checker_fails_on_auto_trigger(self) -> None:
        text = _workflow_text()
        modified = text.replace("on:\n  workflow_dispatch:", "on:\n  push:\n    branches: [main]")
        tmp = _repo_root() / ".pytest_cache" / "reviewer-trust-snapshot-auto.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("push" in e.lower() for e in result["errors"])

    def test_cli_returns_zero_on_valid_workflow(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_repo_root() / "scripts" / "check_reviewer_trust_snapshot_workflow.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_cli_json_output_on_valid_workflow(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_repo_root() / "scripts" / "check_reviewer_trust_snapshot_workflow.py"), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"passed": true' in result.stdout

    def test_cli_fails_on_injected_secrets(self) -> None:
        tmp = self._modified_workflow(
            ("permissions:\n  contents: read", "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}")
        )
        result = subprocess.run(
            [sys.executable, str(_repo_root() / "scripts" / "check_reviewer_trust_snapshot_workflow.py"), "--workflow", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
