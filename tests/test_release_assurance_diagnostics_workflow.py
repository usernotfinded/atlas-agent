"""Static tests for the release assurance diagnostics workflow and its checker."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_release_assurance_diagnostics_workflow import (
    check_workflow,
    _step_has_if,
    _step_if_line,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-assurance.yml"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_diagnostics_workflow.py"
ARTIFACT_NAME = "release-assurance-diagnostics"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _modified_workflow(replacement: tuple[str, str], tmp_path: Path) -> Path:
    original = _workflow_text()
    modified = original.replace(replacement[0], replacement[1])
    tmp = tmp_path / "release-assurance-diagnostics-workflow-test.yml"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(modified, encoding="utf-8")
    return tmp


class TestReleaseAssuranceDiagnosticsWorkflow:
    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW_PATH.exists(), "release-assurance.yml must exist"

    def test_uses_workflow_dispatch(self) -> None:
        text = _workflow_text()
        assert "workflow_dispatch:" in text

    def test_upload_diagnostics_json_input_exists(self) -> None:
        text = _workflow_text()
        assert "upload_diagnostics_json:" in text
        assert "type: boolean" in text

    def test_upload_diagnostics_json_defaults_to_false(self) -> None:
        text = _workflow_text()
        lines = text.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("upload_diagnostics_json:"):
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

    def test_diagnostics_flag_is_conditional(self) -> None:
        text = _workflow_text()
        diag_idx = text.find("--diagnostics-json")
        assert diag_idx != -1
        preceding = text[:diag_idx]
        assert "UPLOAD_DIAGNOSTICS_JSON" in preceding

    def test_diagnostics_artifact_upload_is_conditional(self) -> None:
        text = _workflow_text()
        artifact_idx = text.lower().find(ARTIFACT_NAME)
        assert artifact_idx != -1
        preceding = text[:artifact_idx]
        assert "inputs.upload_diagnostics_json" in preceding

    def test_diagnostics_artifact_upload_uses_ignore_if_no_files_found(self) -> None:
        text = _workflow_text()
        assert "if-no-files-found: ignore" in text

    def test_diagnostics_artifact_uses_upload_artifact_action(self) -> None:
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

    def test_failure_step_exists_and_is_conditional(self) -> None:
        text = _workflow_text()
        assert "Fail if release assurance failed" in text
        assert _step_has_if(text, "Fail if release assurance failed"), (
            "failure step must be conditional"
        )
        if_line = _step_if_line(text, "Fail if release assurance failed")
        assert if_line is not None
        assert "steps.release_assurance.outputs.exit_code" in if_line
        assert "!= '0'" in if_line

    def test_validate_diagnostics_artifact_input_exists(self) -> None:
        text = _workflow_text()
        assert "validate_diagnostics_artifact:" in text
        assert "type: boolean" in text

    def test_validate_diagnostics_artifact_defaults_to_false(self) -> None:
        text = _workflow_text()
        lines = text.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("validate_diagnostics_artifact:"):
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

    def test_validator_step_exists(self) -> None:
        text = _workflow_text()
        assert "Validate release assurance diagnostics artifact" in text
        assert "scripts/check_release_assurance_diagnostics_artifact.py" in text

    def test_validator_step_is_conditional(self) -> None:
        text = _workflow_text()
        if_line = _step_if_line(text, "Validate release assurance diagnostics artifact")
        assert if_line is not None
        if_line_lower = if_line.lower()
        assert "inputs.upload_diagnostics_json" in if_line_lower
        assert "inputs.validate_diagnostics_artifact" in if_line_lower
        assert "steps.release_assurance.outputs.exit_code != '0'" in if_line_lower

    def test_validator_step_runs_before_upload(self) -> None:
        text = _workflow_text()
        validator_pos = text.find("Validate release assurance diagnostics artifact")
        upload_pos = text.find("Upload release assurance diagnostics artifact")
        assert validator_pos != -1
        assert upload_pos != -1
        assert validator_pos < upload_pos


class TestReleaseAssuranceDiagnosticsWorkflowChecker:
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
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_push(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: git push origin main\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git push" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_gh_release_create(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: gh release create v0.0.0 --title test\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release create" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_twine_upload(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: twine upload dist/*\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine upload" in e.lower() for e in result["errors"])

    def test_checker_fails_if_diagnostics_flag_unconditional(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                '          if [[ "${UPLOAD_DIAGNOSTICS_JSON}" == "true" ]]; then\n            flags+=(--diagnostics-json artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json)\n          fi',
                '          flags+=(--diagnostics-json artifacts/x.json)',
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("conditional" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_git_tag(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: git tag v0.0.0\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("git tag" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_gh_release_upload(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: gh release upload v0.0.0 dist/*\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("release upload" in e.lower() for e in result["errors"])

    def test_checker_fails_on_injected_twine_publish(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Upload release assurance diagnostics artifact",
                "- name: Bad step\n        run: twine publish dist/*\n      - name: Upload release assurance diagnostics artifact",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("twine publish" in e.lower() for e in result["errors"])

    def test_checker_fails_if_upload_diagnostics_defaults_to_true(self, tmp_path: Path) -> None:
        original = _workflow_text()
        lines = original.splitlines()
        start_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip().startswith("upload_diagnostics_json:"):
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
        new_input = (
            " " * start_indent
            + "upload_diagnostics_json:\n"
            + " " * (start_indent + 2)
            + 'description: "bad"\n'
            + " " * (start_indent + 2)
            + "type: boolean\n"
            + " " * (start_indent + 2)
            + "default: true\n"
        )
        modified_lines.insert(start_idx, new_input.rstrip())
        modified = "\n".join(modified_lines)
        tmp = tmp_path / "release-assurance-diagnostics-default-true.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("default to false" in e.lower() for e in result["errors"])

    def test_checker_fails_if_diagnostics_artifact_upload_is_unconditional(self, tmp_path: Path) -> None:
        original = _workflow_text()
        lines = original.splitlines()
        upload_idx: int | None = None
        for i, line in enumerate(lines):
            if "Upload release assurance diagnostics artifact" in line:
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
        tmp = tmp_path / "release-assurance-diagnostics-upload-unconditional.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("conditional" in e.lower() for e in result["errors"])

    def test_checker_rejects_arbitrary_secret(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "- name: Run static release checks",
                "- name: Run static release checks\n        env:\n          GH_TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("secret" in e.lower() for e in result["errors"])

    def test_checker_rejects_contents_write(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read",
                "permissions:\n  contents: write",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_rejects_id_token_write(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  id-token: write",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("broad/write permission" in e.lower() for e in result["errors"])

    def test_checker_fails_if_failure_step_if_is_wrong(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "if: steps.release_assurance.outputs.exit_code != '0'\n        env:\n          RA_EXIT_CODE: ${{ steps.release_assurance.outputs.exit_code }}",
                "if: false\n        env:\n          RA_EXIT_CODE: ${{ steps.release_assurance.outputs.exit_code }}",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any(
            "steps.release_assurance.outputs.exit_code != '0'" in e
            for e in result["errors"]
        )

    def test_checker_requires_gh_token_for_static_checks(self, tmp_path: Path) -> None:
        original = _workflow_text()
        modified = "\n".join(
            line for line in original.splitlines() if "GH_TOKEN" not in line
        )
        assert "GH_TOKEN" not in modified
        tmp = tmp_path / "release-assurance-diagnostics-no-gh-token.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("gh_token" in e.lower() or "github_token" in e.lower() for e in result["errors"])

    def test_checker_fails_if_validate_diagnostics_defaults_to_true(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "validate_diagnostics_artifact:\n        description: \"Validate the diagnostics JSON before uploading it\"\n        type: boolean\n        required: false\n        default: false",
                "validate_diagnostics_artifact:\n        description: \"bad\"\n        type: boolean\n        required: false\n        default: true",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any(
            "validate_diagnostics_artifact" in e and "default to false" in e.lower()
            for e in result["errors"]
        )

    def test_checker_fails_if_validator_step_missing(self, tmp_path: Path) -> None:
        tmp = _modified_workflow(
            (
                "      - name: Validate release assurance diagnostics artifact\n        if: >-\n          inputs.upload_diagnostics_json &&\n          inputs.validate_diagnostics_artifact &&\n          steps.release_assurance.outputs.exit_code != '0'\n        run: |\n          python3.11 scripts/check_release_assurance_diagnostics_artifact.py \\\n            artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json\n\n",
                "",
            ),
            tmp_path,
        )
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validate release assurance diagnostics artifact" in e.lower() for e in result["errors"])

    def test_checker_fails_if_validator_step_unconditional(self, tmp_path: Path) -> None:
        original = _workflow_text()
        lines = original.splitlines()
        validator_idx: int | None = None
        for i, line in enumerate(lines):
            if "Validate release assurance diagnostics artifact" in line:
                validator_idx = i
                break
        assert validator_idx is not None
        if_idx: int | None = None
        for j in range(validator_idx + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("- name:"):
                break
            if stripped.startswith("if:"):
                if_idx = j
                break
        assert if_idx is not None
        modified_lines = lines[:if_idx] + lines[if_idx + 1 :]
        modified = "\n".join(modified_lines)
        tmp = tmp_path / "release-assurance-diagnostics-validator-unconditional.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any("validator step must be conditional" in e.lower() for e in result["errors"])

    def test_checker_fails_if_upload_before_validator(self, tmp_path: Path) -> None:
        original = _workflow_text()
        lines = original.splitlines()
        validator_idx: int | None = None
        upload_idx: int | None = None
        for i, line in enumerate(lines):
            if "Validate release assurance diagnostics artifact" in line:
                validator_idx = i
            if "Upload release assurance diagnostics artifact" in line:
                upload_idx = i
        assert validator_idx is not None
        assert upload_idx is not None

        def block_end(start: int) -> int:
            for j in range(start + 1, len(lines)):
                if lines[j].strip().startswith("- name:"):
                    return j
            return len(lines)

        validator_end = block_end(validator_idx)
        upload_end = block_end(upload_idx)
        validator_block = lines[validator_idx:validator_end]
        upload_block = lines[upload_idx:upload_end]
        if validator_idx < upload_idx:
            modified_lines = (
                lines[:validator_idx]
                + upload_block
                + lines[validator_end:upload_idx]
                + validator_block
                + lines[upload_end:]
            )
        else:
            modified_lines = (
                lines[:upload_idx]
                + validator_block
                + lines[upload_end:validator_idx]
                + upload_block
                + lines[validator_end:]
            )
        modified = "\n".join(modified_lines)
        tmp = tmp_path / "release-assurance-diagnostics-upload-before-validator.yml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(modified, encoding="utf-8")
        result = check_workflow(tmp)
        assert not result["passed"]
        assert any(
            "validator step must run before diagnostics artifact upload" in e.lower()
            for e in result["errors"]
        )

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
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  id-token: write\n\nenv:\n  TOKEN: ${{ secrets.MY_TOKEN }}",
            ),
            tmp_path,
        )
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--workflow", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
