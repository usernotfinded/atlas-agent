"""Static tests for CI workflow files and ci_check.sh."""

from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _workflow_files() -> list[Path]:
    workflow_dir = _repo_root() / ".github" / "workflows"
    return sorted(
        [
            *workflow_dir.glob("*.yml"),
            *workflow_dir.glob("*.yaml"),
        ]
    )


class TestWorkflowActionVersions:
    def test_all_workflows_use_checkout_v6(self) -> None:
        for path in _workflow_files():
            text = path.read_text(encoding="utf-8")
            assert "actions/checkout@v4" not in text
            assert "actions/checkout@v5" not in text
            if "actions/checkout@" in text:
                assert "actions/checkout@v6" in text

    def test_all_workflows_use_setup_python_v6(self) -> None:
        for path in _workflow_files():
            text = path.read_text(encoding="utf-8")
            assert "actions/setup-python@v5" not in text
            if "actions/setup-python@" in text:
                assert "actions/setup-python@v6" in text

    def test_all_workflows_use_upload_artifact_v6(self) -> None:
        for path in _workflow_files():
            text = path.read_text(encoding="utf-8")
            assert "actions/upload-artifact@v4" not in text
            assert "actions/upload-artifact@v5" not in text
            if "actions/upload-artifact@" in text:
                assert "actions/upload-artifact@v6" in text


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

    def test_includes_release_metadata(self, ci_content: str) -> None:
        assert "check_release_metadata.py" in ci_content


    def test_includes_version_consistency(self, ci_content: str) -> None:
        assert "check_version_consistency.py" in ci_content

    def test_includes_forbidden_claims(self, ci_content: str) -> None:
        assert "check_forbidden_claims.py" in ci_content

    def test_includes_public_docs_consistency(self, ci_content: str) -> None:
        assert "check_public_docs_consistency.py" in ci_content

    def test_includes_trust_center_check(self, ci_content: str) -> None:
        assert "check_trust_center.py" in ci_content

    def test_includes_onboarding_docs_check(self, ci_content: str) -> None:
        assert "check_onboarding_docs.py" in ci_content

    def test_includes_generated_artifact_check(self, ci_content: str) -> None:
        assert "check_generated_artifacts.py" in ci_content

    def test_includes_github_actions_version_check(self, ci_content: str) -> None:
        assert "check_github_actions_versions.py" in ci_content

    def test_includes_generated_artifact_tests(self, ci_content: str) -> None:
        assert "tests/test_generated_artifacts.py" in ci_content

    def test_includes_github_actions_version_tests(self, ci_content: str) -> None:
        assert "tests/test_github_actions_versions.py" in ci_content

    def test_includes_onboarding_docs_tests(self, ci_content: str) -> None:
        assert "tests/test_onboarding_docs.py" in ci_content

    def test_includes_readme_quickstart(self, ci_content: str) -> None:
        assert "verify_readme_quickstart.py" in ci_content

    def test_includes_rc_cutover(self, ci_content: str) -> None:
        assert "check_rc1_cutover.py" in ci_content

    def test_includes_clean_install(self, ci_content: str) -> None:
        assert "check_clean_install.py" in ci_content

    def test_includes_package_distribution(self, ci_content: str) -> None:
        assert "check_package_distribution.py" in ci_content

    def test_includes_public_launch_readiness(self, ci_content: str) -> None:
        assert "check_public_launch_readiness.py" in ci_content

    def test_includes_reviewer_onboarding(self, ci_content: str) -> None:
        assert "check_reviewer_onboarding.py" in ci_content

    def test_includes_public_launch_messaging(self, ci_content: str) -> None:
        assert "check_public_launch_messaging.py" in ci_content

    def test_includes_final_rc_audit(self, ci_content: str) -> None:
        assert "check_final_rc_audit.py" in ci_content

    def test_includes_stable_release_decision(self, ci_content: str) -> None:
        assert "check_stable_release_decision.py" in ci_content

    def test_includes_v060_post_release_readiness(self, ci_content: str) -> None:
        assert "check_v060_readiness.py --post-release" in ci_content

    def test_post_release_readiness_does_not_use_broad_or_true(self, ci_content: str) -> None:
        # The post-release step must not silence errors with || true
        lines = ci_content.splitlines()
        for i, line in enumerate(lines):
            if "check_v060_readiness.py --post-release" in line:
                # Check the same line and next line for broad || true
                window = "\n".join(lines[i : i + 2])
                assert "|| true" not in window, "post-release check must not use || true"
                break
        else:
            pytest.fail("v0.6 post-release readiness step not found")

    def test_includes_hotfix_cutover_gate(self, ci_content: str) -> None:
        assert "check_v0581_hotfix_cutover.py" in ci_content

    def test_obsolete_rc5_cutover_not_direct_ci_gate(self, ci_content: str) -> None:
        assert "python3.11 scripts/check_v058_rc5_cutover.py" not in ci_content

    def test_includes_release_check_quick(self, ci_content: str) -> None:
        assert "release_check.sh --quick" in ci_content

    def test_includes_pip_check(self, ci_content: str) -> None:
        assert "pip check" in ci_content

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
        ci_lower = ci_content.lower()
        # Reject explicit live-trading mode references, not innocent substrings
        # like filenames containing "live" (e.g. test_live_submit_safety_contract_docs.py)
        forbidden = ["mode: live", "atlas_mode=live", "--mode live", "run --live"]
        assert not any(f in ci_lower for f in forbidden)

    def test_no_cached_diff(self, ci_content: str) -> None:
        assert "git diff --cached --check" not in ci_content

    def test_no_publish_or_upload(self, ci_content: str) -> None:
        assert "twine upload" not in ci_content.lower()
        assert "gh release create" not in ci_content.lower()
        assert "git push" not in ci_content
        assert "git tag" not in ci_content

    def test_has_timeout(self, ci_content: str) -> None:
        assert "timeout-minutes:" in ci_content

    def test_checkout_uses_fetch_depth_zero(self, ci_content: str) -> None:
        assert "fetch-depth: 0" in ci_content

    def test_checkout_uses_fetch_tags_true(self, ci_content: str) -> None:
        assert "fetch-tags: true" in ci_content

    def test_has_explicit_tag_fetch_step(self, ci_content: str) -> None:
        assert "git fetch --force --tags origin" in ci_content

    def test_core_functional_fetches_tags(self, ci_content: str) -> None:
        # The core-functional job must also fetch tags so that tag-dependent
        # tests (e.g. v0.6.0 post-release readiness) have the tag available.
        assert ci_content.count("git fetch --force --tags origin") >= 2

    def test_clean_install_uses_allow_network(self, ci_content: str) -> None:
        assert "check_clean_install.py --allow-network" in ci_content


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


