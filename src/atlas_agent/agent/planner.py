# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/planner.py
# PURPOSE: Shows what the agent WOULD do — which routine the current market state
#          selects — without doing any of it. The dry run of the agent itself.
# DEPS:    config, market.session
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any

from atlas_agent.config import AtlasConfig
from atlas_agent.market.session import MarketSessionDetector


# ==============================================================================
# PLAN
# ==============================================================================

def get_agent_plan(config: AtlasConfig) -> str:
    payload = get_agent_plan_payload(config)
    detector = MarketSessionDetector()
    lines = [
        "Atlas Agent Plan",
        f"Detected Market State: {payload['market_state']}",
        f"Requested Mode: {payload['requested_mode']}",
        ""
    ]
    lines.append(f"Plan: {payload['summary']}")
    if payload.get("safety_note"):
        lines.append(f"Safety: {payload['safety_note']}")
    lines.append(f"Market Calendar: {detector.config.timezone}")
    return "\n".join(lines)


def get_agent_plan_payload(config: AtlasConfig) -> dict[str, Any]:
    detector = MarketSessionDetector()
    state = detector.get_state()
    mode = config.trading_mode
    summary: str
    safety_note = ""
    if state == "open":
        if mode == "live" and not config.enable_live_trading:
            summary = (
                "Live mode requested but ENABLE_LIVE_TRADING is false; "
                "order flow fails safely and remains non-executable."
            )
            safety_note = "Live execution remains gated until explicit enable + approvals."
        elif mode == "live":
            summary = "Market open. Live trade cycle with risk manager and approval gates."
            safety_note = "Each live order still requires kill-switch pass, risk pass, and approval."
        else:
            summary = "Market open. Paper trade cycle."
    elif state in ("closed", "premarket", "afterhours", "weekend", "holiday"):
        summary = "Market closed. Research/planning/paper simulation cycle; no live broker orders."
    else:
        summary = "Unknown market state. Defaulting to paper/research cycle."
        safety_note = "Unknown state never forces live execution."
    return {
        "market_state": state,
        "requested_mode": mode,
        "summary": summary,
        "safety_note": safety_note,
    }
