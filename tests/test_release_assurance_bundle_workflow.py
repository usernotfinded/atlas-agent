# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_assurance_bundle_workflow.py
# PURPOSE: Verifies release assurance bundle workflow behavior and regression
#         expectations.
# DEPS:    subprocess, sys, pathlib, pytest, scripts.
# ==============================================================================

"""Static tests for the release assurance bundle demo workflow and its checker."""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_release_assurance_bundle_workflow import check_workflow


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-assurance.yml"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_bundle_workflow.py"
DEMO_SCRIPT = "scripts/demo_release_assurance_snapshot_bundle.sh"
MANIFEST_CHECK_SCRIPT = "scripts/check_release_assurance_bundle_manifest.py"
ARTIFACT_NAME = "release-assurance-bundle-demo"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _modified_workflow(replacement: tuple[str, str]) -> Path:
    original = _workflow_text()
    modified = original.replace(replacement[0], replacement[1])
    tmp = REPO_ROOT / ".pytest_cache" / "release-assurance-bundle-workflow-test.yml"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(modified, encoding="utf-8")
    return tmp


class TestReleaseAssuranceBundleWorkflow:
    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW_PATH.exists(), "release-assurance.yml must exist"

    def test_uses_workflow_dispatch(self) -> None:
        text = _workflow_text()
        assert "workflow_dispatch:" in text

    def test_run_bundle_demo_input_exists(self) -> None:
        text = _workflow_text()
        assert "run_bundle_demo:" in text
        assert "type: boolean" in text

    def test_run_bundle_demo_defaults_to_false(self) -> None:
        text = _workflow_text()
        lines = text.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("run_bundle_demo:"):
                start_idx = i
                break
        assert start_idx is not None
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
        assert "default: false" in block

    def test_bundle_demo_step_is_conditional(self) -> None:
        text = _workflow_text()
        demo_idx = text.find(DEMO_SCRIPT)
        assert demo_idx != -1
        preceding = text[:demo_idx]
        assert "inputs.run_bundle_demo" in preceding

    def test_manifest_checker_step_is_conditional(self) -> None:
        text = _workflow_text()
        manifest_idx = text.find(MANIFEST_CHECK_SCRIPT)
        assert manifest_idx != -1
        preceding = text[:manifest_idx]
        assert "inputs.run_bundle_demo" in preceding

    def test_manifest_checker_runs_before_upload(self) -> None:
        text = _workflow_text()
        manifest_idx = text.find(MANIFEST_CHECK_SCRIPT)
        artifact_name_idx = text.lower().find(ARTIFACT_NAME)
        assert manifest_idx != -1
        assert artifact_name_idx != -1
        assert manifest_idx < artifact_name_idx, "manifest checker must run before artifact upload"

    def test_bundle_demo_script_runs_before_manifest_checker(self) -> None:
        text = _workflow_text()
        demo_idx = text.find(DEMO_SCRIPT)
        manifest_idx = text.find(MANIFEST_CHECK_SCRIPT)
        assert demo_idx != -1
        assert manifest_idx != -1
        assert demo_idx < manifest_idx, "demo script must run before manifest checker"

    def test_artifact_upload_is_conditional(self) -> None:
        text = _workflow_text()
        artifact_idx = text.lower().find(ARTIFACT_NAME)
        assert artifact_idx != -1
        preceding = text[:artifact_idx]
        assert "inputs.run_bundle_demo" in preceding

    def test_artifact_upload_uses_upload_artifact_action(self) -> None:
        text = _workflow_text().lower()
        assert "actions/upload-artifact" in text
        assert ARTIFACT_NAME in text

    def test_permissions_are_read_only(self) -> None:
        text = _workflow_text()
        assert "permissions:" in text
        assert "contents: read" in text
        assert "contents: write" not in text
        assert "actions: write" not in text

    def test_uses_only_safe_github_token(self) -> None:
        text = _workflow_text().lower()
        assert "github.token" in text or "secrets.github_token" in text
        assert "secrets.my_token" not in text
        assert "secrets.api_token" not in text

    def test_does_not_reference_unsafe_secrets(self) -> None:
        text = _workflow_text().lower()
        # The only allowed secrets.* reference is secrets.GITHUB_TOKEN.
        for token_name in ("secrets.my_token", "secrets.api_token", "secrets.pypi_token"):
            assert token_name not in text, f"workflow references unsafe secret {token_name}"

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