class TestReleaseGateWorkflow:
    @pytest.fixture
    def release_gate_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "release-gate.yml"
        assert path.exists(), "release-gate.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, release_gate_content: str) -> None:
        assert release_gate_content

    def test_uses_python_311(self, release_gate_content: str) -> None:
        assert "3.11" in release_gate_content

    def test_triggers_workflow_dispatch(self, release_gate_content: str) -> None:
        assert "workflow_dispatch:" in release_gate_content

    def test_triggers_on_tags(self, release_gate_content: str) -> None:
        assert "tags:" in release_gate_content

    def test_includes_release_check_quick(self, release_gate_content: str) -> None:
        assert "release_check.sh --quick" in release_gate_content

    def test_includes_release_check_research(self, release_gate_content: str) -> None:
        assert "release_check.sh --research" in release_gate_content

    def test_includes_release_check_full(self, release_gate_content: str) -> None:
        assert "release_check.sh --full" in release_gate_content

    def test_includes_clean_install(self, release_gate_content: str) -> None:
        assert "check_clean_install.py" in release_gate_content

    def test_includes_package_distribution(self, release_gate_content: str) -> None:
        assert "check_package_distribution.py" in release_gate_content

    def test_does_not_require_secrets(self, release_gate_content: str) -> None:
        assert "secrets." not in release_gate_content.lower()

    def test_does_not_publish(self, release_gate_content: str) -> None:
        assert "twine upload" not in release_gate_content.lower()
        assert "gh release create" not in release_gate_content.lower()
        assert "git push" not in release_gate_content
        assert "git tag" not in release_gate_content

    def test_has_timeout(self, release_gate_content: str) -> None:
        assert "timeout-minutes:" in release_gate_content

    def test_checkout_uses_fetch_depth_zero(self, release_gate_content: str) -> None:
        assert "fetch-depth: 0" in release_gate_content

    def test_checkout_uses_fetch_tags_true(self, release_gate_content: str) -> None:
        assert "fetch-tags: true" in release_gate_content

    def test_has_explicit_tag_fetch_step(self, release_gate_content: str) -> None:
        assert "git fetch --force --tags origin" in release_gate_content

    def test_clean_install_uses_allow_network(self, release_gate_content: str) -> None:
        assert "check_clean_install.py --allow-network" in release_gate_content


