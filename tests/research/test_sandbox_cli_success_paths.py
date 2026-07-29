# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_sandbox_cli_success_paths.py
# PURPOSE: Drives sandbox-show, sandbox-validate and sandbox-replay to success,
#         which nothing else did.
# DEPS:    contextlib, io, json, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Success envelopes for the sandbox inspection commands.

Instrumenting `dispatch_research` across a full suite run found that all 170
research commands execute but only 153 ever reach exit 0. Three of the seventeen
that never did are `sandbox-show`, `sandbox-validate` and `sandbox-replay`.

`tests/research/test_research_sandbox_cli.py` is extensive — 301 in-process
`main([...])` calls — and does drive `research sandbox` itself to success. What
it never does is inspect the request it just created, so the three commands that
read one back were only ever exercised on their not-found path, by
`test_research_command_envelopes.py` and its placeholder ids.

That gap is the enabling work for `CAND-035`. A wrapper migration rewrites each
handler's success branch as well as its error envelope, and the envelope suite
pins only the latter.

Reaching success needs the whole lineage — a research artifact, a prompt packet
from it, then a sandbox request from that — which is why an empty workspace
cannot get there and why these three sat uncovered.
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

#: Command -> the success status it must answer with, once a sandbox request
#: exists to inspect.
INSPECTION_COMMANDS = {
    "sandbox-show": "research_sandbox_loaded",
    "sandbox-validate": "research_sandbox_validated",
    "sandbox-replay": "research_sandbox_replayed",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run(argv: list[str]) -> tuple[int | None, dict]:
    from atlas_agent.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


@pytest.fixture
def sandbox_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A real sandbox request id, built through its full lineage.

    The domain functions are called directly for the setup rather than the CLI,
    because the point of this file is the three inspection commands; using the
    CLI to build the lineage would not add coverage and would obscure a setup
    failure as a failure of the command under test.
    """
    from atlas_agent.research.session import generate_prompt_packet, run_research_session

    monkeypatch.chdir(tmp_path)
    (tmp_path / "memory").mkdir(exist_ok=True)
    (tmp_path / "events").mkdir(exist_ok=True)

    artifact = run_research_session(
        symbol="AAPL",
        workspace_path=tmp_path,
        memory_dir=None,
        event_logger=None,
        provider_name="deterministic",
    )
    packet = generate_prompt_packet(
        workspace_path=tmp_path, run_id=artifact.run_id, event_logger=None
    )

    code, created = _run(["research", "sandbox", packet["prompt_packet_id"], "--json"])
    assert code == 0 and created["status"] == "research_sandbox_request_created", (
        "the lineage this file depends on stopped building; the cases below would "
        "fail as if the inspection commands had broken"
    )
    return created["sandbox_request_id"]


@pytest.mark.parametrize(
    "command,expected_status", sorted(INSPECTION_COMMANDS.items())
)
def test_inspection_command_answers_in_its_success_envelope(
    sandbox_request: str, command: str, expected_status: str
) -> None:
    """Each command reads back the request and says so in the documented shape."""
    code, payload = _run(["research", command, sandbox_request, "--json"])

    assert code == 0
    assert payload["ok"] is True
    assert payload["status"] == expected_status


def test_show_returns_the_request_that_was_asked_for(sandbox_request: str) -> None:
    """The status alone would pass while returning somebody else's artifact."""
    _code, payload = _run(["research", "sandbox-show", sandbox_request, "--json"])

    rendered = json.dumps(payload)
    assert sandbox_request in rendered


def test_replay_reports_a_match_for_an_untouched_request(sandbox_request: str) -> None:
    """Replay exists to detect divergence, so on a fresh artifact it must agree.

    Asserting only the status would leave `match: false` passing, which is the
    answer that means the artifact has changed under us.
    """
    _code, payload = _run(["research", "sandbox-replay", sandbox_request, "--json"])

    assert payload.get("match") is True
