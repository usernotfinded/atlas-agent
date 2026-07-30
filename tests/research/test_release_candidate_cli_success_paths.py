# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_release_candidate_cli_success_paths.py
# PURPOSE: Drives the release-candidate CLI commands to success, which nothing
#         else did.
# DEPS:    contextlib, io, json, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Success envelopes for the release-candidate commands.

`tests/research/test_release_candidate_readiness.py` and its cutover twin are
thorough, but they call the domain functions directly and never go through the
CLI handler. `tests/research/test_research_command_envelopes.py` does go through
the CLI, but it builds argv from placeholder IDs against an empty workspace, so
every one of its 175 cases takes the not-found path.

Between them, four success statuses were asserted nowhere in `tests/`:

    research_release_candidate_readiness_list
    research_release_candidate_readiness_validated
    research_release_candidate_cutover_dry_run_list
    research_release_candidate_cutover_dry_run_validated

That matters beyond these commands. `CAND-035` proposes absorbing the repeated
handler scaffolding across 170 handlers and leans on the envelope suite as its
safety net — a net that pins the error envelope, which is what the wrapper
absorbs, and pins nothing about the success branch, which such a refactor also
rewrites.

The two `_list` statuses are covered here, along with readiness `-show`,
`-doctor` and `-summary`, which a later execution measurement found were never
driven to exit 0 either.

Every command in both families now reaches its success envelope here.

The two `..._validated` *statuses* remain uncovered, and deliberately: validation
passing requires the repository itself — README safety claims, version
consistency, a forbidden-claims scan, the protected-boundary check, and named
docs and scripts. Reaching `..._validated` from a temporary workspace would mean
reconstructing the repo, so `test_release_candidate_readiness.py` covers that
logic at the domain level instead, and
`test_the_validated_statuses_are_blocked_for_a_stated_reason` pins the reason.
Note the distinction: `-validate` reaches exit 0 either way, reporting
`..._validation_failed`; it is the verdict that needs the repo, not the command.