class TestFullTestWorkflow:
    @pytest.fixture
    def full_test_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "full-test.yml"
        assert path.exists(), "full-test.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, full_test_content: str) -> None:
        assert full_test_content

    def test_uses_python_311(self, full_test_content: str) -> None:
        assert "3.11" in full_test_content

    def test_is_label_gated_for_pull_requests(self, full_test_content: str) -> None:
        assert "full-ci" in full_test_content
        assert "contains(github.event.pull_request.labels.*.name, 'full-ci')" in full_test_content

    def test_runs_full_pytest(self, full_test_content: str) -> None:
        assert "python3.11 -m pytest tests/ -q -n auto" in full_test_content

    def test_does_not_require_secrets(self, full_test_content: str) -> None:
        assert "secrets." not in full_test_content.lower()

    def test_does_not_publish_or_create_release(self, full_test_content: str) -> None:
        content = full_test_content.lower()
        assert "twine upload" not in content
        assert "gh release create" not in content
        assert "git push" not in full_test_content
        assert "git tag" not in full_test_content


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

    def test_includes_release_metadata(self, ci_check_content: str) -> None:
        assert "check_release_metadata.py" in ci_check_content


    def test_includes_version_consistency(self, ci_check_content: str) -> None:
        assert "check_version_consistency.py" in ci_check_content

    def test_includes_forbidden_claims(self, ci_check_content: str) -> None:
        assert "check_forbidden_claims.py" in ci_check_content

    def test_includes_public_docs_consistency(self, ci_check_content: str) -> None:
        assert "check_public_docs_consistency.py" in ci_check_content

    def test_includes_trust_center_check(self, ci_check_content: str) -> None:
        assert "check_trust_center.py" in ci_check_content

    def test_includes_onboarding_docs_check(self, ci_check_content: str) -> None:
        assert "check_onboarding_docs.py" in ci_check_content

    def test_includes_generated_artifact_check(self, ci_check_content: str) -> None:
        assert "check_generated_artifacts.py" in ci_check_content

    def test_includes_github_actions_version_check(self, ci_check_content: str) -> None:
        assert "check_github_actions_versions.py" in ci_check_content

    def test_includes_generated_artifact_tests(self, ci_check_content: str) -> None:
        assert "tests/test_generated_artifacts.py" in ci_check_content

    def test_includes_github_actions_version_tests(self, ci_check_content: str) -> None:
        assert "tests/test_github_actions_versions.py" in ci_check_content

    def test_includes_trust_center_tests(self, ci_check_content: str) -> None:
        assert "tests/test_trust_center.py" in ci_check_content

    def test_includes_onboarding_docs_tests(self, ci_check_content: str) -> None:
        assert "tests/test_onboarding_docs.py" in ci_check_content

    def test_includes_readme_quickstart(self, ci_check_content: str) -> None:
        assert "verify_readme_quickstart.py" in ci_check_content

    def test_includes_rc_cutover(self, ci_check_content: str) -> None:
        assert "check_rc1_cutover.py" in ci_check_content

    def test_includes_clean_install(self, ci_check_content: str) -> None:
        assert "check_clean_install.py" in ci_check_content

    def test_includes_package_distribution(self, ci_check_content: str) -> None:
        assert "check_package_distribution.py" in ci_check_content

    def test_includes_public_launch_readiness(self, ci_check_content: str) -> None:
        assert "check_public_launch_readiness.py" in ci_check_content

    def test_includes_reviewer_onboarding(self, ci_check_content: str) -> None:
        assert "check_reviewer_onboarding.py" in ci_check_content

    def test_includes_public_launch_messaging(self, ci_check_content: str) -> None:
        assert "check_public_launch_messaging.py" in ci_check_content

    def test_includes_final_rc_audit(self, ci_check_content: str) -> None:
        assert "check_final_rc_audit.py" in ci_check_content

    def test_includes_stable_release_decision(self, ci_check_content: str) -> None:
        assert "check_stable_release_decision.py" in ci_check_content

    def test_includes_pip_check(self, ci_check_content: str) -> None:
        assert "pip check" in ci_check_content

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

