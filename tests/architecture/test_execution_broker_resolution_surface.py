# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_execution_broker_resolution_surface.py
# PURPOSE: Pins which functions may obtain an execution broker, and which of
#         them may do so for live.
# DEPS:    ast, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Structural pin on how a live broker handle is obtained.

`tests/architecture/test_broker_submission_surface.py` pins who may call
`place_order`. This pins the step before it: who may get the broker to call it
on. A path that cannot resolve a live broker cannot submit through one, so this
is the narrower gate of the two.

`run_submit_execution` states the rule in its own docstring — "This is the ONLY
function permitted to call resolve_execution_broker('live') for live
submissions. No other CLI or runtime path may do so." Nothing enforced it, and
this project has already been bitten once by a rule that only existed in prose:
`brokers/guards.py` held guards nobody called, and while nobody called them
`guard_sync` drifted into admitting `paper` as a live sync broker.

Tracing it turns out to leave the docstring true, with the qualifier "for live
submissions" doing real work. There are two resolution sites, not one:

- `run_submit_execution` resolves `"live"` literally. The gated submit funnel.
- `_broker_for_mode` resolves a *variable* mode, so it can be live. Its live
  callers are the kill switch's cancel and flatten — risk-reducing actions, not
  submissions. `run_once` also calls it, but never with live: the live branch
  returns `_run_once_live_analysis` first, verified by calling `run_once` with
  `mode="live"` and observing `_broker_for_mode` is never reached.

Both facts are asserted below, because both are load-bearing and neither was
checked. The second especially: if the live divert in `run_once` were ever
removed, `run_once` would silently gain a live execution path that no gate in
this file's allowlist was written to expect.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"

#: Every function allowed to resolve an execution broker, and why.
#:
#: - `execution/submit_execution.py::run_submit_execution` is the live-submit
#:   funnel. It resolves `"live"` literally, after its full gate chain.
#: - `cli.py::_broker_for_mode` is the CLI's broker factory. It resolves a
#:   variable mode and refuses live unless `resolution.status.can_submit`, so
#:   the live locks apply to it too.
#:
#: Adding an entry means a new way to obtain a broker. That is the moment a
#: human should be looking, which is the whole purpose of pinning the set.
PERMITTED_RESOLUTION_SITES = {
    ("execution/submit_execution.py", "run_submit_execution"),
    ("cli.py", "_broker_for_mode"),
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _resolution_sites() -> set[tuple[str, str]]:
    """Every (module, enclosing function) that calls `resolve_execution_broker`."""
    found: set[tuple[str, str]] = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a parse failure is its own bug
            continue
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != "resolve_execution_broker":
                continue
            enclosing = next(
                (
                    fn.name
                    for fn in functions
                    if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno)
                ),
                "<module>",
            )
            found.add((path.relative_to(SRC_ROOT).as_posix(), enclosing))
    return found


def test_only_the_permitted_functions_resolve_an_execution_broker() -> None:
    """Both directions. A new resolver is a new front door; a missing one means
    this list has gone stale and stopped describing the code."""
    assert _resolution_sites() == PERMITTED_RESOLUTION_SITES


def test_the_submit_funnel_is_the_only_literal_live_resolution() -> None:
    """`resolve_execution_broker("live")` spelled literally, anywhere else, is a
    second submission path regardless of what guards happen to sit around it."""
    literal_live: set[str] = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != "resolve_execution_broker" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value == "live":
                literal_live.add(path.relative_to(SRC_ROOT).as_posix())

    assert literal_live == {"execution/submit_execution.py"}


def test_run_once_never_resolves_a_broker_for_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live divert is what keeps `run_once` off the execution path.

    Asserted by running it rather than by reading the branch above the call. A
    reader can be wrong about which guard dominates; a spy cannot.

    The setup below is not incidental. `run_once` refuses at the discipline gate,
    then for a missing symbol, then for absent bars — all of them long before the
    live branch. A first version of this test did none of it, passed, and kept
    passing with the divert deleted, because it never got within three guards of
    the thing it claimed to check.

    So both directions are asserted: the analysis path was entered, and no broker
    was resolved. The first is what stops this from silently becoming vacuous
    again.
    """
    import atlas_agent.cli as cli
    from atlas_agent.config.builder import get_effective_config

    monkeypatch.chdir(tmp_path)
    cli.main(["init", "."])
    cli.main(["discipline", "setup", "--manual", "--yes"])
    for key, value in (
        ("trading_mode", "live"),
        ("broker.provider", "alpaca"),
        # Must match the symbol in the sample bars, or the strategy gets an empty
        # frame and raises before the branch under test.
        ("market.symbol", "DEMO-SYMBOL"),
    ):
        cli.main(["config", "set", key, value])

    sample = SRC_ROOT.parents[1] / "data" / "sample" / "ohlcv.csv"
    destination = tmp_path / "data" / "sample" / "ohlcv.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    resolved_modes: list[str] = []
    analysis_calls: list[int] = []
    original_broker = cli._broker_for_mode
    original_analysis = cli._run_once_live_analysis

    def broker_spy(mode, *args, **kwargs):
        resolved_modes.append(mode)
        return original_broker(mode, *args, **kwargs)

    def analysis_spy(*args, **kwargs):
        analysis_calls.append(1)
        return original_analysis(*args, **kwargs)

    monkeypatch.setattr(cli, "_broker_for_mode", broker_spy)
    monkeypatch.setattr(cli, "_run_once_live_analysis", analysis_spy)

    cli.run_once(mode="live", config=get_effective_config())

    assert analysis_calls, "run_once never reached the live branch; the test is vacuous"
    assert "live" not in resolved_modes