An earlier version of this file also claimed the cutover family's *creation* was
blocked by repository state. It is not — see the comment above the cutover cases
for what was actually going on.
"""

# --- IMPORTS ---

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run(argv: list[str]) -> tuple[int | None, dict]:
    """Run a CLI command and return its status and parsed JSON envelope."""
    from atlas_agent.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        main(["init", "."])
    return tmp_path


def test_readiness_list_answers_in_its_success_envelope(workspace: Path) -> None:
    """The created report has to come back out of the listing.

    Asserting the status alone would pass against an empty list, which is what
    the command returns before anything is created — so the report id is checked
    through as well.
    """
    _code, created = _run(["research", "release-candidate-readiness", "--json"])
    report_id = created["release_candidate_readiness_report_id"]

    code, listed = _run(["research", "release-candidate-readiness-list", "--json"])

    assert code == 0
    assert listed["status"] == "research_release_candidate_readiness_list"
    assert report_id in [
        item["release_candidate_readiness_report_id"] for item in listed["items"]
    ]


def test_cutover_dry_run_list_answers_in_its_success_envelope(workspace: Path) -> None:
    """The listing answers before anything has been created.

    An empty listing is a real state worth pinning separately from the populated
    one in `test_the_cutover_listing_contains_the_created_report`.
    """
    code, listed = _run(["research", "release-candidate-cutover-dry-run-list", "--json"])

    assert code == 0
    assert listed["status"] == "research_release_candidate_cutover_dry_run_list"
    assert listed["items"] == []


def test_the_validated_statuses_are_blocked_for_a_stated_reason(workspace: Path) -> None:
    """Why the other two success statuses are not covered here.

    Not an accident and not a gap a fixture should paper over: readiness in a
    temporary workspace is blocked on the repository's own contents. If this
    ever starts passing, validation has stopped depending on them and the two
    `..._validated` statuses become reachable — at which point they want tests.
    """
    _code, created = _run(["research", "release-candidate-readiness", "--json"])
    report_id = created["release_candidate_readiness_report_id"]

    code, validated = _run(
        ["research", "release-candidate-readiness-validate", report_id, "--json"]
    )

    assert code == 0
    assert validated["status"] == "research_release_candidate_readiness_validation_failed"
    # The blockers name repository state, which is what makes this unreachable
    # from a synthetic workspace rather than merely unimplemented.
    assert any(b.startswith("doc_present:") for b in created["blockers"])
    assert "version_consistency" in created["blockers"]


# ---------------------------------------------------------------------------
# The readiness inspection commands
#
# `-show`, `-doctor` and `-summary` were among the 17 commands a full suite run
# never drove to exit 0, for the same reason as the dossier family: this
# command's own tests call the domain functions directly. Creation succeeds in a
# temporary workspace, so all three are reachable from a created report.
# ---------------------------------------------------------------------------


def _readiness_report_id() -> str:
    _code, created = _run(["research", "release-candidate-readiness", "--json"])
    assert created["status"] == "research_release_candidate_readiness_created", created
    return created["release_candidate_readiness_report_id"]


def test_readiness_doctor_answers_in_its_success_envelope(workspace: Path) -> None:
    report_id = _readiness_report_id()

    code, payload = _run(["research", "release-candidate-readiness-doctor", report_id, "--json"])

    assert code == 0
    assert payload["status"] == "research_release_candidate_readiness_doctored"


def test_readiness_summary_answers_in_its_success_envelope(workspace: Path) -> None:
    report_id = _readiness_report_id()

    code, payload = _run(["research", "release-candidate-readiness-summary", report_id, "--json"])

    assert code == 0
    assert payload["status"] == "research_release_candidate_readiness_summarized"


def test_readiness_show_returns_the_report_that_was_asked_for(workspace: Path) -> None:
    """`-show` prints the artifact itself, with no `ok`/`status` envelope.

    The same divergence as `provider-safety-dossier-show`. Asserted as it is
    rather than as the family suggests, because a wrapper migration has to
    preserve it — and because the status key it does not have is what a
    copy-pasted assertion would look for.
    """
    report_id = _readiness_report_id()

    code, payload = _run(["research", "release-candidate-readiness-show", report_id, "--json"])

    assert code == 0
    assert "status" not in payload
    assert payload["release_candidate_readiness_report_id"] == report_id


def test_market_is_disabled_and_has_no_success_path(workspace: Path) -> None:
    """`market` never reaches exit 0, and should not.

    It appeared alongside the genuinely uncovered commands in the execution
    measurement, but `handle_market` returns 1 unconditionally: it is a legacy
    command disabled in the frozen local research pipeline. There is nothing to
    cover, and this pins that rather than leaving it looking like an omission. If
    the command is ever re-enabled, this case fails and asks for a real one.
    """
    code, payload = _run(["research", "market", "--symbol", "AAPL", "--json"])

    assert code == 1
    assert payload["status"] == "legacy_command_disabled"


# ---------------------------------------------------------------------------
# The cutover commands
#
# These were recorded as unreachable from a temporary workspace, on the evidence
# that creation answered `..._blocked` and so wrote no artifact for the
# inspection commands to read. That was wrong, and the mistake is worth keeping
# visible: creation was refused because the *target version* was invalid, not
# because of repository state.
#
# `--target-version 9.9.9` does not match `^v(\d+)\.(\d+)\.(\d+)-rc([1-9]\d*)$`,
# so it never got as far as the repository checks. With `v0.6.27-rc1` the
# artifact is created and all four commands reach exit 0 — while still reporting
# blockers, which is the point of a dry run.
#
# What genuinely needs the repository is the `..._validated` status. `-validate`
# reaches its success envelope either way; validation *passing* is the part that
# depends on release-check scripts, docs and a clean protected boundary.
# ---------------------------------------------------------------------------

#: Matches `_TARGET_RE` in `research/release_candidate_cutover.py`. A version
#: this does not match is refused before any repository check runs.
VALID_RC_TARGET = "v0.6.27-rc1"


def _cutover_report_id() -> str:
    code, created = _run([
        "research", "release-candidate-cutover-dry-run",
        "--target-version", VALID_RC_TARGET, "--json",
    ])
    assert code == 0, created
    assert created["status"] == "research_release_candidate_cutover_dry_run_created", created
    return created["release_candidate_cutover_dry_run_id"]


def test_cutover_creation_succeeds_with_a_valid_rc_target(workspace: Path) -> None:
    """Creation is not gated on repository state, only on the target version."""
    report_id = _cutover_report_id()

    assert report_id


def test_cutover_creation_is_refused_for_a_non_rc_target(workspace: Path) -> None:
    """The refusal that was mistaken for a repository constraint.

    Pinned so the distinction stays visible: this is a version-format refusal,
    and it happens before the repository checks are consulted.
    """
    code, created = _run([
        "research", "release-candidate-cutover-dry-run",
        "--target-version", "9.9.9", "--json",
    ])

    assert code == 1
    assert created["status"] == "research_release_candidate_cutover_dry_run_blocked"
    assert created["target_version"] == "<invalid>"
    assert "target_not_rc" in created["blockers"]


def test_cutover_doctor_answers_in_its_success_envelope(workspace: Path) -> None:
    report_id = _cutover_report_id()

    code, payload = _run([
        "research", "release-candidate-cutover-dry-run-doctor", report_id, "--json",
    ])

    assert code == 0
    assert payload["status"] == "research_release_candidate_cutover_dry_run_doctored"


def test_cutover_summary_answers_in_its_success_envelope(workspace: Path) -> None:
    report_id = _cutover_report_id()

    code, payload = _run([
        "research", "release-candidate-cutover-dry-run-summary", report_id, "--json",
    ])

    assert code == 0
    assert payload["status"] == "research_release_candidate_cutover_dry_run_summarized"


def test_cutover_validate_reaches_its_envelope_but_reports_blockers(workspace: Path) -> None:
    """`-validate` succeeds as a command while validation itself fails.

    Exit 0 with `..._validation_failed` is the documented shape: the command ran,
    and its answer is that the candidate is not ready. Reaching `..._validated`
    needs the repository, which is the constraint already recorded for readiness.
    """
    report_id = _cutover_report_id()

    code, payload = _run([
        "research", "release-candidate-cutover-dry-run-validate", report_id, "--json",
    ])

    assert code == 0
    assert payload["status"] == "research_release_candidate_cutover_dry_run_validation_failed"


def test_the_cutover_listing_contains_the_created_report(workspace: Path) -> None:
    """Now that creation succeeds, the listing can be checked properly.

    An earlier version of this file could only assert the listing was a list,
    because nothing was ever created to appear in it.
    """
    report_id = _cutover_report_id()

    code, listed = _run(["research", "release-candidate-cutover-dry-run-list", "--json"])

    assert code == 0
    assert report_id in [
        item.get("release_candidate_cutover_dry_run_id") for item in listed["items"]
    ]
