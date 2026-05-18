"""Static tests for CI workflow files and ci_check.sh."""

from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


class TestCiWorkflow:
    @pytest.fixture
    def ci_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "ci.yml"
        assert path.exists(), "ci.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, ci_content: str) -> None:
        assert ci_content

    def test_uses_python_311(self, ci_content: str) -> None:
        assert "3.11" in ci_content

    def test_triggers_push_to_main(self, ci_content: str) -> None:
        assert "branches: [main]" in ci_content or "branches: [main]" in ci_content.replace(" ", "")

    def test_triggers_pull_request_to_main(self, ci_content: str) -> None:
        assert "pull_request:" in ci_content

    def test_triggers_workflow_dispatch(self, ci_content: str) -> None:
        assert "workflow_dispatch:" in ci_content

    def test_includes_version_consistency(self, ci_content: str) -> None:
        assert "check_version_consistency.py" in ci_content

    def test_includes_forbidden_claims(self, ci_content: str) -> None:
        assert "check_forbidden_claims.py" in ci_content

    def test_includes_pytest(self, ci_content: str) -> None:
        assert "pytest -q" in ci_content

    def test_includes_pip_check(self, ci_content: str) -> None:
        assert "pip check" in ci_content

    def test_includes_paper_demo(self, ci_content: str) -> None:
        assert "demo_paper_workflow.sh" in ci_content

    def test_includes_research_demo(self, ci_content: str) -> None:
        assert "demo_research_workflow.sh" in ci_content

    def test_includes_git_diff_check(self, ci_content: str) -> None:
        assert "git diff --check" in ci_content

    def test_includes_protected_staged_check(self, ci_content: str) -> None:
        assert "check_no_protected_staged.py" in ci_content

    def test_does_not_require_secrets(self, ci_content: str) -> None:
        assert "secrets." not in ci_content.lower()

    def test_does_not_mention_env_atlas(self, ci_content: str) -> None:
        assert ".env.atlas" not in ci_content

    def test_does_not_run_git_add_dot(self, ci_content: str) -> None:
        assert "git add ." not in ci_content

    def test_does_not_run_live_trading(self, ci_content: str) -> None:
        assert "live" not in ci_content.lower() or "mode: paper" in ci_content.lower()

    def test_no_cached_diff(self, ci_content: str) -> None:
        assert "git diff --cached --check" not in ci_content


class TestResearchCiWorkflow:
    @pytest.fixture
    def research_ci_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "research-ci.yml"
        assert path.exists(), "research-ci.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, research_ci_content: str) -> None:
        assert research_ci_content

    def test_uses_python_311(self, research_ci_content: str) -> None:
        assert "3.11" in research_ci_content

    def test_triggers_push_to_main(self, research_ci_content: str) -> None:
        assert "branches: [main]" in research_ci_content or "branches: [main]" in research_ci_content.replace(" ", "")

    def test_triggers_pull_request_to_main(self, research_ci_content: str) -> None:
        assert "pull_request:" in research_ci_content

    def test_triggers_workflow_dispatch(self, research_ci_content: str) -> None:
        assert "workflow_dispatch:" in research_ci_content

    def test_has_path_filters(self, research_ci_content: str) -> None:
        assert "paths:" in research_ci_content
        assert "src/atlas_agent/research/" in research_ci_content

    def test_runs_research_check(self, research_ci_content: str) -> None:
        assert "release_check.sh --research" in research_ci_content

    def test_does_not_require_secrets(self, research_ci_content: str) -> None:
        assert "secrets." not in research_ci_content.lower()

    def test_does_not_mention_env_atlas(self, research_ci_content: str) -> None:
        assert ".env.atlas" not in research_ci_content

    def test_does_not_run_git_add_dot(self, research_ci_content: str) -> None:
        assert "git add ." not in research_ci_content


class TestCiCheckScript:
    @pytest.fixture
    def ci_check_content(self) -> str:
        path = _repo_root() / "scripts" / "ci_check.sh"
        assert path.exists(), "ci_check.sh must exist"
        assert path.stat().st_mode & 0o111, "ci_check.sh should be executable"
        return path.read_text(encoding="utf-8")

    def test_exists_and_executable(self, ci_check_content: str) -> None:
        assert ci_check_content

    def test_uses_set_euo_pipefail(self, ci_check_content: str) -> None:
        assert "set -euo pipefail" in ci_check_content

    def test_includes_version_consistency(self, ci_check_content: str) -> None:
        assert "check_version_consistency.py" in ci_check_content

    def test_includes_forbidden_claims(self, ci_check_content: str) -> None:
        assert "check_forbidden_claims.py" in ci_check_content

    def test_includes_pytest(self, ci_check_content: str) -> None:
        assert "pytest -q" in ci_check_content

    def test_includes_pip_check(self, ci_check_content: str) -> None:
        assert "pip check" in ci_check_content

    def test_includes_paper_demo(self, ci_check_content: str) -> None:
        assert "demo_paper_workflow.sh" in ci_check_content

    def test_includes_research_demo(self, ci_check_content: str) -> None:
        assert "demo_research_workflow.sh" in ci_check_content

    def test_includes_git_diff_check(self, ci_check_content: str) -> None:
        assert "git diff --check" in ci_check_content

    def test_includes_protected_staged_check(self, ci_check_content: str) -> None:
        assert "check_no_protected_staged.py" in ci_check_content

    def test_does_not_include_cached_diff(self, ci_check_content: str) -> None:
        assert "git diff --cached --check" not in ci_check_content

    def test_no_git_add_dot(self, ci_check_content: str) -> None:
        assert "git add ." not in ci_check_content

    def test_no_git_mutations(self, ci_check_content: str) -> None:
        forbidden = [
            "git commit",
            "git push",
            "git checkout",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
        ]
        for pattern in forbidden:
            assert pattern not in ci_check_content, f"ci_check.sh contains forbidden pattern: {pattern}"
