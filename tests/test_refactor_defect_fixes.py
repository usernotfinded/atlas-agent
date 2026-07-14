# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_refactor_defect_fixes.py
# PURPOSE: Regression tests for the defects found during the code-structure
#          refactor. Each test pins a property that was previously broken, so the
#          fix cannot silently regress.
# DEPS:    pytest
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from datetime import date

import pytest

from atlas_agent.market_data.base import Bar


# ==============================================================================
# 1. cli_safety: `Any` was used in an annotation but never imported
# ==============================================================================

def test_cli_safety_annotation_names_all_resolve() -> None:
    """Every name used in an annotation must exist in the module namespace."""
    # The defect: `_audit_hook` (a CLOSURE inside _kill_switch_controller) annotated a
    # parameter as `dict[str, Any]` while `Any` was never imported.
    #
    # `from __future__ import annotations` made that invisible — annotations became
    # lazy strings and were never evaluated, so nothing raised. Calling get_type_hints()
    # on the OUTER function does not catch it either, because it never descends into the
    # nested function. Hence the AST walk: it inspects every annotation in the module,
    # including the ones inside closures, and checks each name can actually be resolved.
    import ast
    import builtins
    import inspect

    import atlas_agent.cli_safety as cli_safety

    tree = ast.parse(inspect.getsource(cli_safety))
    annotation_names: set[str] = set()
    for node in ast.walk(tree):
        annotation = getattr(node, "annotation", None) or getattr(node, "returns", None)
        if annotation is None:
            continue
        for inner in ast.walk(annotation):
            if isinstance(inner, ast.Name):
                annotation_names.add(inner.id)

    unresolvable = sorted(
        name
        for name in annotation_names
        if not hasattr(cli_safety, name) and not hasattr(builtins, name)
    )
    assert unresolvable == [], f"annotation names not importable in module: {unresolvable}"


# ==============================================================================
# 1b. Secrets are compared in constant time
# ==============================================================================

def test_secret_comparisons_use_constant_time_equality() -> None:
    """TOTP codes and approval hashes must never be compared with `==`.

    A plain comparison short-circuits on the first differing byte, so its running time
    leaks how many leading bytes were correct. That is not observable from behaviour —
    both `==` and compare_digest return the same booleans — so it is asserted against
    the source, which is where the property actually lives.
    """
    import inspect

    from atlas_agent.execution import approval
    from atlas_agent.safety import totp

    totp_src = inspect.getsource(totp.verify_totp)
    assert "compare_digest" in totp_src
    assert "== normalized" not in totp_src

    approval_src = inspect.getsource(approval.ApprovalManager.is_approved)
    assert "compare_digest" in approval_src
    assert "approval_hash != recomputed" not in approval_src


# ==============================================================================
# 2. config.secrets: .env.atlas was rewritten non-atomically
# ==============================================================================

def test_set_secret_does_not_destroy_other_secrets_on_write_failure(
    tmp_path, monkeypatch
) -> None:
    """A failed write must leave the previous .env.atlas intact, not truncated."""
    from pathlib import Path

    from atlas_agent.config import secrets as secrets_mod

    env_path = tmp_path / ".env.atlas"
    monkeypatch.setattr(secrets_mod, "get_env_atlas_path", lambda: env_path)
    monkeypatch.delenv("FIRST_TOKEN", raising=False)
    monkeypatch.delenv("SECOND_TOKEN", raising=False)

    secrets_mod.set_secret("FIRST_TOKEN", "value-one")
    assert "FIRST_TOKEN=value-one" in env_path.read_text(encoding="utf-8")

    # Simulate a disk filling up PART WAY THROUGH the write, which is the failure the
    # atomic write exists to survive. Opening a file in "w" mode truncates it before a
    # single byte is written, so this replacement truncates whatever it is handed and
    # then fails — exactly what a real mid-write ENOSPC does.
    #
    # This is what discriminates the fix from the bug:
    #   OLD: write_text() was called on .env.atlas itself  -> truncated, FIRST_TOKEN gone.
    #   NEW: it is called on a temp file, and os.replace()  -> .env.atlas never touched.
    real_write_text = Path.write_text

    def _truncate_then_fail(self: Path, *_args, **_kwargs):
        self.write_bytes(b"")  # the truncation a "w"-mode open performs
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "write_text", _truncate_then_fail)
    with pytest.raises(OSError):
        secrets_mod.set_secret("SECOND_TOKEN", "value-two")
    monkeypatch.setattr(Path, "write_text", real_write_text)

    # The first secret survived the failed write of the second.
    assert "FIRST_TOKEN=value-one" in env_path.read_text(encoding="utf-8")