class TestProviderAuditPackWorkflow:
    @pytest.fixture
    def audit_pack_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "provider-audit-pack.yml"
        assert path.exists(), "provider-audit-pack.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, audit_pack_content: str) -> None:
        assert audit_pack_content

    def test_triggers_workflow_dispatch_only(self, audit_pack_content: str) -> None:
        assert "workflow_dispatch:" in audit_pack_content
        assert "push:" not in audit_pack_content
        assert "pull_request:" not in audit_pack_content
        assert "schedule:" not in audit_pack_content

    def test_permissions_read_only(self, audit_pack_content: str) -> None:
        assert "permissions:" in audit_pack_content
        assert "contents: read" in audit_pack_content

    def test_does_not_reference_secrets(self, audit_pack_content: str) -> None:
        assert "secrets." not in audit_pack_content.lower()

    def test_does_not_reference_provider_api_keys(self, audit_pack_content: str) -> None:
        content = audit_pack_content.upper()
        assert "API_KEY" not in content
        assert "TOKEN" not in content
        assert "PASSWORD" not in content

    def test_does_not_publish_or_release(self, audit_pack_content: str) -> None:
        content = audit_pack_content.lower()
        assert "twine upload" not in content
        assert "gh release create" not in content
        assert "git push" not in content
        assert "git tag" not in content

    def test_runs_providers_audit_pack(self, audit_pack_content: str) -> None:
        assert "providers audit-pack" in audit_pack_content

    def test_runs_providers_verify_audit_pack(self, audit_pack_content: str) -> None:
        assert "providers verify-audit-pack" in audit_pack_content

    def test_uploads_artifact(self, audit_pack_content: str) -> None:
        assert "actions/upload-artifact" in audit_pack_content
        assert "path: artifacts/provider_audit_pack/ci-smoke" in audit_pack_content

    def test_disables_live_trading(self, audit_pack_content: str) -> None:
        assert "TRADING_MODE: paper" in audit_pack_content
        assert "ENABLE_LIVE_TRADING: \"false\"" in audit_pack_content
        assert "PROVIDER_EXECUTION_ENABLED: \"false\"" in audit_pack_content

