# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_unexercised_research_command_envelopes.py
# PURPOSE: Runs the research CLI handlers that no other test executes, and holds
#         them to the JSON envelope contract.
# DEPS:    argparse, json, pytest, atlas_agent.cli.
# ==============================================================================

"""Smoke coverage for the release-candidate and provider-safety-dossier commands.

Coverage over the whole suite put `cli_commands/research/release_candidate.py`
at 3% and `cli_commands/research/safety_dossier.py` at 4%, with every handler
body unexecuted — while the logic behind them,
`research/release_candidate_readiness.py` and `research/provider_safety_dossier.py`,
sits at 81% and 88%. The logic was tested; the CLI wiring to it was not.

`check_cli_command_compatibility.py` and `tests/fixtures/cli_command_contract.json`
pin these command names, which made the gap harder to see: the surface was
asserted to exist while nothing ran it. A handler could pass the wrong argument,
mishandle `--json`, or let an exception escape, and the contract check would
still pass.

What this asserts is deliberately narrow and contract-shaped: the command runs,
answers in the documented envelope, and its exit status agrees with what the
envelope says. A handler reporting `ok: false` while exiting 0 is a refusal the
caller cannot see.

It does not assert a particular refusal code. The research group answers a clean
refusal with exit 1 while `cli_io.emit_cli_error` uses 2 for the same thing —
both conventions are live, and asserting either here would pin the wrong one for
most of the group. That divergence is recorded separately rather than settled by
a test written for something else.

The subcommands are read from the parser rather than listed, so a command added
to either group is covered without editing this file. Required positionals get a
placeholder id, which exercises each handler's not-found path — the branch an
operator hits first.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from atlas_agent.cli import build_parser, main

# --- CONFIGURATION AND CONSTANTS ---

#: The two command groups no other test executes.
UNEXERCISED_PREFIXES = ("release-candidate", "provider-safety-dossier")

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


def _unexercised_commands() -> list[str]:
    return sorted(
        name
        for name in _research_subparsers()
        if name.startswith(UNEXERCISED_PREFIXES)
    )


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


def test_the_command_groups_are_still_found() -> None:
    """Every case below is vacuous if the parser walk stops finding them."""
    commands = _unexercised_commands()

    assert len(commands) >= 15, (
        f"only {len(commands)} commands matched {UNEXERCISED_PREFIXES}: {commands}. "
        "The parser walk has probably stopped reaching the research subcommands."
    )


@pytest.mark.parametrize("command", _unexercised_commands())
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
    assert (code == 0) is payload["ok"], (
        f"`atlas research {command} --json` reported ok={payload['ok']} and exited "
        f"{code}. Success and exit status must agree, whichever refusal code the "
        "command uses."
    )
