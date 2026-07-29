# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_autonomous_paper_honours_the_runtime_kill_switch.py
# PURPOSE: Pins that the autonomous loop honours a kill switch armed on disk,
#         which currently holds because of one rebinding line.
# DEPS:    contextlib, io, json, pathlib, datetime, pytest, atlas_agent.
# ==============================================================================

"""The autonomous path already honours the runtime kill switch. Nothing said so.

`atlas kill-switch enable` writes on-disk state and leaves
`config.safety.kill_switch_enabled` untouched, so a path that reads the config
field alone would keep trading through an armed switch. That is the defect class
already found and fixed in four other consumers.

`agent/autonomous_paper.py` reads exactly that field, passing it to
`RiskManager(kill_switch_enabled=...)`. It is nonetheless correct, because
`cli.py` rebinds `config = _effective_config_with_runtime_kill_switch(config)`
before calling the loop, so the field arrives already OR-ed with the on-disk
state. The property depends entirely on that one line, and no test held it.

This case exists because the investigation that produced it started from the
opposite conclusion. Running `atlas agent autonomous-paper` with the switch armed
reports `completed` and exit 0, which reads like the loop ignoring the stop —
but with a single bar of data the strategy proposes nothing, so no order ever
reaches the gate that would refuse it. The loop running is not the question; the
order being refused is.

So the assertion is on the violation, not on the exit status: with the switch
armed, `kill_switch` must appear among the risk violations for an order that does
reach the gate. `max_symbol_exposure_pct` appears alongside it and is irrelevant
here — what matters is that `kill_switch` is present at all, since the config
field is false throughout.
"""

# --- IMPORTS ---

from __future__ import annotations

import contextlib
import datetime
import io
import json
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

#: Enough bars, with a flat stretch then a sustained rise, for the moving-average
#: strategy to cross over and propose an order. Without a proposed order the risk
#: gate is never reached and this file would assert nothing.
BAR_COUNT = 80


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def trading_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A paper workspace whose data actually produces a proposed order."""
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        main(["init", "."])
        main(["discipline", "setup", "--manual", "--yes"])
        main(["config", "set", "market.symbol", "DEMO-SYMBOL"])

    rows = ["date,symbol,open,high,low,close,volume"]
    start = datetime.date(2026, 1, 1)
    for index in range(BAR_COUNT):
        price = 100.0 if index < BAR_COUNT // 2 else 100.0 + (index - BAR_COUNT // 2) * 2.0
        day = start + datetime.timedelta(days=index)
        rows.append(f"{day},DEMO-SYMBOL,{price:.2f},{price + 1:.2f},{price - 1:.2f},{price:.2f},1000")
    data = tmp_path / "data" / "sample" / "ohlcv.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


def _blocked_violations(workspace: Path) -> list[str]:
    """Rule names from the first risk-blocked decision of the newest run."""
    reports = sorted((workspace / "reports" / "autonomous_paper").glob("*-decisions.jsonl"))
    assert reports, "the loop wrote no decisions log; it did not run"
    for line in reports[-1].read_text(encoding="utf-8").splitlines():
        decision = json.loads(line)
        if decision.get("decision_state") == "risk_blocked":
            return [v["rule"] for v in decision["risk_result"]["violations"]]
    return []


def _run_loop() -> None:
    from atlas_agent.cli import main

    with contextlib.redirect_stdout(io.StringIO()):
        main(["agent", "autonomous-paper", "--max-cycles", str(BAR_COUNT)])


def test_an_order_reaches_the_risk_gate_at_all(trading_workspace: Path) -> None:
    """The premise. Every case below is vacuous without a blocked order."""
    _run_loop()

    assert _blocked_violations(trading_workspace), (
        "no order reached the risk gate, so the kill-switch case below would pass "
        "for that reason instead"
    )


def test_arming_the_switch_on_disk_blocks_the_autonomous_order(
    trading_workspace: Path,
) -> None:
    """`atlas kill-switch enable` has to reach the autonomous loop's risk gate."""
    from atlas_agent.cli_safety import _kill_switch_controller
    from atlas_agent.config.builder import get_effective_config

    _kill_switch_controller(get_effective_config()).enable(
        mode="flatten", reason="emergency", actor="cli", broker=None
    )
    # The config field stays false; only the on-disk state is armed. That is the
    # whole point -- a consumer reading the field alone would see nothing.
    assert get_effective_config().safety.kill_switch_enabled is False

    _run_loop()

    assert "kill_switch" in _blocked_violations(trading_workspace)


def test_the_switch_is_absent_from_violations_when_it_is_not_armed(
    trading_workspace: Path,
) -> None:
    """The negative control.

    Without it, a gate that always reported `kill_switch` would satisfy the case
    above.
    """
    _run_loop()

    assert "kill_switch" not in _blocked_violations(trading_workspace)