class TestReleaseAssuranceBundleWorkflowChecker:
    def test_checker_passes_on_valid_workflow(self) -> None:
        result = check_workflow(WORKFLOW_PATH)
        assert result["passed"], f"Expected workflow to pass, got errors: {result['errors']}"

    def test_checker_fails_on_missing_workflow(self) -> None:
        result = check_workflow(REPO_ROOT / ".github" / "workflows" / "nonexistent.yml")
        assert not result["passed"]
        assert any("not found" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_secrets(self) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_push(self) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run release assurance bundle demo",
                "- name: Bad step\n        run: git push origin main\n      - name: Run release assurance bundle demo",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git push" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_tag(self) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run release assurance bundle demo",
                "- name: Bad step\n        run: git tag v0.0.0\n      - name: Run release assurance bundle demo",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git tag" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_gh_release_create(self) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run release assurance bundle demo",
                "- name: Bad step\n        run: gh release create v0.0.0 --title test\n      - name: Run release assurance bundle demo",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release create" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_twine_upload(self) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run release assurance bundle demo",
                "- name: Bad step\n        run: twine upload dist/*\n      - name: Run release assurance bundle demo",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine upload" in e.lower() for e in result["errors"])

    def test_checker_fails_if_run_bundle_demo_defaults_to_true(self) -> None:
        # Replace the default inside the run_bundle_demo input block.
        original = _workflow_text()
        lines = original.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("run_bundle_demo:"):
                start_idx = i
                break
        assert start_idx is not None
        start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        block_end = start_idx + 1
        for line in lines[start_idx + 1 :]:
            if line.strip() == "":
                block_end += 1
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= start_indent:
                break
            block_end += 1
        modified_lines = lines[:start_idx] + lines[block_end:]
        modified = "\n".join(modified_lines)
        # Insert a run_bundle_demo input that defaults to true.
        new_input = (
            " " * start_indent
            + "run_bundle_demo:\n"
            + " " * (start_indent + 2)
            + 'description: "bad"\n'
            + " " * (start_indent + 2)
            + "type: boolean\n"
            + " " * (start_indent + 2)
            + "default: true\n"
        )
        modified_lines.insert(start_idx, new_input.rstrip())
        modified = "\n".join(modified_lines)
        tmp = REPO_ROOT / ".pytest_cache" / "release-assurance-bundle-default-true.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("default to false" in e.lower() for e in result["errors"])

    def test_checker_fails_if_artifact_upload_is_unconditional(self) -> None:
        original = _workflow_text()
        # Remove the `if:` line immediately before the bundle demo artifact upload step.
        lines = original.splitlines()
        upload_idx: int | None = None
        for i, line in enumerate(lines):
            if "Upload release assurance bundle demo artifact" in line:
                upload_idx = i
                break
        assert upload_idx is not None
        # Find the `if:` line that belongs to this step (between this - name: and the next).
        if_idx: int | None = None
        for j in range(upload_idx + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("- name:"):
                break
            if stripped.startswith("if:"):
                if_idx = j
                break
        assert if_idx is not None, "Could not find conditional line for upload step"
        modified_lines = lines[:if_idx] + lines[if_idx + 1 :]
        modified = "\n".join(modified_lines)
        tmp = REPO_ROOT / ".pytest_cache" / "release-assurance-bundle-upload-unconditional.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("conditional" in e.lower() for e in result["errors"])

    def test_checker_allows_safe_github_token(self) -> None:
        result = check_workflow(WORKFLOW_PATH)
        assert result["passed"], f"Expected workflow to pass, got errors: {result['errors']}"
        assert not any("secret" in e.lower() for e in result["errors"])

    def test_checker_rejects_arbitrary_secret(self) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run static release checks",
                "- name: Run static release checks\n        env:\n          GH_TOKEN: ${{ secrets.MY_TOKEN }}",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_rejects_contents_write(self) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read",
                "permissions:\n  contents: write",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_requires_gh_token_for_static_checks(self) -> None:
        original = _workflow_text()
        # Remove every GH_TOKEN line from the workflow.
        modified = "\n".join(
            line for line in original.splitlines() if "GH_TOKEN" not in line
        )
        assert "GH_TOKEN" not in modified
        tmp = REPO_ROOT / ".pytest_cache" / "release-assurance-no-gh-token.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("gh_token" in e.lower() or "github_token" in e.lower() for e in result["errors"])

    def test_checker_rejects_unsafe_token_source(self) -> None:
        tmp = _modified_workflow(
            (
                "GH_TOKEN: ${{ github.token }}",
                "GH_TOKEN: ${{ secrets.MY_TOKEN }}",
            )
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

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

    def test_cli_fails_on_injected_secrets(self) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            )
        )
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--workflow", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
