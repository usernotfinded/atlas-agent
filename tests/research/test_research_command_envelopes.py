# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_command_envelopes.py
# PURPOSE: Runs every `atlas research` subcommand and holds each to the JSON
#         envelope contract.
# DEPS:    argparse, json, pytest, atlas_agent.cli.
# ==============================================================================

"""Smoke coverage for the whole `atlas research` command surface.

Coverage over the full suite put `cli_commands/research/release_candidate.py` at
3% and `cli_commands/research/safety_dossier.py` at 4%, with every handler body
unexecuted — while the logic behind them, `research/release_candidate_readiness.py`
and `research/provider_safety_dossier.py`, sat at 81% and 88%. The logic was
tested; the CLI wiring to it was not. Neighbouring handler modules were at 17%
to 53% for the same reason, so this covers all 175 subcommands rather than the
two groups that surfaced first.

`check_cli_command_compatibility.py` and `tests/fixtures/cli_command_contract.json`
pin these names, which made the gap harder to see: the surface was asserted to
exist while nothing ran it. A handler could pass the wrong argument, mishandle
`--json`, or let an exception escape, and the contract check would still pass.

What each case asserts is deliberately narrow and contract-shaped: the command
runs, answers in the documented envelope, and its exit status agrees with what
the envelope says. A handler reporting `ok: false` while exiting 0 is a refusal
the caller cannot see — four commands do exactly that and are marked below.

It does not assert a particular refusal code. The research group answers a clean
refusal with exit 1 while `cli_io.emit_cli_error` uses 2 for the same thing.
Both conventions are live, and asserting either here would pin the wrong one for
most of the group; the divergence is recorded in
`docs/development/safety-invariant-audit-followups.md` rather than settled by a
test written for something else.

Subcommands are read from the parser, so one added tomorrow is covered without
editing this file. Required arguments get a placeholder id, which exercises each
handler's not-found path — the branch an operator hits first.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from atlas_agent.cli import build_parser, main

# --- CONFIGURATION AND CONSTANTS ---

#: Commands whose exit status disagrees with their own envelope: each reports
#: `ok: false` for a missing artifact and exits 0. Their `-show` siblings report
#: the same condition with exit 1, so this is an inconsistency inside a command
#: family rather than a convention. Marked rather than fixed — see
#: `docs/development/safety-invariant-audit-followups.md`.
EXIT_STATUS_DISAGREES = frozenset(
    {
        "provider-credential-boundary-summary",
        "provider-execution-chain-doctor",
        "provider-opt-in-policy-summary",
        "provider-preflight-freeze-summary",
    }
)

#: Stands in for a required id. Nothing by this name exists, which is the point.
PLACEHOLDER_ID = "nonexistent-id-for-smoke-coverage"

#: The research group answers a clean refusal with exit 1 — `research dossier`,
#: `research show`, and `research backtest-proposal` all do, and they are covered
#: by tests. `cli_io.emit_cli_error` uses 2 for the same thing, and says why in a
#: comment: "exit 1 is what an uncaught Python traceback produces", so reserving 2
#: lets a caller tell a refusal from a crash. Both conventions are live, which is
#: recorded in `safety-invariant-audit-followups.md`.
#:
#: This test therefore asserts the property that holds under either: the exit code
#: agrees with the envelope. Pinning one convention here would pin the wrong one
#: for most of the group.
ACCEPTABLE_EXIT_CODES = frozenset({0, 1, 2})


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _research_subparsers() -> dict[str, argparse.ArgumentParser]:
    """The `atlas research <name>` subparsers, keyed by name."""
    parser = build_parser()
    research = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            research = action.choices.get("research")
            break
    assert research is not None, "the `research` command is no longer in the parser"

    for action in research._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("`atlas research` no longer has subcommands")


def _all_research_commands() -> list[str]:
    return sorted(_research_subparsers())


def _argv_for(name: str) -> list[str]:
    """Build a runnable argv, filling every required argument with a placeholder.

    Required *options* matter as much as positionals here: two commands in these
    groups take `--output` and `--target-version`, and missing either sends the
    call through argparse instead of the handler this test exists to run.
    """
    parser = _research_subparsers()[name]
    argv = ["research", name]

    for action in parser._actions:
        if action.dest == "help":
            continue
        if not action.option_strings:
            argv.append(PLACEHOLDER_ID)
        elif action.required:
            argv.extend([action.option_strings[0], PLACEHOLDER_ID])

    argv.append("--json")
    return argv


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> Path:
    """An initialised, empty workspace to answer from."""
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    return tmp_path


def test_the_command_surface_is_still_found() -> None:
    """Every case below is vacuous if the parser walk stops finding commands."""
    commands = _all_research_commands()

    assert len(commands) >= 150, (
        f"the parser walk found only {len(commands)} research subcommands. It has "
        "probably stopped reaching them rather than the surface having shrunk."
    )


def test_the_marked_commands_still_exist() -> None:
    """A marked command that vanished would leave a stale exemption behind."""
    missing = EXIT_STATUS_DISAGREES - set(_all_research_commands())

    assert missing == set(), (
        f"{sorted(missing)} are marked as exit-status disagreements and no longer "
        "exist. Remove them from EXIT_STATUS_DISAGREES."
    )


@pytest.mark.parametrize("command", _all_research_commands())
def test_command_answers_in_the_json_envelope(
    command: str, workspace: Path, capsys
) -> None:
    """Each handler runs, and says no in the documented shape rather than crashing."""
    try:
        code = main(_argv_for(command))
    except SystemExit as exc:  # argparse refusing the argv this test built
        raise AssertionError(
            f"`atlas research {command} --json` exited through argparse "
            f"({exc.code}); the argv this test builds no longer matches the "
            "command's signature."
        ) from exc

    captured = capsys.readouterr()

    assert code in ACCEPTABLE_EXIT_CODES, (
        f"`atlas research {command} --json` returned {code}. stderr: "
        f"{captured.err[:400]}"
    )

    try:
        payload = json.loads(captured.out)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"`atlas research {command} --json` did not emit JSON. "
            f"stdout: {captured.out[:400]!r}"
        ) from exc

    assert "ok" in payload, (
        f"`atlas research {command} --json` emitted JSON without an `ok` field: "
        f"{sorted(payload)}"
    )
    assert isinstance(payload["ok"], bool)

    # The property that survives both exit-code conventions, and the one worth
    # having: a command that reports failure must not exit 0. A handler that says
    # `ok: false` and returns success is a refusal a caller cannot see.
    if command in EXIT_STATUS_DISAGREES:
        pytest.xfail(
            f"`atlas research {command}` reports ok={payload['ok']} and exits "
            f"{code}. Its `-show` sibling reports the same missing artifact with "
            "exit 1."
        )

    assert (code == 0) is payload["ok"], (
        f"`atlas research {command} --json` reported ok={payload['ok']} and exited "
        f"{code}. Success and exit status must agree, whichever refusal code the "
        "command uses."
    )
