# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    update/safety.py
# PURPOSE: Decides whether it is safe to UPDATE the agent's own code right now.
#          Swapping the binary out from under a live agent with open positions is a
#          uniquely bad idea: the process that would have to close them is the one
#          being replaced.
# DEPS:    config + brokers + portfolio (to see what is at stake), safety.kill_switch
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.brokers.ccxt_adapter import CCXTBroker
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.config import AtlasConfig
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.safety import KillSwitchController


# ==============================================================================
# SAFETY RESULT
# ==============================================================================

@dataclass(frozen=True)
class UpdateSafetyResult:
    safe: bool
    # blockers STOP the update; warnings merely inform. The split matters: live
    # trading with open positions is a blocker, while an untidy working tree is not.
    blockers: list[str]
    warnings: list[str]


# ==============================================================================
# SAFETY PROBES
# ==============================================================================

# Each probe answers one question about what an update would interrupt. They are a
# Protocol so the whole gate can be exercised in tests without a broker, a portfolio
# or a git repo.
class UpdateSafetyCheck(Protocol):
    def is_live_trading_enabled(self) -> bool:
        ...

    def has_open_positions(self) -> bool:
        ...

    def has_pending_orders(self) -> bool:
        ...

    def has_uncommitted_changes(self) -> bool:
        ...

    def kill_switch_available(self) -> bool:
        ...

    def smoke_check(self) -> bool:
        ...


BrokerLoader = Callable[[AtlasConfig], Any]


@dataclass
class RuntimeUpdateSafetyCheck:
    config: AtlasConfig
    workspace_root: Path
    repo_root: Path
    broker_loader: BrokerLoader | None = None
    smoke_command: list[str] | None = None

    def is_live_trading_enabled(self) -> bool:
        return self.config.trading_mode == "live" and self.config.enable_live_trading

    def has_open_positions(self) -> bool:
        broker = self._resolve_broker()
        if broker is None:
            return False
        positions = broker.get_positions()
        for position in positions:
            quantity = getattr(position, "quantity", 0)
            if abs(float(quantity)) > 0:
                return True
        return False

    def has_pending_orders(self) -> bool:
        pending_dir = self.config.pending_orders_dir
        pending_dir.mkdir(parents=True, exist_ok=True)
        return any(pending_dir.glob("*.json"))

    def has_uncommitted_changes(self) -> bool:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        return bool(result.stdout.strip())

    def kill_switch_available(self) -> bool:
        try:
            controller = KillSwitchController(
                state_path=self.config.memory_dir / "kill_switch_state.json",
                enabled_flag_path=self.config.memory_dir / "kill_switch.enabled",
            )
            controller.status()
        except Exception:
            return False
        return True

    def smoke_check(self) -> bool:
        command = self.smoke_command or [sys.executable, "-m", "atlas_agent.cli", "--help"]
        result = subprocess.run(
            command,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _resolve_broker(self) -> Any | None:
        loader = self.broker_loader or _default_broker_loader
        return loader(self.config)


def evaluate_update_safety(check: UpdateSafetyCheck) -> UpdateSafetyResult:
    blockers: list[str] = []
    warnings: list[str] = []

    live_enabled = _safe_call(check.is_live_trading_enabled, "live trading flag", blockers, warnings)
    if live_enabled is True:
        blockers.append("live trading is enabled")
    open_positions = _safe_call(check.has_open_positions, "open positions check", blockers, warnings)
    if open_positions is True:
        blockers.append("broker has open positions")
    pending_orders = _safe_call(check.has_pending_orders, "pending orders check", blockers, warnings)
    if pending_orders is True:
        blockers.append("broker has pending orders")
    dirty_tree = _safe_call(check.has_uncommitted_changes, "working tree check", blockers, warnings)
    if dirty_tree is True:
        blockers.append("working tree has uncommitted changes")

    kill_switch_ok = _safe_call(check.kill_switch_available, "kill switch availability", blockers, warnings)
    if kill_switch_ok is False:
        blockers.append("kill switch is not available")

    return UpdateSafetyResult(
        safe=not blockers,
        blockers=blockers,
        warnings=warnings,
    )


def _safe_call(
    fn: Callable[[], bool],
    label: str,
    blockers: list[str],
    warnings: list[str],
) -> bool | None:
    try:
        return bool(fn())
    except Exception as exc:
        blockers.append(f"unable to evaluate {label}: {exc}")
        warnings.append(f"{label} failed: {exc}")
        return None


def _default_broker_loader(config: AtlasConfig) -> Any | None:
    if config.trading_mode != "live" or config.live_broker in {"", "none"}:
        return PaperBroker(PortfolioState(cash=config.starting_cash))
    if config.live_broker == "alpaca":
        return AlpacaBroker(config)
    if config.live_broker == "binance":
        return BinanceBroker(config)
    if config.live_broker == "ccxt":
        return CCXTBroker(config)
    return None
