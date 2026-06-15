"""Tests for the release-candidate audit document.

These tests validate that the audit document exists, contains required
sections, and does not contain prohibited claims or false success claims.
"""

from __future__ import annotations

from pathlib import Path

import pytest


AUDIT_PATH = Path("docs/archive/release-candidates/release-candidate-audit-v0.5.7.dev2.md")


class TestReleaseCandidateAuditDocs:
    def test_audit_document_exists(self) -> None:
        assert AUDIT_PATH.exists(), f"Audit document not found: {AUDIT_PATH}"

    def test_audit_document_contains_required_headings(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        required = [
            "# Release Candidate Audit",
            "## Scope",
            "## Version and Tag State",
            "## Release Gate Results",
            "## Smoke Scripts",
            "## Safety Contract State",
            "## Runtime Behavior Change Check",
            "## Protected / Untracked Files",
            "## Known Limitations",
            "## Recommendation",
        ]
        for heading in required:
            assert heading in content, f"Missing required heading: {heading!r}"

    def test_audit_document_contains_development_tag(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        assert "development tag" in content.lower(), (
            "Audit should identify this as a development tag"
        )

    def test_audit_document_does_not_contain_forbidden_claims(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        forbidden = [
            "guaranteed profit",
            "zero risk",
            "risk free",
            "risk-free",
            "100% accurate",
            "always wins",
            "never loses",
            "get rich quick",
            "financial advice",
        ]
        for claim in forbidden:
            assert claim.lower() not in content.lower(), (
                f"Forbidden claim found in audit doc: {claim!r}"
            )

    def test_audit_document_mentions_known_limitations(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        assert "Known Limitations" in content
        assert "limitation" in content.lower() or "not a claim" in content.lower()

    def test_audit_document_mentions_protected_untracked_files(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        assert "Protected" in content or "Untracked" in content
        assert "AUDIT_ENHANCEMENTS" in content or "BATCH2_PLAN" in content

    def test_audit_document_mentions_no_runtime_behavior_changes(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        assert "Runtime Behavior Change Check" in content
        assert "no output" in content.lower() or "no diff" in content.lower()

    # ------------------------------------------------------------------
    # Truthfulness tests for smoke status
    # ------------------------------------------------------------------

    def test_audit_doc_does_not_claim_network_smokes_passed_when_blocked(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8").lower()
        # The doc must not claim these passed in the current environment
        unsupported_pass_claims = [
            "smoke_release_tag.sh v0.5.7.dev2" in content and "pass" in content,
            "tag smoke" in content and "passed" in content,
            "default package build smoke passed" in content,
            "all smoke scripts pass" in content,
        ]
        # Check the specific smoke script lines for false PASS claims
        lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
        for line in lines:
            lowered = line.lower()
            if "smoke_release_tag" in lowered and "pass" in lowered and "not" not in lowered:
                pytest.fail(
                    f"Audit doc falsely claims tag smoke passed: {line!r}"
                )
            if "smoke_package_build.sh" in lowered and "pass" in lowered and "not" not in lowered and "offline" not in lowered:
                pytest.fail(
                    f"Audit doc falsely claims default package smoke passed: {line!r}"
                )

    def test_audit_doc_records_network_blocked_smoke_status(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8").lower()
        # Must mention the network/DNS blockers
        assert "github.com" in content or "github" in content, (
            "Audit should mention GitHub for tag smoke blocker"
        )
        assert "pypi.org" in content or "pypi" in content, (
            "Audit should mention PyPI for package smoke blocker"
        )
        assert "dns" in content or "network" in content or "could not be resolved" in content, (
            "Audit should mention DNS or network resolution failure"
        )
        assert "did not pass" in content or "not passed" in content, (
            "Audit should record that smokes did not pass"
        )

    def test_audit_doc_conclusion_is_conditional(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8").lower()
        rec_section = content.split("## recommendation")[1] if "## recommendation" in content else ""
        # Must mention that network smokes need rerun
        assert "network-enabled environment" in rec_section or "rerun" in rec_section, (
            "Recommendation should mention rerunning in a network-enabled environment"
        )
        # Must not unconditionally claim all smokes passed
        assert "all smoke scripts pass" not in rec_section, (
            "Recommendation should not claim all smokes passed unconditionally"
        )
        assert "tag smoke passed" not in rec_section, (
            "Recommendation should not claim tag smoke passed"
        )
        assert "package build smoke passed" not in rec_section, (
            "Recommendation should not claim package smoke passed unconditionally"
        )

    def test_audit_doc_does_not_hardcode_pytest_pass_count(self) -> None:
        import re

        content = AUDIT_PATH.read_text(encoding="utf-8")
        # Reject any exact test count like "1792 passed" or "3 failed"
        pass_matches = list(re.finditer(r"\b\d+\s+passed\b", content, re.IGNORECASE))
        fail_matches = list(re.finditer(r"\b\d+\s+failed\b", content, re.IGNORECASE))
        if pass_matches:
            pytest.fail(
                f"Audit doc hardcodes exact pytest pass counts: "
                f"{[m.group(0) for m in pass_matches]!r}"
            )
        if fail_matches:
            pytest.fail(
                f"Audit doc hardcodes exact pytest fail counts: "
                f"{[m.group(0) for m in fail_matches]!r}"
            )

    def test_audit_doc_release_gate_count_current_or_non_brittle(self) -> None:
        content = AUDIT_PATH.read_text(encoding="utf-8")
        # Must use stable wording instead of hardcoded counts
        stable_wording = (
            "Passed in the latest release_check.sh run" in content
            or "see the release_check.sh output for the exact current test count" in content
            or "Passed in the latest local validation" in content
        )
        assert stable_wording, (
            "Audit doc should use stable wording for pytest results, not hardcoded counts"
        )