class TestReleaseAssuranceWorkflow:
    @pytest.fixture
    def release_assurance_content(self) -> str:
        path = _repo_root() / ".github" / "workflows" / "release-assurance.yml"
        assert path.exists(), "release-assurance.yml must exist"
        return path.read_text(encoding="utf-8")

    def test_exists(self, release_assurance_content: str) -> None:
        assert release_assurance_content

    def test_triggers_workflow_dispatch_only(self, release_assurance_content: str) -> None:
        assert "workflow_dispatch:" in release_assurance_content
        assert "push:" not in release_assurance_content
        assert "pull_request:" not in release_assurance_content
        assert "schedule:" not in release_assurance_content

    def test_permissions_read_only(self, release_assurance_content: str) -> None:
        assert "permissions:" in release_assurance_content
        assert "contents: read" in release_assurance_content

    def test_does_not_reference_secrets(self, release_assurance_content: str) -> None:
        assert "secrets." not in release_assurance_content.lower()

    def test_does_not_publish_or_release(self, release_assurance_content: str) -> None:
        content = release_assurance_content.lower()
        assert "twine upload" not in content
        assert "gh release create" not in content
        assert "git push" not in content
        assert "git tag" not in content

    def test_runs_release_metadata(self, release_assurance_content: str) -> None:
        assert "scripts/check_release_metadata.py" in release_assurance_content


    def test_runs_version_consistency(self, release_assurance_content: str) -> None:
        assert "scripts/check_version_consistency.py" in release_assurance_content

    def test_runs_forbidden_claims(self, release_assurance_content: str) -> None:
        assert "scripts/check_forbidden_claims.py" in release_assurance_content

    def test_runs_release_check_quick(self, release_assurance_content: str) -> None:
        assert "release_check.sh --quick" in release_assurance_content

    def test_runs_release_assurance(self, release_assurance_content: str) -> None:
        assert "scripts/release_assurance.py" in release_assurance_content

    def test_uploads_artifact(self, release_assurance_content: str) -> None:
        assert "actions/upload-artifact" in release_assurance_content
        assert "release-assurance-" in release_assurance_content

    def test_fetches_tags(self, release_assurance_content: str) -> None:
        assert "fetch-tags: true" in release_assurance_content

    def test_disables_trading(self, release_assurance_content: str) -> None:
        assert "ENABLE_LIVE_TRADING: \"false\"" in release_assurance_content
        assert "PROVIDER_EXECUTION_ENABLED: \"false\"" in release_assurance_content
        assert "BROKER_EXECUTION_ENABLED: \"false\"" in release_assurance_content


class TestDeterministicOrdering:
    """Regression tests for CI nondeterminism fixes (CAND-006)."""

    def test_provider_execution_readiness_report_uses_sorted_set(self) -> None:
        """The doctor function must use sorted(set(...)) not list(set(...))
        so JSON output is deterministic across runs."""
        path = _repo_root() / "src" / "atlas_agent" / "research" / "provider_execution_readiness_report.py"
        text = path.read_text(encoding="utf-8")
        assert "sorted(set(invalid_artifacts))" in text, (
            "provider_execution_readiness_report.py must use sorted(set(...)) for deterministic output"
        )
        assert "sorted(set(orphan_artifacts))" in text, (
            "provider_execution_readiness_report.py must use sorted(set(...)) for deterministic output"
        )
        assert "list(set(invalid_artifacts))" not in text, (
            "provider_execution_readiness_report.py must not use list(set(...)) which is nondeterministic"
        )
        assert "list(set(orphan_artifacts))" not in text, (
            "provider_execution_readiness_report.py must not use list(set(...)) which is nondeterministic"
        )

    def test_discipline_profile_uses_sorted_parametrize(self) -> None:
        """pytest-xdist collection mismatch is avoided by sorting parametrized values."""
        path = _repo_root() / "tests" / "test_discipline_profile.py"
        text = path.read_text(encoding="utf-8")
        assert "sorted(_FORBIDDEN_PATTERNS)" in text, (
            "test_discipline_profile.py must use sorted(_FORBIDDEN_PATTERNS) for deterministic collection"
        )

    def test_no_list_set_in_source(self) -> None:
        """list(set(...)) is a known nondeterministic pattern in Python; prefer sorted(set(...))."""
        src_dir = _repo_root() / "src" / "atlas_agent"
        violations: list[str] = []
        for path in src_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "list(set(" in text:
                violations.append(str(path.relative_to(_repo_root())))
        assert not violations, (
            f"Found list(set(...)) in source files (nondeterministic): {violations}"
        )
