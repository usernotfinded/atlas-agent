"""Tests for generated artifact hygiene checks and policy docs."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_generated_artifacts.py"
DOC = REPO_ROOT / "docs" / "development" / "generated-artifacts.md"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_generated_artifacts_for_tests",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _runner(
    *,
    status: str = "",
    tracked: str = "",
    staged: str = "",
):
    outputs = {
        ("status", "--porcelain=v1"): status,
        ("ls-files",): tracked,
        ("diff", "--cached", "--name-only"): staged,
    }

    def fake_runner(repo_root: Path, args: list[str]):
        return CHECKER.GitResult(0, outputs.get(tuple(args), ""), "")

    return fake_runner


def test_checker_text_mode_passes_on_clean_fixture(tmp_path: Path, capsys) -> None:
    exit_code = CHECKER.main([str(tmp_path)], git_runner=_runner())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Generated artifact hygiene check PASSED" in captured.out
    assert "Blocking findings: 0" in captured.out


def test_checker_json_mode_returns_expected_artifact_type(tmp_path: Path, capsys) -> None:
    exit_code = CHECKER.main(["--json", str(tmp_path)], git_runner=_runner())

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["artifact_type"] == "atlas_generated_artifact_hygiene_report"
    assert payload["valid"] is True


def test_checker_flags_staged_local_evidence_artifacts(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        tmp_path,
        git_runner=_runner(staged="artifacts/release_evidence/evidence.json\n"),
    )

    assert report.exit_code == 1
    assert report.checks["no_staged_local_evidence_artifacts"] is False
    assert any(f.code == "staged_local_evidence_artifact" for f in report.findings)


def test_checker_flags_tracked_local_evidence_artifacts(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        tmp_path,
        git_runner=_runner(tracked="artifacts/provider_audit_pack/manifest.json\n"),
    )

    assert report.exit_code == 1
    assert report.checks["no_tracked_local_evidence_artifacts"] is False
    assert any(f.code == "tracked_local_evidence_artifact" for f in report.findings)


def test_checker_flags_staged_secret_like_filenames(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        tmp_path,
        git_runner=_runner(staged="local/ATLAS_TOKEN\n"),
    )

    assert report.exit_code == 1
    assert report.checks["no_staged_secret_like_files"] is False
    assert any(f.code == "staged_secret_like_file" for f in report.findings)


def test_checker_flags_tracked_secret_like_filenames(tmp_path: Path) -> None:
    report = CHECKER.collect_report(
        tmp_path,
        git_runner=_runner(tracked="local/ATLAS_PASSWORD\n"),
    )

    assert report.exit_code == 1
    assert report.checks["no_tracked_secret_like_files"] is False
    assert any(f.code == "tracked_secret_like_file" for f in report.findings)


def test_checker_does_not_print_fake_secret_values(tmp_path: Path, capsys) -> None:
    fake_value = "sk-" + ("a" * 24)
    path = f"local/ATLAS_TOKEN_{fake_value}"

    exit_code = CHECKER.main([str(tmp_path)], git_runner=_runner(staged=f"{path}\n"))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert fake_value not in captured.out
    assert "[REDACTED]" in captured.out


def test_checker_handles_missing_git_gracefully(tmp_path: Path, capsys) -> None:
    def missing_git(repo_root: Path, args: list[str]):
        raise FileNotFoundError("git")

    exit_code = CHECKER.main([str(tmp_path)], git_runner=missing_git)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Generated artifact hygiene check ERROR" in captured.out
    assert "git unavailable" in captured.out


def test_checker_does_not_modify_files(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "artifacts" / "release_evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "evidence.json"
    evidence.write_text('{"status": "local"}\n', encoding="utf-8")
    before = evidence.read_text(encoding="utf-8")

    report = CHECKER.collect_report(
        tmp_path,
        git_runner=_runner(status="?? artifacts/release_evidence/evidence.json\n"),
    )

    assert report.exit_code == 0
    assert evidence.read_text(encoding="utf-8") == before
    assert any(w.code == "untracked_local_evidence_artifact" for w in report.warnings)


def test_docs_mention_generated_artifacts_are_usually_local_evidence() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "artifacts/ outputs are usually local evidence" in text
    assert "local-only evidence outputs" in text


def test_docs_discourage_committing_generated_artifacts_unless_requested() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "do not commit local generated evidence unless explicitly requested" in text
    assert "versioned evidence pack" in text


def test_docs_discourage_destructive_git_cleanup() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "do not use git reset --hard" in text
    assert "do not use git clean" in text
    assert "do not use stash pop" in text
    assert "do not use stash drop" in text
    assert "do not use stash clear" in text


def test_dev_check_includes_generated_artifact_checker() -> None:
    text = (REPO_ROOT / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

    assert "check_generated_artifacts.py" in text


def test_ci_check_includes_generated_artifact_checker() -> None:
    text = (REPO_ROOT / "scripts" / "ci_check.sh").read_text(encoding="utf-8")

    assert "check_generated_artifacts.py" in text


def test_github_ci_includes_generated_artifact_checker() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "check_generated_artifacts.py" in text


def test_cleanup_guidance_prints_exact_mv_commands(tmp_path: Path, capsys) -> None:
    repo = tmp_path
    (repo / "artifacts" / "release_evidence").mkdir(parents=True)
    (repo / "artifacts" / "release_evidence" / "evidence.json").write_text(
        '{"status": "local"}\n', encoding="utf-8"
    )

    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(status="?? artifacts/release_evidence/evidence.json\n"),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Safe cleanup guidance" in captured.out
    assert "mv artifacts/release_evidence/evidence.json" in captured.out
    assert "mkdir -p /tmp/atlas-agent-artifact-backup" in captured.out
    # The guidance explicitly warns against git clean / reset --hard, so those
    # phrases appear in the output as disallowed commands, not as suggested ones.
    assert "Do not use git clean" in captured.out
    assert "git reset --hard" in captured.out


def test_cleanup_guidance_does_not_suggest_git_clean(tmp_path: Path, capsys) -> None:
    repo = tmp_path
    (repo / "artifacts" / "release_assurance").mkdir(parents=True)
    (repo / "artifacts" / "release_assurance" / "report.md").write_text(
        "# report\n", encoding="utf-8"
    )

    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(
            status="?? artifacts/release_assurance/report.md\n"
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Do not use git clean" in captured.out
    assert "git reset --hard" in captured.out
    assert "stash pop" in captured.out
    assert "stash drop" in captured.out


def test_cleanup_guidance_does_not_touch_source_or_test_paths(
    tmp_path: Path, capsys
) -> None:
    """Even if untracked source paths appear, cleanup guidance is not emitted for them."""
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "src" / "new_file.py").write_text("pass\n", encoding="utf-8")

    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(status="?? src/new_file.py\n"),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Safe cleanup guidance" not in captured.out
    assert "mv src/new_file.py" not in captured.out
    assert "/tmp/atlas-agent-artifact-backup" not in captured.out


def test_cleanup_guidance_only_for_local_artifact_prefixes(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path
    (repo / "artifacts" / "provider_preflight").mkdir(parents=True)
    (repo / "artifacts" / "provider_preflight" / "result.json").write_text(
        "{}\n", encoding="utf-8"
    )

    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(
            status="?? artifacts/provider_preflight/result.json\n"
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "mv artifacts/provider_preflight/result.json" in captured.out
    # The guidance explicitly warns against git clean as a disallowed command.
    assert "Do not use git clean" in captured.out


def test_release_assurance_artifacts_recognized_as_local_evidence(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path
    (repo / "artifacts" / "release_assurance" / "v0.6.3-local-check").mkdir(parents=True)
    (repo / "artifacts" / "release_assurance" / "v0.6.3-local-check" / "release-assurance-summary.json").write_text(
        "{}\n", encoding="utf-8"
    )
    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(
            status="?? artifacts/release_assurance/v0.6.3-local-check/release-assurance-summary.json\n"
        ),
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "untracked local-only generated evidence artifact" in captured.out
    assert "artifacts/release_assurance/" in captured.out


def test_release_assurance_tracked_versioned_evidence_allowed(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path
    (
        repo / "artifacts" / "release_assurance" / "archive" / "v0.5.9-local-check"
    ).mkdir(parents=True)
    (
        repo
        / "artifacts"
        / "release_assurance"
        / "archive"
        / "v0.5.9-local-check"
        / "release-assurance-summary.json"
    ).write_text("{}\n", encoding="utf-8")
    exit_code = CHECKER.main(
        [str(repo)],
        git_runner=_runner(
            tracked="artifacts/release_assurance/archive/v0.5.9-local-check/release-assurance-summary.json\n",
            status="",
        ),
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "tracked local-only generated evidence artifact" not in captured.out
