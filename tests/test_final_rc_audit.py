"""Tests for final RC audit script and docs — Batch 10.12.

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
SCRIPT = ROOT / "scripts" / "check_final_rc_audit.py"
AUDIT_DOC = ROOT / "docs" / "final-rc-audit.md"
CHECKLIST_DOC = ROOT / "docs" / "final-release-candidate-checklist.md"

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
    def test_final_rc_audit_doc_exists(self) -> None:
        assert AUDIT_DOC.exists(), f"Final RC audit doc not found: {AUDIT_DOC}"

    def test_final_release_candidate_checklist_exists(self) -> None:
        assert CHECKLIST_DOC.exists(), f"Final RC checklist not found: {CHECKLIST_DOC}"

    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestReadmeLinks:
    @pytest.fixture
    def readme_text(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_links_to_final_rc_audit(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "final-rc-audit.md" in readme_text
            or "final rc audit" in lower
        )

    def test_readme_links_to_final_checklist(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "final-release-candidate-checklist.md" in readme_text
            or "final release candidate checklist" in lower
        )

    def test_readme_links_to_public_launch_readiness(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "public-launch-readiness.md" in readme_text
            or "public launch readiness" in lower
        )

    def test_readme_links_to_public_faq(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "public-faq.md" in readme_text
            or "public faq" in lower
        )


class TestAuditDocSafety:
    def test_no_forbidden_claims(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
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
                pytest.fail(f"final-rc-audit.md contains forbidden claim: {claim}")

    def test_no_forbidden_fragments(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8")
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"final-rc-audit.md contains forbidden fragment: {frag}"

    def test_no_absolute_paths(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8")
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in text, f"final-rc-audit.md contains absolute path: {frag}"

    def test_no_live_trading_readiness_claims(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text
        assert "production trading ready" not in text
        assert "safe to trade" not in text

    def test_no_profitability_claims(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text
        assert "profitable strategy" not in text
        assert "verified alpha" not in text
        assert "beats the market" not in text

    def test_does_not_claim_stable_release_happened(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        # The doc should use conditional language about preparing a stable release,
        # not claim it has already happened.
        assert "stable v0.5.7 has been released" not in text
        assert "v0.5.7 is now stable" not in text

    def test_mentions_live_trading_disabled(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "live trading" in text and "disabled by default" in text

    def test_mentions_provider_execution_locked(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "provider execution remains locked" in text

    def test_mentions_trust_blocked(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "trust remains blocked" in text

    def test_mentions_not_financial_advice(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "not financial advice" in text

    def test_suggests_rc10_or_final_framework(self) -> None:
        text = AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "rc10" in text or "v0.5.7 final" in text


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
                pytest.fail(f"final-release-candidate-checklist.md contains forbidden claim: {claim}")


class TestScriptBehavior:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Final RC audit script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_json_output(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Final RC audit script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == "0.5.8rc4"
        assert data["public_tag"] == "v0.5.7"
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
    def test_package_version_is_current_dev(self) -> None:
        import tomllib
        pyproject = ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert data.get("project", {}).get("version") == "0.5.8rc4"

    def test_init_version_is_current_dev(self) -> None:
        init = ROOT / "src" / "atlas_agent" / "__init__.py"
        text = init.read_text(encoding="utf-8")
        import re
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m is not None
        assert m.group(1) == "0.5.8rc4"

    def test_release_note_exists(self) -> None:
        assert (ROOT / "docs" / "releases" / "v0.5.7-rc9.md").exists()
