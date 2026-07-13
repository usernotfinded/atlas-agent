"""Tests for public docs consistency script — Batch 10.0.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_public_docs_consistency.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_public_docs_consistency", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_public_docs_consistency"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script_on_text(text: str) -> subprocess.CompletedProcess[str]:
    """Run the consistency script with a temporary doc under REPO_ROOT.

    The temporary doc is placed inside a temp directory under REPO_ROOT
    so that Path.relative_to(REPO_ROOT) works in the script. The script
    is invoked via a small wrapper that imports the module and overrides
    PUBLIC_DOC_PATHS, avoiding brittle string-replacement of the list.
    """
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))
    tmp_path = tmp_dir / "test_doc.md"
    tmp_path.write_text(text, encoding="utf-8")

    wrapper = f'''import sys
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT / "scripts")!r})
sys.path.insert(0, {str(REPO_ROOT)!r})
import check_public_docs_consistency as mod
mod.PUBLIC_DOC_PATHS = [Path({str(tmp_path)!r})]
sys.exit(mod.main())
'''
    tmp_script = tmp_dir / "check.py"
    tmp_script.write_text(wrapper, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True,
        text=True,
    )
    # Clean up temp files
    try:
        tmp_path.unlink()
        tmp_script.unlink()
        tmp_dir.rmdir()
    except OSError:
        pass
    return result


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestScriptPassesOnCurrentDocs:
    def test_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Public docs consistency script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_public_docs_still_pass_on_current_baseline(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Public docs consistency script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_no_forbidden_claims_introduced(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_forbidden_claims.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Forbidden claims checker failed:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsUnsafePositiveClaims:
    def test_rejects_live_trading_ready(self) -> None:
        text = "# Doc\n\n```bash\natlas --help\n```\n\nLive trading ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected failure on live trading ready claim"
        assert "live trading ready" in result.stdout.lower()

    def test_rejects_provider_execution_enabled(self) -> None:
        text = "# Doc\n\nProvider execution enabled.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "provider execution enabled" in result.stdout.lower()

    def test_rejects_guaranteed_profit(self) -> None:
        text = "# Doc\n\nThis strategy produces guaranteed profit.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "guaranteed profit" in result.stdout.lower()


class TestScriptAcceptsNegativeSafetyWording:
    def test_accepts_not_live_trading_ready(self) -> None:
        text = "# Doc\n\nLive trading is not ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for negative wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_live_trading_disabled(self) -> None:
        text = "# Doc\n\nLive trading remains disabled by default.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for disabled wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_provider_execution_locked(self) -> None:
        text = "# Doc\n\nProvider execution remains locked.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for locked wording:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsAbsolutePaths:
    def test_rejects_users_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /Users/natan/dev\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/Users/" in result.stdout

    def test_rejects_private_var_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /private/var/tmp\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/private/var/" in result.stdout


class TestScriptRejectsForbiddenFragments:
    def test_rejects_sk_token(self) -> None:
        text = "# Doc\n\n```bash\nexport KEY=sk-abc123def456\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "sk-" in result.stdout.lower()

    def test_rejects_bearer_token(self) -> None:
        text = "# Doc\n\n```bash\ncurl -H 'Authorization: Bearer xyz123'\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "bearer" in result.stdout.lower()


class TestScriptRejectsUnsafeCommands:
    def test_rejects_curl(self) -> None:
        text = "# Doc\n\n```bash\ncurl https://api.example.com\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "curl" in result.stdout.lower()

    def test_rejects_order_create(self) -> None:
        text = "# Doc\n\n```bash\natlas order create --symbol AAPL\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "order create" in result.stdout.lower()


class TestScriptRequiresNotFinancialAdvice:
    def test_requires_not_financial_advice(self) -> None:
        text = "# Doc\n\nSome safe text.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "not financial advice" in result.stdout.lower()


class TestReadmeCurrentVersion:
    def test_readme_missing_current_status_fails(self) -> None:
        mod = _load_script_module()
        text = "# README\n\nSome text.\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", "v1.2.3")
        assert len(violations) == 1
        assert "v1.2.3" in violations[0]

    def test_readme_has_current_status_passes(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", "v0.6.8")
        assert violations == []

    def test_skipped_for_non_readme(self) -> None:
        mod = _load_script_module()
        text = "# Doc\n\nNo status here.\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "OTHER.md", "v0.6.8")
        assert violations == []


class TestStaleCurrentStatusInReadme:
    def test_stale_current_status_fails(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.4)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "README.md", "v1.2.3")
        assert len(violations) == 1
        assert "v0.6.4" in violations[0]
        assert "v1.2.3" in violations[0]

    def test_current_status_passes(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "README.md", "v0.6.8")
        assert violations == []

    def test_skipped_for_non_readme(self) -> None:
        mod = _load_script_module()
        text = "# Doc\n\n> **Current Status (v0.6.4)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "OTHER.md", "v1.2.3")
        assert violations == []


class TestChangelogReferencesReleaseNotes:
    def test_orphaned_release_note_warns(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.5.8.1.md").write_text("# v0.5.8.1\n")
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.5]\n\nSee v0.6.5.md\n")

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert any("v0.5.8.1.md" in w for w in warnings)
            assert not any("v0.6.5.md" in w for w in warnings)
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

    def test_all_referenced_no_warnings(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\nSee v0.6.5.md\n")

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert warnings == []
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

    def test_missing_changelog_warns(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert any("not found" in w for w in warnings)
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

class TestStalePublicReleaseClaims:
    def test_flags_stale_latest_stable_claim(self) -> None:
        mod = _load_script_module()
        text = "Atlas Agent `v0.6.8` is the latest stable public release. Not financial advice."
        violations = mod._check_stale_public_release_claims(text, "public-faq.md", "v0.6.9")
        assert len(violations) == 1
        assert "v0.6.8" in violations[0]
        assert "expected v0.6.9" in violations[0]

    def test_passes_current_latest_stable_claim(self) -> None:
        mod = _load_script_module()
        text = "The latest stable public GitHub release is `v0.6.9`. Not financial advice."
        violations = mod._check_stale_public_release_claims(text, "public-faq.md", "v0.6.9")
        assert violations == []

    def test_allows_historical_context(self) -> None:
        mod = _load_script_module()
        text = "`v0.6.8` is the latest stable public release, but it is now historical. Not financial advice."
        violations = mod._check_stale_public_release_claims(text, "public-faq.md", "v0.6.9")
        assert violations == []

    def test_skips_historical_docs(self) -> None:
        mod = _load_script_module()
        text = "The latest stable public GitHub release is `v0.6.8`. Not financial advice."
        violations = mod._check_stale_public_release_claims(text, "releases/v0.6.8.md", "v0.6.9")
        assert violations == []


class TestStaleReleaseStatusLines:
    def test_flags_stale_latest_public_tag(self) -> None:
        mod = _load_script_module()
        text = "- **Latest public tag:** `v0.6.9`"
        violations = mod._check_stale_release_status_lines(
            text, "public-repo-hygiene.md", "v0.6.10"
        )
        assert len(violations) == 1
        assert "v0.6.9" in violations[0]
        assert "expected v0.6.10" in violations[0]

    def test_flags_mixed_source_public_status(self) -> None:
        mod = _load_script_module()
        text = "Current status: v0.6.10 source / v0.6.9 public."
        violations = mod._check_stale_release_status_lines(
            text, "public-feedback-checklist.md", "v0.6.10"
        )
        assert len(violations) == 1
        assert "v0.6.9" in violations[0]

    def test_flags_current_release_described_as_untagged(self) -> None:
        mod = _load_script_module()
        text = "The v0.6.10 public release is prepared, not yet tagged."
        violations = mod._check_stale_release_status_lines(
            text, "reviewer-golden-path.md", "v0.6.10"
        )
        assert len(violations) == 1
        assert "prepared or untagged" in violations[0]

    def test_allows_current_public_and_historical_release(self) -> None:
        mod = _load_script_module()
        text = "v0.6.10 public; v0.6.9 is historical."
        violations = mod._check_stale_release_status_lines(
            text, "public-launch-messaging.md", "v0.6.10"
        )
        assert violations == []

    def test_skips_historical_release_docs(self) -> None:
        mod = _load_script_module()
        text = "Latest public tag: v0.6.9"
        violations = mod._check_stale_release_status_lines(
            text, "releases/v0.6.9.md", "v0.6.10"
        )
        assert violations == []

    def test_flags_stale_current_public_release_parenthetical(self) -> None:
        mod = _load_script_module()
        text = (
            "L3 is not implemented in the current release line "
            "(`v0.6.20` current public release; `v0.6.21` planning-only)."
        )
        violations = mod._check_stale_release_status_lines(
            text, "docs/autonomy-roadmap.md", "v0.6.21"
        )
        assert len(violations) == 1
        assert "v0.6.20" in violations[0]
        assert "expected v0.6.21" in violations[0]


class TestTrustReadmeCurrentPublicLabels:
    def _check(self, text: str) -> list[str]:
        mod = _load_script_module()
        return mod._check_trust_readme_current_public_labels(
            text,
            "docs/trust/README.md",
            "v0.6.21",
            "v0.6.22",
            {"v0.6.18", "v0.6.19", "v0.6.20"},
        )

    def test_trust_readme_current_public_label_passes(self) -> None:
        text = (
            "- Public v0.6.21: current public - status\n"
            "- [v0.6.21 Trust and Release Status](v0.6.21-status.md) "
            "(current public)\n"
        )
        assert self._check(text) == []

    def test_trust_readme_old_release_current_public_fails(self) -> None:
        text = "- [v0.6.20 Trust and Release Status](v0.6.20-status.md) (current public)\n"
        violations = self._check(text)
        assert len(violations) == 1
        assert "docs/trust/README.md" in violations[0]
        assert "v0.6.20" in violations[0]
        assert "v0.6.21" in violations[0]

    def test_trust_readme_historical_label_passes(self) -> None:
        text = "- [v0.6.20 Trust and Release Status](v0.6.20-status.md) (historical)\n"
        assert self._check(text) == []

    def test_trust_readme_next_planned_label_passes(self) -> None:
        text = "- [v0.6.22 Planning Status](v0.6.22-status.md) (next planned)\n"
        assert self._check(text) == []

    def test_trust_readme_next_planned_current_public_fails(self) -> None:
        text = "- [v0.6.22 Planning Status](v0.6.22-status.md) (current public)\n"
        violations = self._check(text)
        assert len(violations) == 1
        assert "v0.6.22" in violations[0]
        assert "v0.6.21" in violations[0]

    def test_trust_readme_inline_current_public_old_release_fails(self) -> None:
        text = "- Public v0.6.20: current public - release status\n"
        violations = self._check(text)
        assert len(violations) == 1
        assert "v0.6.20" in violations[0]
        assert "v0.6.21" in violations[0]


class TestAutonomyRoadmapCandidateState:
    def test_roadmap_no_candidates_contradiction_fails(self) -> None:
        mod = _load_script_module()
        text = "No candidates are currently proposed for `v0.6.22`."
        violations = mod._check_autonomy_roadmap_candidate_state(
            text, "docs/autonomy-roadmap.md", "v0.6.22", True
        )
        assert len(violations) == 1
        assert "docs/autonomy-roadmap.md" in violations[0]
        assert "v0.6.22" in violations[0]
        assert "accepted/released candidates are recorded" in violations[0]

    def test_roadmap_no_candidates_when_none_accepted_passes(self) -> None:
        mod = _load_script_module()
        text = "No candidates are currently proposed for `v0.6.22`."
        violations = mod._check_autonomy_roadmap_candidate_state(
            text, "docs/autonomy-roadmap.md", "v0.6.22", False
        )
        assert violations == []

    def test_roadmap_historical_no_candidates_paragraph_passes(self) -> None:
        mod = _load_script_module()
        text = "Historical note: no candidates are currently proposed for `v0.6.22` before selection."
        violations = mod._check_autonomy_roadmap_candidate_state(
            text, "docs/autonomy-roadmap.md", "v0.6.22", True
        )
        assert violations == []


class TestNextPlannedAcceptedCandidates:
    def _write_candidates(self, tmp_path: Path, candidates: list[dict[str, object]]) -> Path:
        repo = tmp_path / "repo"
        releases = repo / "docs" / "releases"
        releases.mkdir(parents=True)
        (releases / "v0.6.22-candidates.json").write_text(
            json.dumps({"candidates": candidates}),
            encoding="utf-8",
        )
        return repo

    def test_next_planned_has_accepted_candidates_true_for_accepted_true(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        repo = self._write_candidates(tmp_path, [{"id": "CAND-X", "accepted": True}])
        assert mod._next_planned_has_accepted_candidates(repo, "v0.6.22") is True

    def test_next_planned_has_accepted_candidates_true_for_status_accepted(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        repo = self._write_candidates(tmp_path, [{"id": "CAND-X", "status": "accepted"}])
        assert mod._next_planned_has_accepted_candidates(repo, "v0.6.22") is True

    def test_next_planned_has_accepted_candidates_true_for_status_released(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        repo = self._write_candidates(tmp_path, [{"id": "CAND-X", "status": "released"}])
        assert mod._next_planned_has_accepted_candidates(repo, "v0.6.22") is True

    def test_next_planned_has_accepted_candidates_false_for_no_accepted(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        repo = self._write_candidates(
            tmp_path, [{"id": "CAND-X", "status": "proposed", "accepted": False}]
        )
        assert mod._next_planned_has_accepted_candidates(repo, "v0.6.22") is False

    def test_next_planned_has_accepted_candidates_false_for_missing_file(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        repo = tmp_path / "repo"
        repo.mkdir()
        assert mod._next_planned_has_accepted_candidates(repo, "v0.6.22") is False


class TestDynamicMetadata:
    def test_reads_dynamic_metadata(self, tmp_path: Path) -> None:
        """Test that changing fixture metadata changes expected checker targets."""
        mod = _load_script_module()
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()
        meta_dir = fake_repo / "docs" / "releases"
        meta_dir.mkdir(parents=True)

        meta_path = meta_dir / "release-metadata.json"
        meta_path.write_text('{"source_version": "0.9.9", "current_public_release": "v0.9.8"}', encoding="utf-8")

        current_version = mod._get_current_version(fake_repo)
        assert current_version == "v0.9.9"

        text = "# README\n\n> **Current Status (v0.9.9)**\n\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", current_version)
        assert violations == []

        text_bad = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations_bad = mod._check_readme_current_version(text_bad, "README.md", current_version)
        assert len(violations_bad) == 1
        assert "v0.9.9" in violations_bad[0]

        violations_stale = mod._check_stale_current_status_in_readme(text_bad, "README.md", current_version)
        assert len(violations_stale) == 1
        assert "expected v0.9.9" in violations_stale[0]

    def test_missing_metadata_fallback(self, tmp_path: Path) -> None:
        """invalid/missing metadata fails clearly."""
        mod = _load_script_module()
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        import pytest
        with pytest.raises(FileNotFoundError, match="Release metadata not found"):
            mod._get_current_version(fake_repo)

        meta_dir = fake_repo / "docs" / "releases"
        meta_dir.mkdir(parents=True)
        meta_path = meta_dir / "release-metadata.json"
        meta_path.write_text('{"bad_schema": "0.9.9"}', encoding="utf-8")

        with pytest.raises(Exception, match="source_version is empty in metadata"):
            mod._get_current_version(fake_repo)


class TestAutonomyRoadmapReleasedCandidateDrift:
    """Reverse drift: a released candidate must not be listed under the
    next-planned planning line (CAND-016 coverage)."""

    _NEXT = "v0.6.22"
    _RELEASED = {"CAND-013", "CAND-014", "CAND-015"}

    def _section(self, body: str) -> str:
        return (
            "## Autonomy roadmap\n\n"
            f"### Candidate status in the `{self._NEXT}` planning line\n\n"
            f"`{self._NEXT}` is the next planned release line and is not released.\n\n"
            f"{body}\n\n"
            "## Current state vs future state\n"
        )

    def test_released_candidate_bullet_under_next_planned_fails(self) -> None:
        mod = _load_script_module()
        text = self._section("- **CAND-013** is accepted into the `v0.6.22` candidate chain.")
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, self._RELEASED
        )
        assert len(violations) == 1
        assert "CAND-013" in violations[0]
        assert self._NEXT in violations[0]
        assert "already-released" in violations[0]

    def test_multiple_released_candidates_each_flagged(self) -> None:
        mod = _load_script_module()
        text = self._section(
            "- **CAND-013** is accepted.\n- **CAND-015** is accepted."
        )
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, self._RELEASED
        )
        assert len(violations) == 2
        assert any("CAND-013" in v for v in violations)
        assert any("CAND-015" in v for v in violations)

    def test_proposed_candidate_under_next_planned_passes(self) -> None:
        mod = _load_script_module()
        text = self._section("- **CAND-016** is proposed for `v0.6.22`.")
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, self._RELEASED
        )
        assert violations == []

    def test_prose_mention_of_released_candidate_passes(self) -> None:
        mod = _load_script_module()
        text = self._section(
            "- **CAND-016** extends the drift guard first shipped as CAND-013."
        )
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, self._RELEASED
        )
        assert violations == []

    def test_released_candidate_in_release_section_passes(self) -> None:
        mod = _load_script_module()
        # A released candidate under its own release section (not the planning
        # line) must not be flagged.
        text = (
            "### Candidate status in the `v0.6.21` release\n\n"
            "- **CAND-013** is released in `v0.6.21`.\n\n"
            f"### Candidate status in the `{self._NEXT}` planning line\n\n"
            "- **CAND-016** is proposed.\n\n"
            "## Current state\n"
        )
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, self._RELEASED
        )
        assert violations == []

    def test_no_released_ids_is_noop(self) -> None:
        mod = _load_script_module()
        text = self._section("- **CAND-013** is accepted.")
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/autonomy-roadmap.md", self._NEXT, set()
        )
        assert violations == []

    def test_non_roadmap_path_is_noop(self) -> None:
        mod = _load_script_module()
        text = self._section("- **CAND-013** is accepted.")
        violations = mod._check_autonomy_roadmap_released_candidates_not_next_planned(
            text, "docs/public-faq.md", self._NEXT, self._RELEASED
        )
        assert violations == []

    def test_released_candidate_ids_reads_released_lines(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        repo = tmp_path / "repo"
        releases = repo / "docs" / "releases"
        releases.mkdir(parents=True)
        (releases / "release-metadata.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_version": "0.6.21",
                    "current_public_release": "v0.6.21",
                    "next_planned_release": "v0.6.22",
                    "pypi_published": False,
                    "releases": [
                        {"tag": "v0.6.21", "version": "0.6.21", "status": "current_public"},
                        {"tag": "v0.6.20", "version": "0.6.20", "status": "historical"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (releases / "v0.6.21-candidates.json").write_text(
            json.dumps(
                {"candidates": [{"id": "CAND-013", "status": "released", "accepted": True}]}
            ),
            encoding="utf-8",
        )
        (releases / "v0.6.20-candidates.json").write_text(
            json.dumps(
                {"candidates": [{"id": "CAND-012", "accepted": True}]}
            ),
            encoding="utf-8",
        )
        # A pending candidate in the next-planned line must NOT be treated as released.
        (releases / "v0.6.22-candidates.json").write_text(
            json.dumps({"candidates": [{"id": "CAND-016", "status": "proposed"}]}),
            encoding="utf-8",
        )
        ids = mod._released_candidate_ids(repo)
        assert "CAND-013" in ids
        assert "CAND-012" in ids
        assert "CAND-016" not in ids