def test_set_secret_keeps_env_file_private(tmp_path, monkeypatch) -> None:
    """.env.atlas must stay 0600 after an atomic rewrite."""
    from atlas_agent.config import secrets as secrets_mod

    env_path = tmp_path / ".env.atlas"
    monkeypatch.setattr(secrets_mod, "get_env_atlas_path", lambda: env_path)
    monkeypatch.delenv("SOME_TOKEN", raising=False)

    secrets_mod.set_secret("SOME_TOKEN", "abc123")
    assert env_path.stat().st_mode & 0o777 == 0o600


# ==============================================================================
# 3. KillSwitchController: a corrupt state file failed OPEN
# ==============================================================================

def test_corrupt_kill_switch_state_fails_closed(tmp_path) -> None:
    """An unreadable kill-switch state file must ARM the switch, never disarm it."""
    from atlas_agent.safety.kill_switch import KillSwitchController

    state_path = tmp_path / "kill_switch_state.json"
    flag_path = tmp_path / "kill_switch.enabled"

    # A file exists — someone wrote it — but it cannot be parsed. We cannot know
    # whether it said "flatten". The only safe reading is that the brake is on.
    state_path.write_text("{ this is not json", encoding="utf-8")
    assert not flag_path.exists()

    controller = KillSwitchController(
        state_path=state_path, enabled_flag_path=flag_path
    )
    state = controller.status()

    assert state.enabled is True, "corrupt state must not read as a disarmed switch"
    # Braking, but not liquidating: escalating to flatten would send real sell orders
    # on the strength of a file we just admitted we cannot read.
    assert state.mode == "soft"


def test_absent_kill_switch_state_is_disabled(tmp_path) -> None:
    """No state file at all means the switch was never armed — that is not a fault."""
    from atlas_agent.safety.kill_switch import KillSwitchController

    controller = KillSwitchController(
        state_path=tmp_path / "kill_switch_state.json",
        enabled_flag_path=tmp_path / "kill_switch.enabled",
    )
    assert controller.status().enabled is False


def test_valid_kill_switch_state_round_trips(tmp_path) -> None:
    """The fail-closed path must not shadow a readable, legitimately-disabled state."""
    from atlas_agent.safety.kill_switch import KillSwitchController

    state_path = tmp_path / "kill_switch_state.json"
    state_path.write_text(
        json.dumps({"enabled": False, "mode": "soft", "reason": "", "actor": "test"}),
        encoding="utf-8",
    )
    controller = KillSwitchController(
        state_path=state_path, enabled_flag_path=tmp_path / "kill_switch.enabled"
    )
    assert controller.status().enabled is False


# ==============================================================================
# 4. Constant-time comparison of secrets
# ==============================================================================

def test_totp_verification_still_accepts_a_valid_code() -> None:
    """compare_digest must not have broken the happy path."""
    from atlas_agent.safety.totp import generate_totp, verify_totp

    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(secret, generate_totp(secret)) is True


def test_totp_verification_rejects_a_wrong_code() -> None:
    from atlas_agent.safety.totp import generate_totp, verify_totp

    secret = "JBSWY3DPEHPK3PXP"
    valid = generate_totp(secret)
    wrong = "000000" if valid != "000000" else "111111"
    assert verify_totp(secret, wrong) is False


# ==============================================================================
# 5. strategies/rsi.py and strategies/breakout.py were fakes
# ==============================================================================

