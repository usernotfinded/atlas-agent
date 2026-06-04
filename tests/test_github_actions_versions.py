"""Tests for GitHub Actions action major policy checks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_github_actions_versions.py"
DOC = REPO_ROOT / "docs" / "development" / "github-actions.md"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_github_actions_versions_for_tests",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _write_workflow(repo_root: Path, text: str) -> Path:
    workflow_dir = repo_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "ci.yml"
    workflow.write_text(text, encoding="utf-8")
    return workflow


def _valid_workflow() -> str:
    return """\
name: CI
on:
  workflow_dispatch:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - uses: actions/upload-artifact@v6
        with:
          name: local-artifact
          path: artifacts/local
"""


def _report_for_action(tmp_path: Path, action_ref: str):
    workflow = _valid_workflow().replace("actions/checkout@v6", action_ref)
    if action_ref.startswith("actions/setup-python"):
        workflow = _valid_workflow().replace("actions/setup-python@v6", action_ref)
    if action_ref.startswith("actions/upload-artifact"):
        workflow = _valid_workflow().replace("actions/upload-artifact@v6", action_ref)
    _write_workflow(tmp_path, workflow)
    return CHECKER.collect_report(tmp_path)


def test_checker_text_mode_passes_on_current_workflows(capsys) -> None:
    exit_code = CHECKER.main([str(REPO_ROOT)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "GitHub Actions version check PASSED" in captured.out
    assert "checkout_uses_v6: PASS" in captured.out


def test_checker_json_mode_returns_expected_artifact_type(capsys) -> None:
    exit_code = CHECKER.main(["--json", str(REPO_ROOT)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["artifact_type"] == "atlas_github_actions_version_report"
    assert payload["valid"] is True


def test_checker_flags_checkout_v4(tmp_path: Path) -> None:
    report = _report_for_action(tmp_path, "actions/checkout@v4")

    assert report.exit_code == 1
    assert report.checks["checkout_uses_v6"] is False
    assert any("actions/checkout uses @v4" in f.detail for f in report.findings)


def test_checker_flags_checkout_v5(tmp_path: Path) -> None:
    report = _report_for_action(tmp_path, "actions/checkout@v5")

    assert report.exit_code == 1
    assert report.checks["checkout_uses_v6"] is False
    assert any("actions/checkout uses @v5" in f.detail for f in report.findings)


def test_checker_flags_setup_python_v5(tmp_path: Path) -> None:
    report = _report_for_action(tmp_path, "actions/setup-python@v5")

    assert report.exit_code == 1
    assert report.checks["setup_python_uses_v6"] is False
    assert any("actions/setup-python uses @v5" in f.detail for f in report.findings)


def test_checker_flags_upload_artifact_v4(tmp_path: Path) -> None:
    report = _report_for_action(tmp_path, "actions/upload-artifact@v4")

    assert report.exit_code == 1
    assert report.checks["upload_artifact_uses_v6"] is False
    assert any("actions/upload-artifact uses @v4" in f.detail for f in report.findings)


def test_checker_flags_upload_artifact_v5(tmp_path: Path) -> None:
    report = _report_for_action(tmp_path, "actions/upload-artifact@v5")

    assert report.exit_code == 1
    assert report.checks["upload_artifact_uses_v6"] is False
    assert any("actions/upload-artifact uses @v5" in f.detail for f in report.findings)


def test_checker_handles_missing_workflow_directory_gracefully(tmp_path: Path) -> None:
    report = CHECKER.collect_report(tmp_path)

    assert report.exit_code == 2
    assert report.checks["workflow_files_present"] is False
    assert any("workflow directory missing" in error for error in report.errors)


def test_checker_does_not_modify_files(tmp_path: Path) -> None:
    workflow = _write_workflow(tmp_path, _valid_workflow())
    before = workflow.read_text(encoding="utf-8")

    report = CHECKER.collect_report(tmp_path)

    assert report.exit_code == 0
    assert workflow.read_text(encoding="utf-8") == before


def test_docs_mention_checkout_v6() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "actions/checkout@v6" in text


def test_docs_mention_setup_python_v6() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "actions/setup-python@v6" in text


def test_docs_mention_upload_artifact_v6() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "actions/upload-artifact@v6" in text


def test_docs_mention_node_24_compatibility() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "node 24" in text
    assert "ubuntu-latest" in text


def test_docs_mention_self_hosted_runner_requirement() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "self-hosted" in text.lower()
    assert "v2.327.1+" in text


def test_dev_check_includes_github_actions_version_checker() -> None:
    text = (REPO_ROOT / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

    assert "check_github_actions_versions.py" in text


def test_ci_check_includes_github_actions_version_checker() -> None:
    text = (REPO_ROOT / "scripts" / "ci_check.sh").read_text(encoding="utf-8")

    assert "check_github_actions_versions.py" in text


def test_github_ci_includes_github_actions_version_checker() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "check_github_actions_versions.py" in text


def test_ci_workflow_tests_enforce_updated_action_majors() -> None:
    text = (REPO_ROOT / "tests" / "test_ci_workflows.py").read_text(encoding="utf-8")

    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert "actions/upload-artifact@v6" in text


def test_release_check_script_tests_enforce_checker_integration() -> None:
    text = (REPO_ROOT / "tests" / "test_release_check_scripts.py").read_text(
        encoding="utf-8"
    )

    assert "check_github_actions_versions.py" in text
