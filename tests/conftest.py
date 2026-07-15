# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/conftest.py
# PURPOSE: Provides shared fixtures and automatic test-tier classification.
# DEPS:    json, sys, collections.abc, pathlib, pytest, release_metadata.
# ==============================================================================

# --- IMPORTS ---

import json
import sys
from collections.abc import Callable
from pathlib import Path
import pytest

# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parent.parent

# These integration modules are intentionally retained in the full suite but
# excluded from the default local loop. Keeping the policy here lets new domain
# tests join the quick tier without editing shell-script allowlists.
SLOW_TEST_PATHS = frozenset(
    {
        "tests/research/test_research_provider_mock_response_final_safety_seal.py",
        "tests/research/test_research_provider_mock_response_trust_decision_blocker.py",
        "tests/research/test_research_provider_safety_dossier.py",
        "tests/research/test_research_sandbox_cli.py",
        "tests/test_check_safety_atomic_write.py",
        "tests/test_clean_install_check.py",
        "tests/test_cli_ux_regression.py",
        "tests/test_demo_research_workflow_script.py",
        "tests/test_package_distribution_check.py",
        "tests/test_paper_human_review_ledger.py",
        "tests/test_paper_human_review_pack.py",
        "tests/test_paper_human_review_policy.py",
        "tests/test_paper_human_review_replay.py",
        "tests/test_provider_artifact_golden_contracts.py",
        "tests/test_release_assurance_diagnostics.py",
        "tests/test_release_assurance_snapshot_integration.py",
        "tests/test_reviewer_golden_path_smoke.py",
    }
)

QUICK_TEST_DIRECTORIES = (
    "tests/agent/",
    "tests/architecture/",
    "tests/audit/",
    "tests/backtest/",
    "tests/brokers/",
    "tests/cli/",
    "tests/config/",
    "tests/dashboard/",
    "tests/e2e/",
    "tests/execution/",
    "tests/gateway/",
    "tests/learning/",
    "tests/notifications/",
    "tests/reflection/",
    "tests/reports/",
    "tests/risk/",
    "tests/safety/",
    "tests/scripts/",
    "tests/skills/",
    "tests/tools/",
    "tests/update/",
)

# Root-level legacy and research tests predate the domain-directory convention.
# This compact compatibility set preserves the former quick-gate coverage while
# new tests join automatically by living in a domain directory or using `quick`.
QUICK_TEST_PATHS = frozenset(
    {
        "tests/research/test_research_check_artifacts_cli.py",
        "tests/research/test_research_cli.py",
        "tests/research/test_research_configless_cli.py",
        "tests/research/test_research_plan_cli.py",
        "tests/research/test_research_prompt_cli.py",
        "tests/research/test_research_providers.py",
        "tests/research/test_research_schema_version.py",
        "tests/research/test_research_session.py",
        "tests/test_changelog_consistency.py",
        "tests/test_check_v0610_release_prep.py",
        "tests/test_check_v0611_planning.py",
        "tests/test_ci_workflows.py",
        "tests/test_cli_smoke.py",
        "tests/test_demo_command_smoke.py",
        "tests/test_feedback_intake.py",
        "tests/test_feedback_taxonomy.py",
        "tests/test_generated_artifacts.py",
        "tests/test_github_actions_versions.py",
        "tests/test_main_health.py",
        "tests/test_onboarding_docs.py",
        "tests/test_product_capability_inventory.py",
        "tests/test_public_docs_consistency.py",
        "tests/test_public_launch_readiness.py",
        "tests/test_readme_quickstart_verification.py",
        "tests/test_release_check_scripts.py",
        "tests/test_reviewer_outreach.py",
        "tests/test_submit_execution_safety_check.py",
        "tests/test_trust_center.py",
    }
)

HISTORICAL_TEST_PREFIXES = (
    "tests/test_v058",
    "tests/test_v060_",
    "tests/test_v061_",
    "tests/test_v062_",
    "tests/test_v063_",
    "tests/test_v064_",
    "tests/test_v065_",
    "tests/test_v066_",
)

# Make scripts/ importable for release_metadata without relying on PYTHONPATH.
_SCRIPTS_DIR = str(ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from release_metadata import load_metadata, ReleaseMetadata


# ==============================================================================
# TEST TIER POLICY
# ==============================================================================

def _is_slow_test_path(relative_path: str) -> bool:
    """Return whether a test belongs only in full CI and release gates."""
    return relative_path in SLOW_TEST_PATHS or relative_path.startswith(
        HISTORICAL_TEST_PREFIXES
    )


def _is_quick_test_path(relative_path: str) -> bool:
    """Return whether a test follows the automatic quick-tier convention."""
    return relative_path in QUICK_TEST_PATHS or relative_path.startswith(
        QUICK_TEST_DIRECTORIES
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify known integration tests without changing normal test files.

    New tests in domain directories are quick by default. A genuinely expensive
    test can opt out with ``@pytest.mark.slow``; an exceptional root-level test
    can opt in with ``@pytest.mark.quick``. Plain ``pytest`` remains the
    authoritative full suite and selects both tiers.
    """
    for item in items:
        relative_path = Path(str(item.path)).resolve().relative_to(ROOT).as_posix()
        if _is_slow_test_path(relative_path):
            item.add_marker(pytest.mark.slow)
            continue
        if item.get_closest_marker("slow") is None and _is_quick_test_path(
            relative_path
        ):
            item.add_marker(pytest.mark.quick)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def release_identity():
    """Load release identity from metadata and return current-state values.

    Returns a dict with:
      - source_version (e.g. "0.6.25")
      - current_public_release (e.g. "v0.6.25")
      - next_planned_release (e.g. "v0.6.26")
      - previous_public_release (first historical release tag, e.g. "v0.6.24")
    """
    metadata = ReleaseMetadata(
        load_metadata(ROOT / "docs" / "releases" / "release-metadata.json")
    )
    previous_public_release = None
    for release in metadata.releases:
        if release.get("status") == "historical":
            previous_public_release = release.get("tag")
            break
    return {
        "source_version": metadata.source_version,
        "current_public_release": metadata.current_public_release,
        "next_planned_release": metadata.next_planned_release,
        "previous_public_release": previous_public_release,
    }


@pytest.fixture
def write_complete_setup_config():
    def _write(workspace: Path, provider="anthropic", model="claude-opus-4-7"):
        atlas_dir = workspace / ".atlas"
        atlas_dir.mkdir(parents=True, exist_ok=True)
        config_file = atlas_dir / "config.json"
        config_data = {
            "setup_mode": "quick",
            "provider": provider,
            "model": model,
            "messaging": "cli",
            "workspace_path": str(workspace),
            "trust_mode": "paper",
            "broker_mode": "paper",
            "update_channel": "stable",
            "credentials_configured": True
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        # Also satisfy credential requirement
        env_atlas = workspace / ".env.atlas"
        env_atlas.write_text(f"ANTHROPIC_API_KEY=test-key\n", encoding="utf-8")
        return config_data
    return _write


@pytest.fixture
def mutated_copy(tmp_path: Path) -> Callable[..., Path]:
    """Create a modified temporary copy without mutating repository sources."""

    def _copy(
        source: Path,
        *,
        append: str = "",
        replacements: dict[str, str] | None = None,
    ) -> Path:
        text = source.read_text(encoding="utf-8")
        for old, new in (replacements or {}).items():
            text = text.replace(old, new)
        target = tmp_path / source.name
        target.write_text(text + append, encoding="utf-8")
        return target

    return _copy