def _bars(closes, highs=None, lows=None) -> list[Bar]:
    highs = highs or closes
    lows = lows or closes
    return [
        Bar(
            date=date(2026, 1, index + 1),
            symbol="TEST",
            open=close,
            high=high,
            low=low,
            close=close,
            volume=100.0,
        )
        for index, (close, high, low) in enumerate(zip(closes, highs, lows))
    ]


def test_rsi_strategy_is_not_a_moving_average_in_disguise() -> None:
    """RSIStrategy must compute an RSI, not inherit MovingAverageStrategy."""
    from atlas_agent.strategies.moving_average import MovingAverageStrategy
    from atlas_agent.strategies.rsi import RSIStrategy

    assert not issubclass(RSIStrategy, MovingAverageStrategy)


def test_rsi_strategy_buys_when_oversold() -> None:
    from atlas_agent.strategies.rsi import RSIStrategy

    # A monotonic decline drives RSI to its floor.
    decision = RSIStrategy().decide(_bars([100 - index * 2 for index in range(20)]))
    assert decision.action == "buy"
    assert 0.0 <= decision.confidence <= 1.0
    assert decision.proposed_order is not None
    assert decision.proposed_order.side == "buy"


def test_rsi_strategy_sells_when_overbought() -> None:
    from atlas_agent.strategies.rsi import RSIStrategy

    decision = RSIStrategy().decide(_bars([50 + index * 2 for index in range(20)]))
    assert decision.action == "sell"


def test_rsi_strategy_holds_without_enough_history() -> None:
    from atlas_agent.strategies.rsi import RSIStrategy

    # RSI over N periods needs N+1 closes. Fewer must yield a hold, not a signal
    # computed from a truncated window.
    decision = RSIStrategy(period=14).decide(_bars([100.0, 101.0, 102.0]))
    assert decision.action == "hold"
    assert decision.proposed_order is None


def test_breakout_strategy_is_not_a_moving_average_in_disguise() -> None:
    from atlas_agent.strategies.breakout import BreakoutStrategy
    from atlas_agent.strategies.moving_average import MovingAverageStrategy

    assert not issubclass(BreakoutStrategy, MovingAverageStrategy)


def test_breakout_strategy_buys_above_the_channel() -> None:
    from atlas_agent.strategies.breakout import BreakoutStrategy

    decision = BreakoutStrategy(lookback=20).decide(_bars([100.0] * 21 + [110.0]))
    assert decision.action == "buy"
    assert decision.proposed_order is not None


def test_breakout_strategy_holds_inside_the_channel() -> None:
    from atlas_agent.strategies.breakout import BreakoutStrategy

    # A perfectly flat series never leaves its own range. Touching the boundary is not
    # breaking it.
    decision = BreakoutStrategy(lookback=20).decide(_bars([100.0] * 25))
    assert decision.action == "hold"


def test_breakout_strategy_holds_without_enough_history() -> None:
    from atlas_agent.strategies.breakout import BreakoutStrategy

    decision = BreakoutStrategy(lookback=20).decide(_bars([100.0] * 5))
    assert decision.action == "hold"


# ==============================================================================
# 6. Stubs must not fabricate
# ==============================================================================

def test_skill_miner_does_not_fabricate_evidence(tmp_path) -> None:
    """An unimplemented miner must return nothing, not an invented skill."""
    from atlas_agent.learning.skill_miner import mine_skills_from_journal

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "trade_journal.md").write_text(
        "# Trade Journal\n\n" + ("- an entry\n" * 40), encoding="utf-8"
    )

    # The old implementation returned a static skill whose `evidence` field claimed
    # "Observed multiple similar entries" — a fabricated claim about the user's own
    # trading. Nothing was ever observed.
    assert mine_skills_from_journal(memory_dir) == []


def test_memory_nudge_does_not_fabricate(tmp_path) -> None:
    """An unimplemented nudge generator must return None, not a canned suggestion."""
    from atlas_agent.learning.nudges import generate_memory_nudge

    assert generate_memory_nudge(tmp_path) is None
