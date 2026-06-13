"""Tests for stable release decision script and docs — Batch 10.13.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_stable_release_decision.py"
DECISION_DOC = ROOT / "docs" / "stable-release-decision.md"
CHECKLIST_DOC = ROOT / "docs" / "stable-release-checklist.md"

_FORBIDDEN_POSITIVE_CLAIMS = (
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
)

_FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "/var/folders/",
    "/tmp/",
    "/var/tmp/",
)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result


class TestDocsExist:
    def test_stable_release_decision_doc_exists(self) -> None:
        assert DECISION_DOC.exists(), f"Stable release decision doc not found: {DECISION_DOC}"

    def test_stable_release_checklist_exists(self) -> None:
        assert CHECKLIST_DOC.exists(), f"Stable release checklist not found: {CHECKLIST_DOC}"

    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestReadmeLinks:
    @pytest.fixture
    def readme_text(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_links_to_stable_decision(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "stable-release-decision.md" in readme_text
            or "stable release decision" in lower
        )

    def test_readme_links_to_stable_checklist(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "stable-release-checklist.md" in readme_text
            or "stable release checklist" in lower
        )

    def test_readme_current_status_is_v0610(self, readme_text: str) -> None:
        assert "v0.6.10" in readme_text


class TestDecisionDocSafety:
    def test_no_forbidden_claims(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        for claim in _FORBIDDEN_POSITIVE_CLAIMS:
            if claim not in text:
                continue
            idx = text.index(claim)
            context_start = max(0, idx - 120)
            context_end = min(len(text), idx + 120)
            context = text[context_start:context_end]
            negative_indicators = (
                "not ", "does not", "never", "no ", "avoid",
                "disclaimer", "prohibited", "forbidden", "must not",
                "cannot", "do not", "is not", "are not", "without",
                "fail closed", "not yet", "not implemented", "not enabled",
                "not authorized", "not a ", "not ready", "remains disabled",
                "remains locked", "remains blocked", "do not assume",
            )
            if not any(ind in context for ind in negative_indicators):
                pytest.fail(f"stable-release-decision.md contains forbidden claim: {claim}")

    def test_no_forbidden_fragments(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8")
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"stable-release-decision.md contains forbidden fragment: {frag}"

    def test_no_absolute_paths(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8")
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"stable-release-decision.md contains absolute path: {frag}"

    def test_no_live_trading_readiness_claims(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text
        assert "production trading ready" not in text
        assert "safe to trade" not in text

    def test_no_profitability_claims(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text
        assert "profitable strategy" not in text
        assert "verified alpha" not in text
        assert "beats the market" not in text

    def test_explains_stable_means_release_process_docs_stability(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "release/documentation/process stability" in text or "release process stability" in text

    def test_stable_does_not_mean_live_trading_readiness(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "live trading readiness" not in text or "does not mean" in text
        assert "production trading readiness" not in text or "does not mean" in text

    def test_does_not_claim_stable_release_published_externally(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        # Allow negative contexts like "does not claim that v0.5.8 has already been published"
        positive_claims = [
            "v0.6.8 has been released externally",
            "v0.6.8 is now live",
            "v0.6.8 is already published",
        ]
        for claim in positive_claims:
            assert claim not in text, f"Doc contains positive publication claim: {claim}"

    def test_mentions_live_trading_disabled(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "live trading" in text and "disabled" in text

    def test_mentions_provider_execution_locked(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "provider execution remains locked" in text

    def test_mentions_trust_blocked(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "trust remains blocked" in text

    def test_mentions_not_financial_advice(self) -> None:
        text = DECISION_DOC.read_text(encoding="utf-8").lower()
        assert "not financial advice" in text


class TestChecklistDoc:
    def test_includes_protected_boundary_commands(self) -> None:
        text = CHECKLIST_DOC.read_text(encoding="utf-8").lower()
        assert "git diff -- src/atlas_agent/config" in text

    def test_includes_release_check_full(self) -> None:
        text = CHECKLIST_DOC.read_text(encoding="utf-8").lower()
        assert "release_check.sh --full" in text

    def test_no_forbidden_claims(self) -> None:
        text = CHECKLIST_DOC.read_text(encoding="utf-8").lower()
        for claim in _FORBIDDEN_POSITIVE_CLAIMS:
            if claim not in text:
                continue
            idx = text.index(claim)
            context_start = max(0, idx - 120)
            context_end = min(len(text), idx + 120)
            context = text[context_start:context_end]
            negative_indicators = (
                "not ", "does not", "never", "no ", "avoid",
                "disclaimer", "prohibited", "forbidden", "must not",
                "cannot", "do not", "is not", "are not", "without",
                "fail closed", "not yet", "not implemented", "not enabled",
                "not authorized", "not a ", "not ready", "remains disabled",
                "remains locked", "remains blocked", "do not assume",
            )
            if not any(ind in context for ind in negative_indicators):
                pytest.fail(f"stable-release-checklist.md contains forbidden claim: {claim}")


class TestScriptBehavior:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Stable release decision script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_json_output(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from release_metadata import load_metadata, ReleaseMetadata
        _meta = ReleaseMetadata(load_metadata(ROOT / "docs" / "releases" / "release-metadata.json"))
        sys.path.pop(0)

        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Stable release decision script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == _meta.source_version
        assert data["public_tag"] == _meta.current_public_release
        assert data["errors"] == []

    def test_json_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in result.stdout, f"JSON output contains absolute path: {frag}"


class TestScriptSafety:
    def test_no_github_api_usage(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "github api" not in text or "does not" in text

    def test_no_publish_or_upload(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "twine upload" not in text
        assert "gh release create" not in text

    def test_no_git_push_or_tag(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "git push" not in text
        assert "git tag" not in text

    def test_no_shell_true(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in text

    def test_no_secrets_required(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "api_key" not in text
        assert "secret" not in text or "secret-like" in text


class TestVersionConsistency:
    def test_package_version_is_dev(self) -> None:
        import tomllib
        pyproject = ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert data.get("project", {}).get("version") == "0.6.10"

    def test_init_version_is_dev(self) -> None:
        init = ROOT / "src" / "atlas_agent" / "__init__.py"
        text = init.read_text(encoding="utf-8")
        import re
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m is not None
        assert m.group(1) == "0.6.10"

    def test_release_note_exists(self) -> None:
        assert (ROOT / "docs" / "releases" / "v0.6.10.md").exists()

    def test_changelog_has_stable_entry(self) -> None:
        changelog = ROOT / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        assert "[0.6.10]" in text
