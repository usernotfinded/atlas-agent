# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_assurance_diagnostics_artifact_workflow.py
# PURPOSE: Verifies release assurance diagnostics artifact workflow behavior and
#         regression expectations.
# DEPS:    subprocess, sys, pathlib, scripts.
# ==============================================================================

"""Static tests for the diagnostics artifact revalidation workflow and its checker."""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_release_assurance_diagnostics_artifact_workflow import (
    check_workflow,
)


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "release-assurance-diagnostics-artifact-validate.yml"
)
CHECK_SCRIPT = (
    REPO_ROOT / "scripts" / "check_release_assurance_diagnostics_artifact_workflow.py"
)
ARTIFACT_NAME = "release-assurance-diagnostics"
VALIDATION_ARTIFACT_NAME = "release-assurance-diagnostics-validation"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _modified_workflow(replacement: tuple[str, str], tmp_path: Path) -> Path:
    original = _workflow_text()
    modified = original.replace(replacement[0], replacement[1])
    tmp = tmp_path / "release-assurance-diagnostics-artifact-workflow-test.yml"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(modified, encoding="utf-8")
    return tmp


class TestRevalidationWorkflow:
    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW_PATH.exists(), "release-assurance-diagnostics-artifact-validate.yml must exist"

    def test_uses_workflow_dispatch_only(self) -> None:
        text = _workflow_text()
        assert "workflow_dispatch:" in text
        assert "push:" not in text
        assert "pull_request:" not in text
        assert "schedule:" not in text

    def test_source_run_id_input_exists_and_is_required(self) -> None:
        text = _workflow_text()
        assert "source_run_id:" in text
        block = _input_block(text, "source_run_id")
        assert "type: string" in block
        assert "required: true" in block

    def test_artifact_name_default_is_correct(self) -> None:
        text = _workflow_text()
        block = _input_block(text, "artifact_name")
        assert "type: string" in block
        assert "required: false" in block
        assert "default: release-assurance-diagnostics" in block

    def test_allow_passed_defaults_to_false(self) -> None:
        text = _workflow_text()
        block = _input_block(text, "allow_passed")
        assert "type: boolean" in block
        assert "required: false" in block
        assert "default: false" in block

    def test_permissions_are_read_only(self) -> None:
        text = _workflow_text()
        assert "permissions:" in text
        assert "contents: read" in text
        assert "actions: read" in text
        assert "contents: write" not in text
        assert "actions: write" not in text
        assert "id-token: write" not in text

    def test_uses_only_safe_github_token(self) -> None:
        text = _workflow_text().lower()
        assert "github.token" in text
        assert "secrets." not in text

    def test_uses_gh_run_download(self) -> None:
        text = _workflow_text()
        assert "gh run download" in text

    def test_calls_diagnostics_artifact_validator(self) -> None:
        text = _workflow_text()
        assert "scripts/check_release_assurance_diagnostics_artifact.py" in text

    def test_uploads_validation_report_artifact(self) -> None:
        text = _workflow_text()
        assert VALIDATION_ARTIFACT_NAME in text
        assert "actions/upload-artifact" in text.lower()

    def test_does_not_publish_or_release(self) -> None:
        text = _workflow_text().lower()
        assert "twine upload" not in text
        assert "gh release create" not in text
        assert "gh release upload" not in text
        assert "git push" not in text
        assert "git tag" not in text

    def test_disables_live_trading(self) -> None:
        text = _workflow_text()
        assert 'ENABLE_LIVE_TRADING: "false"' in text
        assert 'PROVIDER_EXECUTION_ENABLED: "false"' in text
        assert 'BROKER_EXECUTION_ENABLED: "false"' in text


class TestRevalidationWorkflowChecker:
    def test_checker_passes_on_valid_workflow(self) -> None:
        result = check_workflow(WORKFLOW_PATH)
        assert result["passed"], f"Expected workflow to pass, got errors: {result['errors']}"

    def test_checker_fails_on_missing_workflow(self) -> None:
        result = check_workflow(REPO_ROOT / ".github" / "workflows" / "nonexistent.yml")
        assert not result["passed"]
        assert any("not found" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_secrets(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: read\n  actions: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_push(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: git push origin main\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git push" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_gh_release_create(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: gh release create v0.0.0 --title test\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release create" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_twine_upload(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: twine upload dist/*\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine upload" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_tag(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: git tag v0.0.0\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git tag" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_gh_release_upload(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: gh release upload v0.0.0 dist/*\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release upload" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_twine_publish(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Bad step\n        run: twine publish dist/*\n      - name: Download diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine publish" in e.lower() for e in result["errors"])

    def test_checker_rejects_arbitrary_secret(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Download diagnostics artifact",
                "      - name: Download diagnostics artifact\n        env:\n          GH_TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_rejects_contents_write(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: write\n  actions: read",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_rejects_actions_write(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: read\n  actions: write",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_rejects_id_token_write(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: read\n  actions: read\n  id-token: write",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_requires_gh_token(self, tmp_path: Path) -> None:
        original = _workflow_text()
        modified = "\n".join(
            line for line in original.splitlines() if "GH_TOKEN:" not in line
        )
        assert "GH_TOKEN:" not in modified
        tmp = tmp_path / "revalidation-workflow-no-gh-token.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("gh_token" in e.lower() or "github_token" in e.lower() for e in result["errors"])

    def test_checker_fails_if_source_run_id_not_required(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "source_run_id:\n        description: \"GitHub Actions run ID that produced the diagnostics artifact\"\n        type: string\n        required: true",
                "source_run_id:\n        description: \"bad\"\n        type: string\n        required: false",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("source_run_id" in e and "required: true" in e for e in result["errors"])

    def test_checker_fails_if_artifact_name_default_wrong(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "artifact_name:\n        description: \"Name of the diagnostics artifact to download\"\n        type: string\n        required: false\n        default: release-assurance-diagnostics",
                "artifact_name:\n        description: \"bad\"\n        type: string\n        required: false\n        default: wrong-name",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("artifact_name" in e and "default to" in e.lower() for e in result["errors"])

    def test_checker_fails_if_allow_passed_defaults_to_true(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "allow_passed:\n        description: \"Allow diagnostics where 'passed' is true\"\n        type: boolean\n        required: false\n        default: false",
                "allow_passed:\n        description: \"bad\"\n        type: boolean\n        required: false\n        default: true",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("allow_passed" in e and "default to" in e.lower() for e in result["errors"])

    def test_checker_fails_if_gh_run_download_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "gh run download \"${SOURCE_RUN_ID}\"",
                "gh run fetch \"${SOURCE_RUN_ID}\"",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("gh run download" in e for e in result["errors"])

    def test_checker_fails_if_validator_command_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "scripts/check_release_assurance_diagnostics_artifact.py",
                "scripts/check_release_assurance_diagnostics_artifact_MISSING.py",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("check_release_assurance_diagnostics_artifact.py" in e for e in result["errors"])

    def test_checker_fails_if_validation_report_upload_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "name: release-assurance-diagnostics-validation",
                "name: diagnostics-validation-report",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release-assurance-diagnostics-validation" in e for e in result["errors"])

    def test_cli_returns_zero_on_valid_workflow(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_cli_json_output_on_valid_workflow(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"passed": true' in result.stdout

    def test_cli_fails_on_injected_secrets(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read\n  actions: read",
                "permissions:\n  contents: read\n  actions: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--workflow", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


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
