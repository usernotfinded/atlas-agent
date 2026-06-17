"""Tests for the direct-main health report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "main_health.py"
GENERATED_ARTIFACT_CHECKER = REPO_ROOT / "scripts" / "check_generated_artifacts.py"
DOC = REPO_ROOT / "docs" / "development" / "main-health.md"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("main_health_for_tests", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    _write(tmp_path / "pyproject.toml", '[project]\nversion = "0.6.12"\n')
    _write(
        tmp_path / "src" / "atlas_agent" / "__init__.py",
        '__version__ = "0.6.12"\n',
    )
    _write(tmp_path / "scripts" / "check_trust_center.py", "# fixture\n")
    _write(tmp_path / "scripts" / "check_onboarding_docs.py", "# fixture\n")
    _write(
        tmp_path / "scripts" / "check_generated_artifacts.py",
        GENERATED_ARTIFACT_CHECKER.read_text(encoding="utf-8"),
    )
    _write(
        tmp_path / "docs" / "releases" / "release-metadata.json",
        (REPO_ROOT / "docs" / "releases" / "release-metadata.json").read_text(encoding="utf-8"),
    )
    return tmp_path


def _runner(
    *,
    branch: str = "main",
    head: str = "abc123",
    origin: str = "abc123",
    status: str = "",
    staged: str = "",
    tracked: str = "",
    tag: str = "",
    future_tag: str = "",
):
    def fake_runner(repo_root: Path, args: list[str]):
        key = tuple(args)
        if key == ("rev-parse", "--show-toplevel"):
            return CHECKER.CommandResult(0, str(repo_root.resolve()) + "\n", "")
        if key == ("branch", "--show-current"):
            return CHECKER.CommandResult(0, branch + "\n", "")
        if key == ("rev-parse", "HEAD"):
            return CHECKER.CommandResult(0, head + "\n", "")
        if key == ("rev-parse", "--verify", "origin/main^{commit}"):
            if origin:
                return CHECKER.CommandResult(0, origin + "\n", "")
            return CHECKER.CommandResult(1, "", "unknown revision\n")
        if key == ("status", "--porcelain=v1"):
            return CHECKER.CommandResult(0, status, "")
        if key == ("diff", "--cached", "--name-only"):
            return CHECKER.CommandResult(0, staged, "")
        if key == ("ls-files",):
            return CHECKER.CommandResult(0, tracked, "")
        if key == ("tag", "--list", "v0.6.1"):
            return CHECKER.CommandResult(0, tag, "")
        if key == ("tag", "--list", "v0.6.3"):
            return CHECKER.CommandResult(0, "v0.6.3\n", "")
        if key == ("tag", "--list", "v0.6.5"):
            return CHECKER.CommandResult(0, tag, "")
        if key == ("tag", "--list", "v0.6.8"):
            return CHECKER.CommandResult(0, "v0.6.8\n", "")
        if key == ("tag", "--list", "v0.6.9"):
            return CHECKER.CommandResult(0, "v0.6.9\n", "")
        if key == ("tag", "--list", "v0.6.10"):
            return CHECKER.CommandResult(0, "v0.6.10\n", "")
        if key == ("tag", "--list", "v0.6.11"):
            return CHECKER.CommandResult(0, "v0.6.11\n", "")
        if key == ("tag", "--list", "v0.6.12"):
            return CHECKER.CommandResult(0, "v0.6.12\n" if not tag else tag, "")
        if key == ("tag", "--list", "v0.6.13"):
            return CHECKER.CommandResult(0, future_tag, "")
        if key == (
            "diff",
            "--name-status",
            "--",
            "src/atlas_agent/config",
            "src/atlas_agent/brokers",
            "src/atlas_agent/execution",
            "src/atlas_agent/safety",
            "src/atlas_agent/risk",
        ):
            return CHECKER.CommandResult(0, "", "")
        raise AssertionError(f"unexpected git args: {args}")

    return fake_runner


def test_text_mode_runs_on_mocked_clean_main_state(tmp_path: Path, capsys) -> None:
    repo = _fixture(tmp_path)

    exit_code = CHECKER.main([str(repo)], git_runner=_runner())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Main health report PASSED" in captured.out
    assert "Source version: 0.6.12" in captured.out


def test_json_mode_returns_artifact_type(tmp_path: Path, capsys) -> None:
    repo = _fixture(tmp_path)

    exit_code = CHECKER.main(["--json", str(repo)], git_runner=_runner())

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["artifact_type"] == "atlas_main_health_report"
    assert payload["valid"] is True


def test_reports_source_version_check(tmp_path: Path) -> None:
    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=_runner())

    assert report.source_version == "0.6.12"
    assert report.checks["expected_source_version"] is True


def test_reports_public_release_v0612(tmp_path: Path) -> None:
    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=_runner())

    assert report.public_release == "v0.6.12"
    assert report.checks["public_release_expected"] is True


def test_release_metadata_validation_passes_when_consistent(tmp_path: Path) -> None:
    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=_runner())

    assert not any(f.code.startswith("release_metadata") for f in report.findings)
    assert not any(f.code == "public_release_tag_missing" for f in report.findings)
    assert not any(f.code == "next_release_tag_exists" for f in report.findings)


def test_release_metadata_drift_detected_when_source_version_mismatches(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.6.99"\n')
    (repo / "src" / "atlas_agent" / "__init__.py").write_text('__version__ = "0.6.99"\n')

    report = CHECKER.collect_report(repo, git_runner=_runner())

    assert any(f.code == "release_metadata_drift" for f in report.findings)


def test_public_release_tag_missing_detected(tmp_path: Path) -> None:
    def no_v0612_tag(repo_root: Path, args: list[str]):
        key = tuple(args)
        if key == ("tag", "--list", "v0.6.12"):
            return CHECKER.CommandResult(0, "", "")
        return _runner()(repo_root, args)

    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=no_v0612_tag)

    assert any(f.code == "public_release_tag_missing" for f in report.findings)


def test_next_release_tag_exists_detected(tmp_path: Path) -> None:
    def v0613_exists(repo_root: Path, args: list[str]):
        key = tuple(args)
        if key == ("tag", "--list", "v0.6.13"):
            return CHECKER.CommandResult(0, "v0.6.13\n", "")
        return _runner()(repo_root, args)

    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=v0613_exists)

    assert any(f.code == "next_release_tag_exists" for f in report.findings)


def test_reports_repo_root_check(tmp_path: Path) -> None:
    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=_runner())

    assert report.checks["repo_root"] is True


def test_reports_current_branch_main_check(tmp_path: Path) -> None:
    report = CHECKER.collect_report(_fixture(tmp_path), git_runner=_runner())

    assert report.checks["on_main"] is True


def test_flags_non_main_branch_using_mocked_git_output(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        _fixture(tmp_path),
        git_runner=_runner(branch="feature/test"),
    )

    assert report.exit_code == 1
    assert report.checks["on_main"] is False
    assert any(f.code == "not_on_main" for f in report.findings)


def test_flags_head_not_matching_origin_main(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        _fixture(tmp_path),
        git_runner=_runner(head="abc123", origin="def456"),
    )

    assert report.exit_code == 1
    assert report.checks["head_matches_origin_main"] is False
    assert any(f.code == "head_not_pushed" for f in report.findings)


def test_flags_dirty_worktree_using_mocked_git_status(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        _fixture(tmp_path),
        git_runner=_runner(status=" M README.md\n"),
    )

    assert report.checks["working_tree_clean"] is False
    assert any(w.code == "working_tree_dirty" for w in report.warnings)


def test_flags_staged_changes_using_mocked_git_status(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        _fixture(tmp_path),
        git_runner=_runner(status="M  README.md\n", staged="README.md\n"),
    )

    assert report.checks["no_staged_changes"] is False
    assert any(w.code == "staged_changes_present" for w in report.warnings)


def test_warns_on_untracked_generated_artifacts_without_printing_secret_values(
    tmp_path: Path,
    capsys,
) -> None:
    fake_secret = "sk-" + ("a" * 24)
    status = f"?? artifacts/release_evidence/ATLAS_TOKEN_{fake_secret}.json\n"
    repo = _fixture(tmp_path)

    exit_code = CHECKER.main([str(repo)], git_runner=_runner(status=status))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "untracked generated artifact" in captured.out
    assert fake_secret not in captured.out
    assert "[REDACTED]" in captured.out


def test_flags_accidental_future_release_tag_using_mocked_git_tag(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        _fixture(tmp_path),
        git_runner=_runner(future_tag="v0.6.13\n"),
    )

    assert report.exit_code == 1
    assert report.checks["no_unrequested_maintenance_tag"] is False
    assert any(f.code == "unrequested_maintenance_tag" for f in report.findings)


def test_handles_missing_git_gracefully(tmp_path: Path, capsys) -> None:
    repo = _fixture(tmp_path)

    def missing_git(repo_root: Path, args: list[str]):
        raise FileNotFoundError("git")

    exit_code = CHECKER.main([str(repo)], git_runner=missing_git)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Main health report ERROR" in captured.out
    assert "git unavailable" in captured.out


def test_handles_missing_gh_gracefully_in_include_github_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _fixture(tmp_path)
    monkeypatch.setattr(CHECKER.shutil, "which", lambda name: None)

    report = CHECKER.collect_report(
        repo,
        include_github=True,
        git_runner=_runner(),
    )

    assert report.exit_code == 0
    assert report.github["requested"] is True
    assert report.github["gh_available"] is False
    assert any(w.code == "github_cli_missing" for w in report.warnings)


def test_does_not_call_gh_unless_include_github_is_passed(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def gh_runner(repo_root: Path, args: list[str]):
        calls.append(args)
        return CHECKER.CommandResult(0, "", "")

    CHECKER.collect_report(
        _fixture(tmp_path),
        include_github=False,
        git_runner=_runner(),
        gh_runner=gh_runner,
    )

    assert calls == []


def test_does_not_modify_files(tmp_path: Path) -> None:
    repo = _fixture(tmp_path)
    evidence = repo / "artifacts" / "release_evidence" / "evidence.md"
    _write(evidence, "local evidence\n")
    before = evidence.read_text(encoding="utf-8")

    CHECKER.collect_report(
        repo,
        git_runner=_runner(status="?? artifacts/release_evidence/evidence.md\n"),
    )

    assert evidence.read_text(encoding="utf-8") == before


def test_docs_mention_main_source_version_can_differ_from_public_release() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "main source version can differ from public release" in text
    assert "public github release is `v0.6.12`" in text


def test_docs_discourage_destructive_git_cleanup() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "do not use git reset --hard" in text
    assert "do not use git clean" in text
    assert "do not use stash pop" in text
    assert "do not use stash drop" in text
    assert "do not use stash clear" in text


def test_docs_mention_generated_artifact_hygiene() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "generated artifact hygiene" in text
    assert "generated artifacts should remain unstaged unless explicitly requested" in text


def test_docs_mention_protected_runtime_boundary_expectation() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "protected runtime boundaries should be empty for docs/checker-only work" in text
